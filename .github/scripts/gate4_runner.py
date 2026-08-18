"""Thin shell for Gate 4 (`ci/data-tests`) on MotherDuck.

Orchestrates: env read → dbt subprocess → run_results.json parse → GitHub status post.
All gate logic (pass/fail/error derivation, store-failures-config rule) lives in the
shared thin interface `parse_run_results.py`; this module owns only I/O.

Usage:
    gate4_runner.py run-gate \
        --pr-number 42 \
        --head-sha abc123def456 \
        --head-sha-short abc1234 \
        --deployment-manifest reports/deployment-manifest-abc123def456.json \
        --dbt-project dbt_project.yml \
        --profiles-dir .github/profiles \
        --run-results target/run_results.json \
        --output reports/gate-4.json

Environment:
    GITHUB_REPOSITORY, GH_TOKEN, GITHUB_RUN_ID, GITHUB_SERVER_URL  (commit-status post)
    MOTHERDUCK_TOKEN                                                 (injected by workflow)
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

try:
    import yaml
except ImportError:
    yaml = None

import emit_status
from parse_run_results import check_store_failures_config, enrich_tests_from_manifest, parse_data_test_results

CONTEXT = "ci/data-tests"
PROFILE = "dbt_motherduck_ci"
TARGET = "ci"


def _run_url() -> str:
    base = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    return f"{base}/{repo}/actions/runs/{run_id}"


def _post(head_sha: str, state: str, description: str) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        return
    emit_status.emit_status(repo, head_sha, CONTEXT, state, description, _run_url())


def _load_manifest_nodes(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f).get("nodes", {})
    except (OSError, json.JSONDecodeError):
        return {}


def _load_dbt_project(path: str) -> dict:
    if yaml is None:
        return {}
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except OSError:
        return {}


def _select_names(deployment_manifest_path: str) -> list[str]:
    try:
        with open(deployment_manifest_path) as f:
            dm = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    names = []
    for a in dm.get("artifacts") or []:
        full = a.get("name", "")
        names.append(full.split(".")[-1] if "." in full else full)
    return [n for n in names if n]


def cmd_run_gate(args) -> int:
    # Pre-flight: store-failures config (advisory only — never blocks the gate).
    dbt_project = _load_dbt_project(args.dbt_project)
    store_failures_config_ok = check_store_failures_config(dbt_project)
    if not store_failures_config_ok:
        print(
            "Advisory: dbt_project.yml is missing 'tests: +store_failures: true' and/or "
            "'+store_failures_as: table'. Failure drill-down tables will not be available. "
            "Gate signal is unaffected.",
            flush=True,
        )

    _post(args.head_sha, "pending", "Gate 4: dbt test --store-failures running")

    env = {
        **os.environ,
        "PR_NUMBER": str(args.pr_number),
        "HEAD_SHA_SHORT": args.head_sha_short,
    }

    subprocess.run(
        ["dbt", "deps", "--profiles-dir", args.profiles_dir, "--profile", PROFILE, "--quiet"],
        env=env,
        capture_output=True,
        text=True,
    )

    cmd = [
        "dbt", "test",
        "--store-failures",
        "--profiles-dir", args.profiles_dir,
        "--profile", PROFILE,
        "--target", TARGET,
        "--exclude", "test_type:unit",
    ]
    names = _select_names(args.deployment_manifest)
    if names:
        cmd.extend(["--select", " ".join(names)])

    subprocess.run(cmd, env=env, capture_output=True, text=True)
    # We intentionally do not exit on dbt's non-zero return code: run_results.json is
    # the authoritative signal, and parse_data_test_results distinguishes fail vs error.

    try:
        with open(args.run_results) as f:
            run_results = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        _post(args.head_sha, "failure", f"Gate 4: run_results.json missing or malformed ({e})")
        print(f"Gate 4 error: {e}", file=sys.stderr)
        return 1

    summary = parse_data_test_results(run_results)
    manifest_nodes = _load_manifest_nodes(args.manifest)
    summary["tests"] = enrich_tests_from_manifest(summary["tests"], manifest_nodes)
    summary["store_failures_config_ok"] = store_failures_config_ok

    overall = summary["overall_status"]
    gh_state = "success" if overall == "pass" else "failure"
    counts = summary["counts"]
    description = (
        f"Gate 4: {overall} — "
        f"{counts['pass']} passed / {counts['fail']} failed / "
        f"{counts['error']} errored / {counts['skip']} skipped"
    )
    _post(args.head_sha, gh_state, description)

    if args.output:
        pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(summary, f, indent=2)

    print(
        f"Gate 4 result: {overall} ({summary['total']} test(s)) → GitHub status: {gh_state}",
        flush=True,
    )
    return 0 if gh_state == "success" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate 4 (ci/data-tests) — MotherDuck")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run-gate")
    p.add_argument("--pr-number", required=True, type=int)
    p.add_argument("--head-sha", required=True)
    p.add_argument("--head-sha-short", required=True)
    p.add_argument("--deployment-manifest", required=True)
    p.add_argument("--dbt-project", default="dbt_project.yml")
    p.add_argument("--profiles-dir", default=".github/profiles")
    p.add_argument("--run-results", default="target/run_results.json")
    p.add_argument("--manifest", default="target/manifest.json")
    p.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    return {"run-gate": cmd_run_gate}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
