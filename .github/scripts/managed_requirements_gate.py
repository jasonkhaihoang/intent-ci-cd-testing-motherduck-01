"""Fail a Domain change that gives a version to a package the managed constraints name (VD-6569).

A managed package is any package in `.github/managed-constraints.txt`, the file the bundle
delivers (ADR 0023), so this check keeps no list of its own. A pin is any version specifier
(`==`, `>=`, `~=`, `<`, `!=`, ranges) on such a package in the Domain's
`ingestion/requirements.txt` or a vendored connector's
`ingestion/sources/<connector>/requirements.txt`. Vibedata manages the version, and a stale
pin makes pip refuse the install (VD-6464).

The parsing mirrors `neutralize_requirements` in the plugin's `scripts/runtime_pins.py`: names
compare after PEP 503 normalisation; extras, environment markers and trailing comments do not
hide a pin. Not a pin, so never reported: a bare name, a package the managed set does not
name, comments, blank lines, options and includes (`-r`, `-c`, `-e`, `--index-url`; an
included file is not followed), and direct references (`name @ url`, a URL or VCS line), which
carry no version to remove and are left to conflict loudly at install time.

A missing constraints file fails the check: without it the gate cannot judge, and the workflow
that runs it arrives in the same deploy as the file.

CLI:
    managed_requirements_gate.py [--repo-root .] [--constraints .github/managed-constraints.txt]

Stdlib only. Exit 0 clean, 1 on any pin or a missing constraints file.
"""
import argparse
import glob
import os
import re
import sys

_REQUIREMENT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?\s*(.*)$")
_SPECIFIER = re.compile(r"^\(?\s*(===|==|>=|<=|~=|!=|<|>)")
DEFAULT_CONSTRAINTS = os.path.join(".github", "managed-constraints.txt")


def _normalize(name: str) -> str:
    """PEP 503 name normalization."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_line(raw: str):
    """(name, specifier text) of a requirement line, or None for anything that is not one."""
    content = raw.rstrip("\r\n").partition(" #")[0]
    if content.lstrip().startswith(("#", "-")) or "@" in content or "://" in content:
        return None
    head = content.partition(";")[0].strip()
    match = _REQUIREMENT.match(head)
    return (match.group(1), match.group(3).strip()) if match else None


def managed_names(constraints_text: str) -> set:
    """Normalized names of every package the constraints file names."""
    names = set()
    for raw in constraints_text.splitlines():
        parsed = _parse_line(raw)
        if parsed:
            names.add(_normalize(parsed[0]))
    return names


def managed_versions(constraints_text: str) -> dict:
    """Normalized name -> the constraint lines (comments dropped) that give it a version."""
    versions = {}
    for raw in constraints_text.splitlines():
        parsed = _parse_line(raw)
        if parsed:
            versions.setdefault(_normalize(parsed[0]), []).append(raw.partition(" #")[0].strip())
    return versions


def neutralize_requirements(text: str, managed: dict) -> tuple:
    """`text` with the version dropped from every requirement on a managed package (VD-6588).

    Mirrors `neutralize_requirements` in the plugin's `scripts/runtime_pins.py`: the managed
    version wins, so `dlt==1.29.0` under a managed `dlt==1.30.0` is published as `dlt`. Name,
    extras, environment marker and trailing comment stay; every other line passes through byte
    for byte, line endings included. `managed` is `managed_versions(...)`. Returns the new text
    and one note per dropped pin.
    """
    out, notes = [], []
    for raw in text.splitlines(keepends=True):
        body = raw.rstrip("\r\n")
        ending = raw[len(body):]
        content, hash_sep, comment = body.partition(" #")
        if content.lstrip().startswith(("#", "-")) or "@" in content or "://" in content:
            out.append(raw)
            continue
        head, marker_sep, marker = content.partition(";")
        match = _REQUIREMENT.match(head.strip())
        if not match or not match.group(3).strip() or _normalize(match.group(1)) not in managed:
            out.append(raw)
            continue
        name, extras = match.group(1), match.group(2) or ""
        rewritten = f"{name}{extras}" + (f" ;{marker}" if marker_sep else "")
        notes.append(f"ignored {head.strip()}: Vibedata manages {', '.join(managed[_normalize(name)])}")
        out.append(f"{rewritten}{hash_sep}{comment}{ending}")
    return "".join(out), notes


def is_requirements_file(path: str) -> bool:
    """Only `ingestion/requirements.txt` and `ingestion/sources/<connector>/requirements.txt`."""
    parts = path.split("/")
    return parts == ["ingestion", "requirements.txt"] or (
        len(parts) == 4 and parts[:2] == ["ingestion", "sources"] and parts[3] == "requirements.txt")


def find_managed_pins(text: str, managed: set, path: str) -> list:
    """One {file, line, package, message} per version pinned on a managed package in `text`."""
    findings = []
    for number, raw in enumerate(text.splitlines(), start=1):
        parsed = _parse_line(raw)
        if not parsed or _normalize(parsed[0]) not in managed or not _SPECIFIER.match(parsed[1]):
            continue
        name = parsed[0]
        findings.append({
            "file": path,
            "line": number,
            "package": name,
            "message": (
                f"{path}:{number}: '{name}' is pinned ({raw.strip()}); remove the version "
                "because Vibedata manages it"
            ),
        })
    return findings


def _requirement_files(repo_root: str) -> list:
    root_file = os.path.join(repo_root, "ingestion", "requirements.txt")
    found = [root_file] if os.path.isfile(root_file) else []
    found += sorted(glob.glob(os.path.join(repo_root, "ingestion", "sources", "*", "requirements.txt")))
    return found


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--constraints", default=None, help=f"default: <repo-root>/{DEFAULT_CONSTRAINTS}")
    args = ap.parse_args(argv)
    constraints = args.constraints or os.path.join(args.repo_root, DEFAULT_CONSTRAINTS)
    try:
        with open(constraints, encoding="utf-8") as f:
            managed = managed_names(f.read())
    except OSError:
        print(f"managed requirements check: cannot read {constraints}; deploy the CI bundle to deliver it", file=sys.stderr)
        return 1
    findings = []
    for path in _requirement_files(args.repo_root):
        with open(path, encoding="utf-8", errors="replace") as f:
            findings += find_managed_pins(f.read(), managed, os.path.relpath(path, args.repo_root))
    for finding in findings:
        print(finding["message"], file=sys.stderr)
        print(f"::error file={finding['file']},line={finding['line']}::{finding['message']}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
