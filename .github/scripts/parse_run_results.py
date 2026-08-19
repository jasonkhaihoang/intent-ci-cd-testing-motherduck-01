"""Parse dbt `run_results.json` into a gate summary.

Shared by Gate 3 (unit tests) and Gate 4 (data tests).

Thin interfaces (see CONTEXT.md#architecture-vocabulary):
    summarize               — normalise raw run_results dict into a summary dict
    parse_run_results       — read a run_results.json file and return a summary dict
    check_store_failures_config — inspect a parsed dbt_project.yml dict for store-failures config
    gate_4_overall_status   — derive three-state overall status from a list of test result dicts
    parse_data_test_results — Gate 4 variant of summarize with three-state overall_status

Output schema written to --output:
    {
      "overall_status": "pass" | "fail",
      "total": int,
      "counts": {"pass": int, "fail": int, "error": int, "skip": int},
      "failures": [{"name": str, "status": str, "message": str}],  # capped at 10
      "truncated": bool,
      "tests": [{"name": str, "model": str, "status": str}]  # one entry per test
    }

Exit codes:
    0 — overall_status == "pass" (includes empty results)
    1 — overall_status == "fail"
    2 — input file missing or unreadable / malformed JSON
"""
from __future__ import annotations

import argparse
import json
import sys

import runner_io

__all__ = [
    "summarize",
    "parse_run_results",
    "check_store_failures_config",
    "gate_4_overall_status",
    "parse_data_test_results",
    "enrich_tests_from_manifest",
]

_FAILURE_CAP = 10


def _extract_model(unique_id: str) -> str:
    """Extract model name from a dbt unit_test unique_id.

    unit_test.<project>.<model>__<test_name> → <model>.
    Returns "" for unique_ids that don't contain "__".
    """
    last = unique_id.split(".")[-1]
    if "__" not in last:
        return ""
    return last.split("__")[0]


def summarize(run_results: dict) -> dict:
    counts = {"pass": 0, "fail": 0, "error": 0, "skip": 0}
    failures: list[dict] = []
    tests: list[dict] = []

    results = run_results.get("results") or []
    for r in results:
        unique_id = r.get("unique_id", "")
        if unique_id.startswith("operation."):
            continue
        status = r.get("status")

        if status in ("pass", "success"):
            norm = "pass"
            counts["pass"] += 1
        elif status == "fail":
            norm = "fail"
            counts["fail"] += 1
            failures.append({"name": unique_id, "status": "fail", "message": r.get("message") or ""})
        elif status == "skip":
            norm = "skip"
            counts["skip"] += 1
        else:
            norm = "error"
            counts["error"] += 1
            failures.append({"name": unique_id, "status": "error", "message": r.get("message") or ""})

        tests.append({"name": unique_id, "model": _extract_model(unique_id), "status": norm})

    truncated = len(failures) > _FAILURE_CAP
    overall = "fail" if (counts["fail"] or counts["error"]) else "pass"

    return {
        "overall_status": overall,
        "total": len(tests),
        "counts": counts,
        "failures": failures[:_FAILURE_CAP],
        "truncated": truncated,
        "tests": tests,
    }


def check_store_failures_config(dbt_project: dict | None) -> bool:
    """Return True if a parsed dbt_project.yml dict enables `tests: +store_failures: true`
    and `+store_failures_as: table`. Missing/invalid input → False.

    Fabric Gate 4 previously read the YAML file path; the shared interface accepts the
    parsed dict so the shell owns YAML I/O.
    """
    if not isinstance(dbt_project, dict):
        return False
    tests = dbt_project.get("tests")
    if not isinstance(tests, dict):
        return False
    return bool(tests.get("+store_failures")) and tests.get("+store_failures_as") == "table"


def gate_4_overall_status(tests: list) -> str:
    """Derive overall status from a list of test result dicts.

    Precedence: any error → 'error'; any fail → 'fail'; else 'pass' (skips and empty pass).
    """
    has_error = any(t.get("status") == "error" for t in tests)
    if has_error:
        return "error"
    has_fail = any(t.get("status") == "fail" for t in tests)
    return "fail" if has_fail else "pass"


def enrich_tests_from_manifest(tests: list, nodes: dict) -> list:
    """Fill blank model names in a tests list using manifest.json node entries.

    Each node entry that has an `attached_node` field (e.g. `model.<proj>.<name>`)
    provides the parent model name for the matching test unique_id. Only blank model
    fields are updated; already-populated entries (unit tests via __) are left unchanged.
    """
    lookup = {
        uid: v.get("attached_node", "").split(".")[-1]
        for uid, v in nodes.items()
        if isinstance(v, dict) and v.get("attached_node")
    }
    return [
        {**t, "model": t["model"] or lookup.get(t["name"], "")}
        for t in tests
    ]


def parse_data_test_results(run_results: dict) -> dict:
    """Parse dbt `run_results.json` for Gate 4 (`dbt test --store-failures`).

    Same shape as `summarize`, but overall_status is three-state: error precedes fail.
    """
    summary = summarize(run_results)
    summary["overall_status"] = gate_4_overall_status(summary["tests"])
    return summary


def parse_run_results(path: str) -> dict:
    with open(path) as f:
        data = json.load(f)
    return summarize(data)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Parse dbt run_results.json into gate summary.")
    p.add_argument("--input", required=True, help="Path to dbt run_results.json")
    p.add_argument("--output", required=True, help="Path to write gate summary JSON")
    args = p.parse_args(argv)

    try:
        summary = parse_run_results(args.input)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        runner_io.error(f"parse_run_results: {e}")
        return 2

    with open(args.output, "w") as f:
        json.dump(summary, f, indent=2)

    print(
        f"parse_run_results: {summary['counts']['pass']} passed / "
        f"{summary['counts']['fail']} failed / "
        f"{summary['counts']['error']} errored / "
        f"{summary['counts']['skip']} skipped "
        f"(overall={summary['overall_status']})"
    )
    return 0 if summary["overall_status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
