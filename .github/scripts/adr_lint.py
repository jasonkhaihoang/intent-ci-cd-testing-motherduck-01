"""ADR numbering check: duplicate-number and dangling-cross-reference detection.

CLI:
    adr_lint.py

See docs/functional/domain-pr-review-approval/README.md (AC-66..AC-73) and
docs/design/domain-pr-review-approval/adr-numbering/README.md for the full contract.
"""

import glob
import os
import re
import sys


_ADR_FILENAME_RE = re.compile(r"^(\d{4})-.*\.md$")
_ADR_CITATION_RE = re.compile(r"\bADR[- ](\d{4})(?!\w)", re.IGNORECASE)


def find_duplicate_adr_numbers(filenames: list) -> dict:
    """Map each ADR number claimed by 2+ filenames to the list of colliding filenames.

    filenames not matching `NNNN-slug.md` are ignored. Returns {} when there are no
    collisions. AC-66, AC-67, AC-71.
    """
    by_number = {}
    for filename in filenames:
        match = _ADR_FILENAME_RE.match(filename)
        if not match:
            continue
        by_number.setdefault(match.group(1), []).append(filename)
    return {number: files for number, files in by_number.items() if len(files) > 1}


def find_dangling_adr_references(known_numbers: set, files: list) -> list:
    """Scan (path, contents) pairs for ADR-00NN / ADR 00NN citations not in known_numbers.

    Returns a list of {file, line, number} for every citation whose number has no
    corresponding file. AC-68, AC-69, AC-71.
    """
    findings = []
    for path, contents in files:
        for line_number, line in enumerate(contents.splitlines(), start=1):
            for match in _ADR_CITATION_RE.finditer(line):
                number = match.group(1)
                if number not in known_numbers:
                    findings.append({"file": path, "line": line_number, "number": number})
    return findings


def _read_docs_tree() -> list:
    files = []
    for path in sorted(glob.glob("docs/**/*.md", recursive=True)):
        with open(path, encoding="utf-8", errors="replace") as f:
            files.append((path, f.read()))
    return files


def main() -> int:
    adr_dir = "docs/adr"
    adr_filenames = sorted(os.path.basename(p) for p in glob.glob(os.path.join(adr_dir, "*.md")))
    if not adr_filenames:
        print("No ADR files found under docs/adr/ — nothing to check.")
        return 0

    duplicates = find_duplicate_adr_numbers(adr_filenames)
    known_numbers = {
        match.group(1) for match in (_ADR_FILENAME_RE.match(f) for f in adr_filenames) if match
    }
    dangling = find_dangling_adr_references(known_numbers, _read_docs_tree())

    if not duplicates and not dangling:
        print("ADR numbering check passed: no duplicate numbers, no dangling references.")
        return 0

    if duplicates:
        print("Duplicate ADR numbers found:")
        for number, files in sorted(duplicates.items()):
            print(f"  ADR number {number} is claimed by: {', '.join(sorted(files))}")

    if dangling:
        print("Dangling ADR cross-references found:")
        for finding in dangling:
            print(f"  {finding['file']}:{finding['line']} cites ADR-{finding['number']}, which has no matching file")

    return 1


if __name__ == "__main__":
    sys.exit(main())
