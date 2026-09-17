"""Validate a domain repository's .workflow/ci-config.yml, standalone.

The same parse `ci/preflight` runs, without preflight's branch-slug, behind-by
and auto-merge checks and without a $GITHUB_OUTPUT write — so an authoring
skill can check the file it just rendered before committing it, and get the
same verdict CI will later reach.

Run it from the bundle, not from a repository copy: it imports its siblings
flatly, so `$VD_CI_BUNDLE_DIR/shared/scripts/validate_ci_config.py` resolves
`ci_config` while a lone copy elsewhere does not.

CLI:
    validate_ci_config.py [--path .workflow/ci-config.yml] [--json]

Exit 0 = valid. Exit 1 = invalid (parse error, or a required key absent or
empty). Exit 2 = the file does not exist.
"""

from __future__ import annotations

import argparse
import json
import sys

from ci_config import locate_ci_config, parse_ci_config


def _render_human(path: str, result: dict) -> str:
    if result["ok"]:
        platform = result["config"].get("platform", "(unset)")
        return f"{path}: valid (platform: {platform})"

    lines = [f"{path}: INVALID"]
    if result.get("error"):
        where = f" (line {result['line_number']})" if result.get("line_number") else ""
        lines.append(f"  {result['error']}{where}")
    for key in result.get("missing_keys", []):
        lines.append(f"  - {key}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a domain repo's ci-config.yml.")
    parser.add_argument(
        "--path",
        default=None,
        help="path to ci-config.yml (default: the conventional .workflow/ci-config.yml)",
    )
    parser.add_argument("--json", action="store_true", help="emit the raw parse result as JSON")
    args = parser.parse_args(argv)

    path = args.path or locate_ci_config()

    try:
        with open(path, encoding="utf-8") as handle:
            yaml_str = handle.read()
    except FileNotFoundError:
        message = f"{path}: not found"
        if args.json:
            print(json.dumps({"ok": False, "error": message, "missing_keys": []}))
        else:
            print(message, file=sys.stderr)
        return 2

    result = parse_ci_config(yaml_str)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
    else:
        stream = sys.stdout if result["ok"] else sys.stderr
        print(_render_human(path, result), file=stream)

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
