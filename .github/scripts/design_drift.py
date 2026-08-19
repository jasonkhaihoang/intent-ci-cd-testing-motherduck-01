"""Deep module for ci/design-drift.

Public thin interfaces:
    build_llm_prompt(design_text, manifest, modified_names) -> str
    parse_llm_content(content) -> dict | None
    run_design_drift(design_text, manifest, modified_names, llm_content) -> dict

Pure: no I/O, no LLM call. The shell (design_drift_runner.py) is responsible
for reading design.md, loading the manifest, calling the Claude API, and
threading the response into run_design_drift as `llm_content`.

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


def _iter_balanced_json_objects(text: str):
    """Yield each substring forming a complete balanced {...} span in text,
    in the order they appear. Braces inside JSON string literals (respecting
    \\" escapes) are not counted as structural braces, so a finding's free-text
    detail field containing a literal brace can't corrupt the scan.

    Known limitation: an unescaped/unmatched literal quote in text outside
    any JSON object (e.g. prose quoting an identifier without closing the
    quote) desyncs the in_string flag for the remainder of the scan, since
    it is not scoped per-candidate. Accepted risk — see parse_llm_content.
    """
    depth = 0
    start = None
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    yield text[start:i + 1]
                    start = None


def parse_llm_content(content: str) -> dict | None:
    """Extract the last *successfully-parseable* JSON object found in raw LLM
    content — tolerates markdown code fences, leading prose, and multiple
    JSON-shaped fragments (e.g. an example the model echoes before its real
    answer). Returns None if nothing parses as a JSON object; run_design_drift
    feeds that into _validate_llm_response's existing fail-closed path.

    Known, accepted limitations (VD-4532 fix-direction point 3 explicitly
    accepts this residual risk rather than requiring a full JSON tokenizer):
    this returns the last fragment that *parses*, not necessarily the
    model's actual last-written one — if a complete valid example precedes a
    real answer that gets truncated mid-object, the complete example is
    returned instead of falling closed. See
    test_parse_llm_content_prefers_last_parseable_over_truncated_real_answer
    and test_parse_llm_content_unmatched_quote_in_prose_can_desync_scanning
    for the exact, tested boundaries of this behavior.
    """
    if not isinstance(content, str) or not content.strip():
        return None
    for candidate in reversed(list(_iter_balanced_json_objects(content))):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


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
    kind_enum = ", ".join(sorted(_VALID_KINDS))
    return (
        "You are a CI gate. Compare the design.md below against the dbt manifest fragment "
        "for the state:modified models. Report every drift class you can identify.\n\n"
        "Respond with a single JSON object and nothing else — no prose, no markdown code "
        "fences — of the exact form:\n"
        '{"has_drift": <bool>, "findings": [{"kind": <string>, "model": <string>, '
        '"detail": <string>}, ...]}\n'
        f"Valid values for \"kind\" are exactly: {kind_enum}.\n"
        "If there is no drift, respond with has_drift=false and an empty findings array.\n\n"
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
    llm_content: str,
) -> dict:
    parsed = parse_llm_content(llm_content)
    validated = _validate_llm_response(parsed) if parsed is not None else None
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
