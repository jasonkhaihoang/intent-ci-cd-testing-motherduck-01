"""Pure thin interface: which models does Gate 4 (`ci/data-tests`) test?

`decide_gate4_scope` turns the deployment manifest's already-read text into one of
three decisions, so the runners never run `dbt test` outside the PR's modified-model
closure. No I/O: the shell reads the file and passes `None` when it
is missing or unreadable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

SKIP_REASON = "no models in scope"


@dataclass(frozen=True)
class Skip:
    reason: str


@dataclass(frozen=True)
class Run:
    names: list[str]


@dataclass(frozen=True)
class Fail:
    reason: str


def decide_gate4_scope(manifest_text: str | None, exclude_ephemeral: bool) -> Skip | Run | Fail:
    if manifest_text is None:
        return Fail("deployment manifest is missing or unreadable")
    try:
        manifest = json.loads(manifest_text)
    except json.JSONDecodeError as e:
        return Fail(f"deployment manifest is not valid JSON ({e.msg})")
    if not isinstance(manifest, dict):
        return Fail("deployment manifest is not a JSON object")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        return Fail("deployment manifest has no `artifacts` list")

    names: list[str] = []
    for artifact in artifacts:
        name = artifact.get("name") if isinstance(artifact, dict) else None
        if not isinstance(name, str):
            return Fail("deployment manifest has an artifact without a name")
        # The emitter writes name "" for a closure uid missing from the compiled manifest;
        # the runners always dropped those and tested the rest, so a non-empty closure still runs.
        if not name or (exclude_ephemeral and artifact.get("materialized") == "ephemeral"):
            continue
        names.append(name.split(".")[-1] or name)
    return Run(names) if names else Skip(SKIP_REASON)


def scope_outcome(scope: Skip | Fail, head_sha: str) -> tuple[str, str, dict]:
    """Commit state, status description and `gate-4.json` report for a decision that runs no tests."""
    if isinstance(scope, Skip):
        report = {
            "gate": "4", "head_sha": head_sha, "overall_status": "skipped",
            "reason": scope.reason, "total": 0,
            "counts": {"pass": 0, "fail": 0, "error": 0, "skip": 0}, "tests": [],
        }
        return "success", f"Gate 4: skipped — {scope.reason}", report
    report = {"gate": "4", "head_sha": head_sha, "overall_status": "error", "error": scope.reason}
    return "failure", f"Gate 4: {scope.reason}", report
