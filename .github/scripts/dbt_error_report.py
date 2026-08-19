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

# Matches: "Compilation Error in model my_model (path/to/model.sql)"
# Also handles dbt log-prefixed lines like "16:04:22  Compilation Error in model …"
_COMPILE_ERROR_RE = re.compile(r"Compilation Error in model (\S+)")


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
            with open("target/run_results.json") as f:
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
