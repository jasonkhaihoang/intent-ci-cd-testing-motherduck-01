"""Thin shell for ci/design-drift (MotherDuck).

gather → call → dispatch:
  1. Read design.md, manifest.json, modified.json from disk.
  2. Read LLM_API_KEY, LLM_API_URL, LLM_MODEL from env.
  3. Build prompt; POST to OpenAI-compatible chat completions API; receive
     structured JSON via tool-use.
  4. Call run_design_drift (pure).
  5. Post ci/design-drift status; sys.exit(1) on drift or error.

All gate logic lives in design_drift.run_design_drift; this module owns only I/O.

Usage:
    design_drift_runner.py \\
        --pr-number 42 --head-sha abc123 --intent-id intent/sales \\
        --manifest target/manifest.json \\
        --modified reports/modified.json

Environment:
    GITHUB_REPOSITORY, GH_TOKEN, GITHUB_RUN_ID, GITHUB_SERVER_URL  (status post)
    LLM_API_KEY                                                      (injected by workflow)
    LLM_API_URL   base URL for OpenAI-compatible provider            (default: https://api.openai.com)
    LLM_MODEL     model identifier                                   (default: gpt-4o)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

import emit_status
import notify_render
import pr_comment

from design_drift import build_llm_prompt, run_design_drift

CONTEXT = "ci/design-drift"
DEFAULT_LLM_API_URL = "https://api.openai.com"
DEFAULT_LLM_MODEL = "gpt-4o"
MAX_OUTPUT_TOKENS = 4096

_DRIFT_TOOL = {
    "type": "function",
    "function": {
        "name": "report_design_drift",
        "description": "Return drift findings comparing design.md against the modified dbt models.",
        "parameters": {
            "type": "object",
            "required": ["has_drift", "findings"],
            "properties": {
                "has_drift": {"type": "boolean"},
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["kind", "model", "detail"],
                        "properties": {
                            "kind": {
                                "type": "string",
                                "enum": [
                                    "missing_model", "extra_model",
                                    "grain_mismatch", "materialization_mismatch",
                                    "unique_key_mismatch",
                                    "unexpected_column", "missing_column",
                                ],
                            },
                            "model": {"type": "string"},
                            "detail": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}


def _read_text(path: str) -> str:
    with open(path) as f:
        return f.read()


def _design_md_path(intent_id: str) -> str:
    return f"{intent_id}/design.md"


def build_llm_url(api_url: str) -> str:
    """AC-66: build the chat-completions URL for any LLM_API_URL base-URL shape."""
    base = api_url.rstrip("/")
    if base.endswith("/v1/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def call_llm(api_key: str, prompt: str, api_url: str, model: str) -> dict:
    url = build_llm_url(api_url)
    body = json.dumps({
        "model": model,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "temperature": 0,
        "tools": [_DRIFT_TOOL],
        "tool_choice": {"type": "function", "function": {"name": "report_design_drift"}},
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("content-type", "application/json")
    req.add_header("User-Agent", "python-httpx/0.27.0")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"LLM API HTTP {e.code}: {e.read().decode(errors='replace')}") from e
    try:
        tool_call = payload["choices"][0]["message"]["tool_calls"][0]
        arguments = tool_call["function"]["arguments"]
        return arguments if isinstance(arguments, dict) else json.loads(arguments)
    except (KeyError, IndexError, json.JSONDecodeError, TypeError) as e:
        raise RuntimeError(
            f"LLM response did not include a report_design_drift tool call: {payload}"
        ) from e


def _run_url() -> str:
    base = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    return f"{base}/{repo}/actions/runs/{run_id}"


def _post(head_sha: str, state: str, description: str) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    emit_status.emit_status(repo, head_sha, CONTEXT, state, description, _run_url())


def _post_pr_comment(pr_number: str, result: dict | None, modified_names: list[str] | None = None) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        return
    body = notify_render.render_design_drift_comment(result, modified_names)
    try:
        pr_comment.upsert(notify_render.DESIGN_DRIFT_MARKER, body, pr_number, repo)
    except BaseException as e:
        print(f"Failed to post PR comment: {e}", flush=True)


def _summary(result: dict) -> str:
    if not result["has_drift"]:
        return "design.md matches state:modified — no drift"
    kinds = sorted({f["kind"] for f in result["findings"]})
    return f"design drift detected: {', '.join(kinds)}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr-number", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--intent-id", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--modified", required=True)
    args = parser.parse_args(argv)

    try:
        design_text = _read_text(_design_md_path(args.intent_id))
        manifest = json.loads(_read_text(args.manifest))
        modified_names = json.loads(_read_text(args.modified))
        api_key = os.environ["LLM_API_KEY"]
        api_url = os.environ.get("LLM_API_URL") or DEFAULT_LLM_API_URL
        model = os.environ.get("LLM_MODEL") or DEFAULT_LLM_MODEL
        prompt = build_llm_prompt(design_text, manifest, modified_names)
        llm_response = call_llm(api_key, prompt, api_url, model)
    except Exception as e:  # gather/call failure → emit failure status, exit 1
        _post(args.head_sha, "failure", f"design-drift error: {type(e).__name__}: {e}")
        _post_pr_comment(args.pr_number, result=None)
        return 1

    result = run_design_drift(design_text, manifest, modified_names, llm_response)
    _post(args.head_sha, "failure" if result["has_drift"] else "success", _summary(result))
    _post_pr_comment(args.pr_number, result=result, modified_names=modified_names)
    return 1 if result["has_drift"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
