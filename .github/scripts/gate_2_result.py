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


def _build_local_dbt_snippet(db_name: str, model_names: list[str]) -> str:
    """Pure: render a copy-paste dbt snippet pointing at the per-PR MotherDuck database."""
    parts = db_name.split("_", 2)  # pr_42_abc1234 → ["pr", "42", "abc1234"]
    pr_num = parts[1] if len(parts) > 1 else ""
    sha = parts[2] if len(parts) > 2 else ""
    select = " ".join(model_names)
    return (
        f"# Run dbt locally against {db_name}\n"
        f"# Requires MOTHERDUCK_TOKEN in your environment\n"
        f"export PR_NUMBER={pr_num}\n"
        f"export HEAD_SHA_SHORT={sha}\n"
        f"dbt run --select {select} \\\n"
        f"  --profiles-dir .github/profiles --profile dbt_motherduck_ci"
    )


def assemble(
    db_created: bool,
    run_results: dict | None,
    head_sha: str,
    error: str | None = None,
    manifest_materializations: dict[str, str] | None = None,
    dive_url: str | None = None,
    db_name: str | None = None,
    share_creation_failed: bool = False,
) -> dict:
    """Return the gate-2 result dict for render_gate_2_comment().

    Args:
        db_created: True if CREATE DATABASE pr_<N>_<sha> FROM prd succeeded.
        run_results: Parsed dbt run_results.json content, or None if dbt did not run.
        head_sha: PR head SHA (short or full; passed through to the renderer).
        error: Non-None string for transport/auth failures (renders as session_error).
        manifest_materializations: Optional {model_name: materialization} fallback.
        dive_url: MotherDuck Dive URL from MD_CREATE_DIVE SQL (shell-supplied, I/O done).
        db_name: Per-PR database name (e.g. pr_42_abc1234) used to build local_dbt_snippet.
        share_creation_failed: True if the CREATE SHARE call (VD-3321) failed after the
            Dive was created — surfaced as a non-blocking warning (VD-3330), never as a
            gate failure.
    """
    if error is not None:
        return {
            "overall_status": "error",
            "session_error": error,
            "head_sha": head_sha,
            "clone": {"status": "fail", "models": []},
            "build": {"status": "fail", "models": []},
        }

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

    # AC-10: include developer surfaces only when the DB was created and models were built
    if db_created and build_models:
        if dive_url is not None:
            result["dive_url"] = dive_url
            # VD-3330: surface a non-blocking warning when the per-PR database's
            # read-only share (VD-3321) failed to create — never affects
            # overall_status. Gated on dive_url (not just db_created/build_models)
            # so this key never appears without the Dive link it qualifies.
            if share_creation_failed:
                result["share_creation_failed"] = True
        model_names = [m["name"] for m in build_models]
        result["local_dbt_snippet"] = (
            _build_local_dbt_snippet(db_name, model_names) if db_name else None
        )

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
