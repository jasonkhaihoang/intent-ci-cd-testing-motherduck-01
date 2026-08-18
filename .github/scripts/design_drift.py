"""Deep module for ci/design-drift.

Public thin interfaces:
    build_llm_prompt(design_text, manifest, modified_names) -> str
    run_design_drift(design_text, manifest, modified_names, llm_response) -> dict

Pure: no I/O, no LLM call. The shell (design_drift_runner.py) is responsible
for reading design.md, loading the manifest, calling the Claude API, and
threading the response into run_design_drift as `llm_response`.

Returns:
    {"has_drift": bool, "findings": [{"kind": str, "model": str, "detail": str}, ...]}

Finding kinds:
    missing_model, extra_model, grain_mismatch, materialization_mismatch,
    unique_key_mismatch, unexpected_column, missing_column,
    malformed_llm_response.

Malformed LLM responses produce a deterministic single-finding result of
kind="malformed_llm_response" — the function never raises.
"""
from __future__ import annotations

import json

_VALID_KINDS = {
    "missing_model",
    "extra_model",
    "grain_mismatch",
    "materialization_mismatch",
    "unique_key_mismatch",
    "unexpected_column",
    "missing_column",
}


def _compact_node(node: dict) -> dict:
    # Column names only (no metadata) — deliberately strips description, data_type, etc.
    # to keep prompt small. Present/absent is all the LLM needs for column-level drift.
    config = node.get("config", {})
    result = {"columns": sorted(node.get("columns", {}).keys())}
    if mat := config.get("materialized"):
        result["materialization"] = mat
    if uk := config.get("unique_key"):
        result["unique_key"] = uk
    return result


def build_llm_prompt(design_text: str, manifest: dict, modified_names: list[str]) -> str:
    modified_set = set(modified_names)
    compact = {
        v.get("name", k): _compact_node(v)
        for k, v in manifest.get("nodes", {}).items()
        if v.get("name") in modified_set
    }
    return (
        "You are a CI gate. Compare the design.md below against the dbt manifest fragment "
        "for the state:modified models. Report every drift class you can identify by "
        "calling the report_design_drift tool exactly once. If there is no drift, call it "
        "with has_drift=false and an empty findings array.\n\n"
        f"=== design.md ===\n{design_text}\n\n"
        f"=== state:modified ===\n{json.dumps(sorted(modified_set))}\n\n"
        f"=== manifest (modified nodes only) ===\n{json.dumps(compact, indent=2)}\n"
    )


def _validate_llm_response(llm_response: dict) -> dict | None:
    """Returns the validated response, or None if malformed."""
    if not isinstance(llm_response, dict):
        return None
    if "has_drift" not in llm_response or "findings" not in llm_response:
        return None
    if not isinstance(llm_response["has_drift"], bool):
        return None
    if not isinstance(llm_response["findings"], list):
        return None
    for f in llm_response["findings"]:
        if not isinstance(f, dict):
            return None
        if not {"kind", "model", "detail"} <= f.keys():
            return None
        if f["kind"] not in _VALID_KINDS:
            return None
    return llm_response


def run_design_drift(
    design_text: str,
    manifest: dict,
    modified_names: list[str],
    llm_response: dict,
) -> dict:
    validated = _validate_llm_response(llm_response)
    if validated is None:
        return {
            "has_drift": True,
            "findings": [{
                "kind": "malformed_llm_response",
                "model": "",
                "detail": "LLM response did not conform to the required schema.",
            }],
        }
    return {
        "has_drift": validated["has_drift"],
        "findings": list(validated["findings"]),
    }
