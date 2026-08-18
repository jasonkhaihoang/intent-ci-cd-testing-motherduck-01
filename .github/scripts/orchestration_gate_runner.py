"""Thin shell for ci/orchestration (platform-neutral Schedule design contract).

gather → call → dispatch:
  1. Read {intent_id}/design.md; parse the optional ## Schedule section (C1).
  2. Read dbt model names from manifest.json (project-owned models).
  3. Read dlt pipeline names from ingestion/pipelines/*.py.
  4. Call run_orchestration_gate (pure).
  5. Post ci/orchestration status; upsert <!-- ci-orchestration --> comment.
  6. sys.exit(1) iff any critical finding (or gather error).

All gate logic lives in orchestration_gate.run_orchestration_gate; this module
owns only I/O.

Usage:
    orchestration_gate_runner.py \\
        --pr-number 42 --head-sha abc123 --intent-id intent/sales \\
        --manifest "$PROJ/target/manifest.json"

Environment:
    GITHUB_REPOSITORY, GH_TOKEN, GITHUB_RUN_ID, GITHUB_SERVER_URL  (status post)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import emit_status
import notify_render
import pr_comment

from design_contract import parse_design_sections
from dbt_manifest import Manifest
from orchestration_gate import run_orchestration_gate

CONTEXT = "ci/orchestration"


def _read_text(path: str) -> str:
    with open(path) as f:
        return f.read()


def _dbt_model_names(manifest: dict) -> set[str]:
    return {node["name"] for node in Manifest.from_dict(manifest).own_models().values()}


def _dlt_pipeline_names(root: str = "ingestion/pipelines") -> set[str]:
    return {
        os.path.splitext(os.path.basename(path))[0]
        for path in glob.glob(os.path.join(root, "*.py"))
        if not os.path.basename(path).startswith("__")
    }


def _run_url() -> str:
    base = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    return f"{base}/{repo}/actions/runs/{run_id}"


def _post(head_sha: str, state: str, description: str) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    emit_status.emit_status(repo, head_sha, CONTEXT, state, description, _run_url())


def _post_pr_comment(pr_number: str, result: dict | None) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        return
    body = notify_render.render_contract_gate_comment(
        notify_render.ORCHESTRATION_MARKER, "Orchestration", CONTEXT, result
    )
    try:
        pr_comment.upsert(notify_render.ORCHESTRATION_MARKER, body, pr_number, repo)
    except BaseException as e:
        print(f"Failed to post PR comment: {e}", flush=True)


def _summary(result: dict) -> str:
    if result.get("skipped"):
        return "no ## Schedule section — skipped"
    critical = [f for f in result["findings"] if f["severity"] == "critical"]
    if not critical:
        return "schedule design contract satisfied"
    rules = sorted({f["rule"] for f in critical})
    return f"schedule contract violations: {', '.join(rules)}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr-number", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--intent-id", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)

    try:
        design_text = _read_text(f"{args.intent_id}/design.md")
        manifest = json.loads(_read_text(args.manifest))
        schedule = parse_design_sections(design_text)["schedule"]
        dbt_model_names = _dbt_model_names(manifest)
        dlt_pipeline_names = _dlt_pipeline_names()
    except Exception as e:  # gather failure → emit failure status, exit 1
        _post(args.head_sha, "failure", f"orchestration error: {type(e).__name__}: {e}")
        _post_pr_comment(args.pr_number, result=None)
        return 1

    result = run_orchestration_gate(schedule, dbt_model_names, dlt_pipeline_names)
    has_critical = any(f["severity"] == "critical" for f in result["findings"])
    _post(args.head_sha, "failure" if has_critical else "success", _summary(result))
    _post_pr_comment(args.pr_number, result=result)
    return 1 if has_critical else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
