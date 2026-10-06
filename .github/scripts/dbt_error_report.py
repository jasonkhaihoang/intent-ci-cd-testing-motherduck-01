"""
Wrap a dbt command and write a structured error report JSON.

Usage:
    python dbt_error_report.py <report_path> <dbt args...>

Writes {"passed": bool, "errors": [{"model": str, "message": str}]} to <report_path>.
Exits with the underlying dbt command exit code.
"""
import json
import pathlib
import re
import subprocess
import sys

import parse_run_results as prr
import runner_io

# Matches: "Compilation Error in model my_model (path/to/model.sql)"
# Also handles dbt log-prefixed lines like "16:04:22  Compilation Error in model …"
_COMPILE_ERROR_RE = re.compile(r"Compilation Error in model (\S+)")

# dbt prefixes most log lines with "HH:MM:SS  "; the error header itself often
# arrives unprefixed, so both shapes have to normalize to the same text.
_LOG_PREFIX_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\s+")

# "Parsing Error", "Compilation Error", "Database Error", "Runtime Error" — the
# header dbt prints before the detail it failed on. Matched as a prefix, not a
# whole line: dbt writes the header alone for a project-level rejection but
# appends the node for a model-level one ("Compilation Error in model x (...)"),
# and both are headers followed by their detail.
_ERROR_HEADER_RE = re.compile(r"(?:Parsing|Compilation|Database|Runtime) Error")


# Closed list of credential shapes that can appear in a dbt error dbt itself
# prints — a package URL it failed to clone, a profile it failed to open. A
# commit-status description is readable by anyone with repo read, so these are
# replaced while the rest of the message survives: a redacted message the reader
# can still act on beats a generic one they cannot (ADR-0085's human-UI posture).
_CREDENTIAL_PATTERNS = (
    # https://user:secret@host, and https://token@host — a token used as the
    # whole userinfo has no colon, which is the shape `dbt deps` produces for a
    # git package URL.
    re.compile(r"//[^/\s:@]+:[^/\s@]+@"),
    re.compile(r"//[^/\s:@]+@"),
    # Classic GitHub tokens, and github_pat_, the fine-grained prefix that is
    # the default for anything minted today.
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    # Secrets carried as query or key=value pairs, including an Azure SAS
    # signature.
    re.compile(r"\b(?:motherduck_token|token|password|secret|sig)=\S+", re.IGNORECASE),
)


def _strip_log_prefix(line: str) -> str:
    return _LOG_PREFIX_RE.sub("", line).strip()


def _redact(text: str) -> str:
    for pattern in _CREDENTIAL_PATTERNS:
        replacement = "//[REDACTED]@" if pattern.pattern.startswith("//") else "[REDACTED]"
        text = pattern.sub(replacement, text)
    return text


def _extract_errors_from_summary(failures: list) -> list[dict]:
    """Map parse_run_results failure dicts to [{model, message}] for the error report."""
    return [
        {"model": f["name"].split(".")[-1], "message": f["message"]}
        for f in failures
    ]


def parse_output_errors(output: str) -> list[dict]:
    """
    Fallback: extract compile errors from dbt text output when run_results.json
    has no entries (e.g. Jinja macro errors that abort before individual nodes run).
    """
    errors = []
    lines = output.splitlines()
    for i, line in enumerate(lines):
        m = _COMPILE_ERROR_RE.search(line)
        if m:
            model = m.group(1).rstrip("(")
            msg_lines = []
            for subsequent in lines[i + 1:]:
                stripped = subsequent.strip()
                if not stripped:
                    break
                if subsequent.startswith(" ") or subsequent.startswith("\t"):
                    msg_lines.append(stripped)
                else:
                    break
            errors.append({"model": model, "message": " ".join(msg_lines)})
    return errors


def summarize_parse_failure(output: str) -> str:
    """One line naming why dbt refused to parse the project, for a commit status.

    A gate that cannot parse the project has to say what broke it: "see job
    logs" leaves the PR reader with a red check and no artifact to look at
    (VD-5918). Returns "" when the output carries no line dbt itself labelled
    as an error, so the caller keeps its own generic message rather than
    inventing a cause — or relaying an arbitrary log line, which the same log's
    `dbt deps` half can make a credential-bearing one.
    """
    lines = [_strip_log_prefix(line) for line in output.splitlines()]
    for i, line in enumerate(lines):
        if not _ERROR_HEADER_RE.match(line):
            continue
        detail = next((subsequent for subsequent in lines[i + 1:] if subsequent), "")
        return _redact(f"{line} — {detail}" if detail else line)
    return ""


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: dbt_error_report.py <report_path> <dbt args...>", file=sys.stderr)
        sys.exit(1)

    report_path = sys.argv[1]
    dbt_args = sys.argv[2:]

    proc = subprocess.run(["dbt"] + dbt_args, capture_output=True, text=True)

    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)

    passed = proc.returncode == 0
    if passed:
        errors = []
    else:
        try:
            # $PROJ is trusted as the resolved dbt project dir here; it is not
            # cross-checked against dbt_args' own --project-dir value. The two
            # agree today only because every ci.yml call site passes
            # --project-dir "$PROJ" literally (VD-4656).
            with open(runner_io.target_path("target/run_results.json")) as f:
                data = json.load(f)
            summary = prr.summarize(data)
            errors = _extract_errors_from_summary(summary["failures"])
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            errors = []
        if not errors:
            errors = parse_output_errors(proc.stdout + proc.stderr)

    pathlib.Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({"passed": passed, "errors": errors}, f, indent=2)

    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
