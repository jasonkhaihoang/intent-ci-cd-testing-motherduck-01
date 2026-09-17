"""Gate 2 result assembly — pure function, no I/O.

Converts raw inputs (DB creation outcome, dbt run_results.json content,
head SHA, optional error string) into the result dict consumed by
notify_render.render_gate_2_comment().
"""
from __future__ import annotations


def _map_model(result: dict, manifest_materializations: dict[str, str] | None = None) -> dict:
    node = result.get("node") or {}
    name = node.get("name") or result.get("unique_id", "").split(".")[-1]
    rows_affected = (result.get("adapter_response") or {}).get("rows_affected")
    materialization = (node.get("config") or {}).get("materialized", "")
    if not materialization:
        materialization = (manifest_materializations or {}).get(name, "")
    return {
        "name": name,
        "status": result.get("status", ""),
        "rows": rows_affected if rows_affected is not None else None,
        "materialization": materialization,
    }


def assemble(
    db_created: bool,
    run_results: dict | None,
    head_sha: str,
    error: str | None = None,
    manifest_materializations: dict[str, str] | None = None,
    db_name: str | None = None,
) -> dict:
    """Return the gate-2 result dict for render_gate_2_comment().

    Args:
        db_created: True if CREATE DATABASE pr_<N>_<sha> FROM prd succeeded.
        run_results: Parsed dbt run_results.json content, or None if dbt did not run.
        head_sha: PR head SHA (short or full; passed through to the renderer).
        error: Non-None string for transport/auth failures (renders as session_error).
        manifest_materializations: Optional {model_name: materialization} fallback.
        db_name: Per-PR database name (e.g. pr_42_abc1234), surfaced in the ci/run comment
            as an operator correlation handle. No interactive surface is derived from it:
            the database is reachable by the CI service account alone (AC-93, VD-5012).
    """
    if error is not None:
        result = {
            "overall_status": "error",
            "session_error": error,
            "head_sha": head_sha,
            "clone": {"status": "fail", "models": []},
            "build": {"status": "fail", "models": []},
        }
        # AC-10: a crash after the clone leaves a real database behind holding whatever
        # the run built. That is the case the name exists for, so it is named here too —
        # only a failure before the clone (db_created False) has nothing to name.
        if db_created and db_name:
            result["db_name"] = db_name
        return result

    clone_status = "pass" if db_created else "fail"

    raw_results = (run_results or {}).get("results") or []
    build_models = [_map_model(r, manifest_materializations or {}) for r in raw_results]
    build_failed = any(
        m["status"] not in ("success", "pass") for m in build_models
    )
    build_status = "fail" if build_failed else "pass"

    overall = "pass" if (db_created and not build_failed) else "fail"

    result: dict = {
        "overall_status": overall,
        "head_sha": head_sha,
        "clone": {"status": clone_status, "models": []},
        "build": {"status": build_status, "models": build_models},
    }

    # AC-10: name the per-PR database whenever one was created — including on a failed
    # build, where the database still exists and an operator may need to correlate it to
    # a CI log. No Dive link and no dbt snippet: nothing but the service account can read it.
    if db_created and db_name:
        result["db_name"] = db_name

    return result


def decide_commit_status(result: dict | None) -> tuple[str, str]:
    """Map an assembled gate-2 result to a GitHub commit-status (state, description).

    Fails closed: anything other than a well-formed result with
    overall_status == "pass" reports failure — including a missing/malformed
    result, which happens if the job crashed before assemble() ran. The
    ci/run status must never default to success on silence (VD-3322).
    """
    if isinstance(result, dict) and result.get("overall_status") == "pass":
        return "success", "Gate 2: dbt build passed"
    return "failure", "Gate 2: dbt build failed — see PR comment"
