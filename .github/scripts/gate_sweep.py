"""Terminal-status sweep for required gates that never ran (VD-5918, SB-18).

Each gate job posts its own commit status. A job that is skipped or cancelled
posts nothing, so its required context stays `pending` for ever: branch
protection blocks the merge, and the PR says nothing about why. That is the
whole cost of a cascade — one broken artifact silently withholds the verdict
on every gate below it.

This module decides, from the workflow's own job results, which required
contexts were left without one and what to say about them. It names the gates
that actually concluded in failure, so the reader is pointed at the cause
rather than at the collapse.

Pure: the caller supplies the job results and dispatches the emissions.
"""
from typing import Mapping, NamedTuple

from emit_status import DESCRIPTION_LIMIT
from platform_enum import FABRIC_LAKEHOUSE, MOTHERDUCK


class SweepStatus(NamedTuple):
    context: str
    state: str
    description: str


# Required context -> the ci.yml job that owns emitting it. Order is the gate
# ladder's own order; it drives both the sweep order and the order causes are
# named in. Locked against ci.yml and configure_repo.py by
# tests/unit/domain_pr_review_approval/test_ci_yml_status_sweep.py.
_FABRIC_OWNERS = {
    "ci/preflight": "preflight",
    "ci/adr-numbering": "adr-numbering",
    "ci/static-check": "static-analysis",
    "ci/state-modified+": "fetch-prod-state",
    "ci/design-drift": "design-drift",
    "ci/orchestration": "orchestration",
    "ci/semantic-model": "semantic-model",
    "ci/provision": "provision-workspace",
    "ci/run": "gate-2-write",
    "ci/unit-tests": "gate-3-unit",
    "ci/data-tests": "gate-4-data-test",
}

_MOTHERDUCK_OWNERS = {
    "ci/preflight": "preflight",
    "ci/adr-numbering": "adr-numbering",
    "ci/static-check": "static-analysis",
    "ci/state-modified+": "fetch-prod-state",
    "ci/design-drift": "design-drift",
    "ci/orchestration": "orchestration",
    "ci/semantic-model": "semantic-model",
    "ci/run": "gate-2-run",
    "ci/unit-tests": "gate-3-unit",
    "ci/data-tests": "gate-4-data-test",
}

_OWNERS_BY_PLATFORM = {
    FABRIC_LAKEHOUSE: _FABRIC_OWNERS,
    MOTHERDUCK: _MOTHERDUCK_OWNERS,
}

# A context already carrying one of these has its verdict and must be left alone.
_TERMINAL = ("success", "failure", "error")


# "Not run — blocked by " plus the longest plausible blame list overruns the
# status description, and GitHub truncates mid-context — a list that reads
# complete but is not, on the one status whose job is to name the cause.
_BLAME_PREFIX = "Not run — blocked by "


def _name_within_limit(contexts: list) -> str:
    """As many blamed contexts as fit, then an honest count of the rest."""
    budget = DESCRIPTION_LIMIT - len(_BLAME_PREFIX)
    named = []
    for i, context in enumerate(contexts):
        remaining = len(contexts) - i - 1
        suffix = f", +{remaining} more" if remaining else ""
        candidate = ", ".join(named + [context]) + suffix
        if len(candidate) > budget:
            return ", ".join(named) + f", +{len(contexts) - len(named)} more"
        named.append(context)
    return ", ".join(named)


def owners_for(platform: str) -> Mapping[str, str]:
    """The required context -> owning job map for a platform."""
    try:
        return _OWNERS_BY_PLATFORM[platform]
    except KeyError:
        raise ValueError(f"no gate sweep defined for platform {platform!r}")


def plan_gate_sweep(
    platform: str, job_results: Mapping[str, str], status_states: Mapping[str, str]
) -> list:
    """Terminal statuses to post for required contexts still without a verdict.

    `status_states` is the latest state already posted per context; a context
    absent from it has never been posted at all. Whether a context needs a
    verdict is read from there rather than inferred from its job's result,
    because the two disagree: a job that dies before its runner runs concludes
    as `failure` having posted nothing.

    `job_results` is GitHub's own per-job `result` for every job in the run
    (`success` / `failure` / `skipped` / `cancelled`), and says only what the
    swept status should blame.
    """
    owners = owners_for(platform)
    failed = [ctx for ctx, job in owners.items() if job_results.get(job) == "failure"]
    if failed:
        blocked = _BLAME_PREFIX + _name_within_limit(failed)
    else:
        blocked = "Not run — the run ended before this gate started"

    def describe(job: str) -> str:
        result = job_results.get(job)
        if result == "failure":
            return "Gate failed without reporting — see the job log"
        if result == "success":
            # The job ran and exited 0 without posting — "not run" would be
            # false, and so would blaming a gate that did fail.
            return "Gate succeeded without reporting — see the job log"
        return blocked

    return [
        SweepStatus(ctx, "failure", describe(job))
        for ctx, job in owners.items()
        if status_states.get(ctx) not in _TERMINAL
    ]
