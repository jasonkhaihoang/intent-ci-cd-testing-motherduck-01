"""Thin shell for ci/semantic-model (static MetricFlow design-contract gate).

gather → call → dispatch:
  1. Read {intent_id}/design.md; parse the optional ## Semantic Model section (C1).
  2. Read the parsed dbt manifest (semantic_models + metrics).
  3. Call run_semantic_model_gate (pure).
  4. Post ci/semantic-model status; upsert <!-- ci-semantic-model --> comment.
  5. sys.exit(1) iff any critical finding (or gather error).

All gate logic lives in semantic_model_gate.run_semantic_model_gate; this module owns only I/O.
No `mf query` runtime check — static manifest validation only (AC-43 deferred).

Usage:
    semantic_model_gate_runner.py \\
        --pr-number 42 --head-sha abc123 --intent-id intent/sales \\
        --manifest "$PROJ/target/manifest.json"

Environment:
    GITHUB_REPOSITORY, GH_TOKEN, GITHUB_RUN_ID, GITHUB_SERVER_URL  (status post)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import emit_status
import notify_render
import pr_comment

from design_contract import parse_design_sections
from semantic_model_gate import run_semantic_model_gate

CONTEXT = "ci/semantic-model"


def _read_text(path: str) -> str:
    with open(path) as f:
        return f.read()


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
        notify_render.SEMANTIC_MODEL_MARKER, "Semantic Model", CONTEXT, result
    )
    try:
        pr_comment.upsert(notify_render.SEMANTIC_MODEL_MARKER, body, pr_number, repo)
    except BaseException as e:
        print(f"Failed to post PR comment: {e}", flush=True)


def _summary(result: dict) -> str:
    if result.get("skipped"):
        return "no semantic-model objects or ## Semantic Model section — skipped"
    critical = [f for f in result["findings"] if f["severity"] == "critical"]
    if not critical:
        return "semantic-model design contract satisfied"
    rules = sorted({f["rule"] for f in critical})
    return f"semantic-model contract violations: {', '.join(rules)}"


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
        design_metrics = parse_design_sections(design_text)["metrics"]
    except Exception as e:  # gather failure → emit failure status, exit 1
        _post(args.head_sha, "failure", f"semantic-model error: {type(e).__name__}: {e}")
        _post_pr_comment(args.pr_number, result=None)
        return 1

    result = run_semantic_model_gate(manifest, design_metrics)
    has_critical = any(f["severity"] == "critical" for f in result["findings"])
    _post(args.head_sha, "failure" if has_critical else "success", _summary(result))
    _post_pr_comment(args.pr_number, result=result)
    return 1 if has_critical else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
