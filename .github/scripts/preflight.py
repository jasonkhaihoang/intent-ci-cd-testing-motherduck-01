"""Preflight validation: intent-slug + ci-config parse.

CLI:
    preflight.py --branch-name <name> --behind-by <n>
                 --ci-config-path <path> --output <path>
                 --github-output <path>
"""

import argparse
import json
import os
import subprocess
import sys

from ci_config import validate_intent_slug, parse_ci_config, locate_ci_config


_AUTO_MERGE_VIOLATION_MESSAGE = (
    "Per-PR auto-merge is enabled. Disable the auto-merge toggle on this PR — leaving it "
    "on lets GitHub merge ahead of `domain-deploy` (once it ships) and bypasses the deploy lock."
)


def check_auto_merge_disabled(auto_merge_value) -> dict:
    """Return {passed, message} for the auto_merge_disabled preflight check.

    Null, missing (None), or empty dict → disabled → passed.
    Any non-empty object → enabled → failed.
    """
    enabled = bool(auto_merge_value)
    if enabled:
        return {"passed": False, "message": _AUTO_MERGE_VIOLATION_MESSAGE}
    return {"passed": True, "message": "Per-PR auto-merge is disabled."}


def build_preflight_result(
    branch_name: str,
    yaml_str: str,
    behind_by: int = 0,
    auto_merge=None,
    conflict_files: list | None = None,
) -> dict:
    """Build the full preflight result dict.

    ci_config is skipped when intent validation fails.
    conflict_files: list of file paths that conflict with main. When non-empty
                    and behind_by > 0, auto_rebase.status is set to "fail" and
                    overall_status is forced to "fail".
    auto_merge: raw value from pulls/{pr}.auto_merge API field.
                None / missing / {} → disabled (passes).
                Non-empty object → enabled (fails).
    """
    intent_valid, slug = validate_intent_slug(branch_name)

    has_conflicts = bool(conflict_files) and behind_by > 0
    if has_conflicts:
        auto_rebase = {
            "status": "fail",
            "behind_by": behind_by,
            "conflict_files": conflict_files,
            "message": (
                f"Branch is {behind_by} commit(s) behind main with "
                f"{len(conflict_files)} conflict(s) — resolve before merging."
            ),
        }
    else:
        auto_rebase = {
            "status": "ok" if behind_by == 0 else "behind",
            "behind_by": behind_by,
            "message": (
                "Branch is up-to-date with main."
                if behind_by == 0
                else f"Branch is {behind_by} commit(s) behind main — rebase manually before merge."
            ),
        }

    intent = {
        "status": "pass" if intent_valid else "fail",
        "slug": slug,
        "message": (
            f"Valid intent slug: `{slug}`"
            if intent_valid
            else (
                f"Invalid branch name: `{branch_name}` — must match "
                r"`intent/<slug>` where `<slug>` matches `[a-z0-9][a-z0-9\-]+`"
            )
        ),
    }

    auto_merge_check = check_auto_merge_disabled(auto_merge)

    if not intent_valid:
        return {
            "overall_status": "fail",
            "auto_rebase": auto_rebase,
            "intent": intent,
            "ci_config": {
                "status": "skipped",
                "message": "intent validation failed",
                "line_number": None,
                "missing_keys": [],
            },
            "auto_merge_disabled": auto_merge_check,
        }

    ci_raw = parse_ci_config(yaml_str)
    ci_config = {
        "status": "pass" if ci_raw["ok"] else "fail",
        "message": ci_raw["error"] or "Parsed successfully.",
        "line_number": ci_raw["line_number"],
        "missing_keys": ci_raw["missing_keys"],
    }

    overall_status = "pass" if (ci_raw["ok"] and auto_merge_check["passed"] and not has_conflicts) else "fail"

    return {
        "overall_status": overall_status,
        "auto_rebase": auto_rebase,
        "intent": intent,
        "ci_config": ci_config,
        "auto_merge_disabled": auto_merge_check,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight validation for domain CI.")
    parser.add_argument("--branch-name", required=True)
    parser.add_argument("--behind-by", type=int, default=0)
    parser.add_argument("--conflict-files", default="")
    parser.add_argument("--ci-config-path", default="ci-config.yml")
    parser.add_argument("--output", default="reports/preflight.json")
    parser.add_argument("--github-output", default="")
    args = parser.parse_args()

    config_path = args.ci_config_path
    if not os.path.isfile(config_path):
        config_path = locate_ci_config()

    yaml_str = ""
    try:
        with open(config_path) as f:
            yaml_str = f.read()
    except FileNotFoundError:
        pass

    # Fetch per-PR auto_merge field (read-only, uses existing GITHUB_TOKEN)
    auto_merge = None
    pr_number = os.environ.get("PR_NUMBER", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if pr_number and repo:
        try:
            raw = subprocess.check_output(
                ["gh", "api", f"repos/{repo}/pulls/{pr_number}", "--jq", ".auto_merge"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=10,
            ).strip()
            # gh --jq returns "null" string for JSON null, or a JSON object string
            if raw and raw != "null":
                auto_merge = json.loads(raw)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, OSError):
            pass

    conflict_files = [f for f in args.conflict_files.split(",") if f.strip()] if args.conflict_files else []
    result = build_preflight_result(
        args.branch_name, yaml_str, args.behind_by,
        auto_merge=auto_merge, conflict_files=conflict_files,
    )

    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)

    if result["overall_status"] == "pass" and args.github_output:
        ci_raw = parse_ci_config(yaml_str)
        with open(args.github_output, "a") as out:
            for k, v in ci_raw["config"].items():
                out.write(f"{k}={v}\n")
            slug = result["intent"]["slug"]
            out.write(f"intent_slug={slug}\n")
        print(f"Config outputs written. intent_slug={slug}")

    if result["overall_status"] != "pass":
        am_enabled = not result["auto_merge_disabled"]["passed"]
        print(f"Preflight failed: intent={result['intent']['status']}, ci_config={result['ci_config']['status']}, auto_merge_enabled={am_enabled}")
        sys.exit(1)

    print("Preflight passed.")


if __name__ == "__main__":
    main()
