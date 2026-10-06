"""Thin shell for the required-gate status sweep (VD-5918, SB-18).

gather → call → dispatch:
  1. Read the workflow's own `needs` result map (passed as JSON by ci.yml) and
     the statuses already posted for the head SHA.
  2. Call plan_gate_sweep (pure).
  3. Post one terminal commit status per required context still without one.

Runs with `if: always()` so it also fires on the cascade it exists to report.
It never rewrites a status a gate posted for itself.

Usage:
    gate_sweep_runner.py --platform motherduck --head-sha abc123 \\
        --needs "$NEEDS_JSON"

Environment:
    GITHUB_REPOSITORY, GH_TOKEN, GITHUB_RUN_ID, GITHUB_SERVER_URL  (status post)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import emit_status

from gate_sweep import plan_gate_sweep


def _run_url() -> str:
    base = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    return f"{base}/{repo}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--needs", required=True, help="toJSON(needs) from the workflow")
    args = parser.parse_args(argv)

    needs = json.loads(args.needs)
    job_results = {job: (outcome or {}).get("result", "") for job, outcome in needs.items()}

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    status_states = emit_status.fetch_status_states(repo, args.head_sha)

    target_url = _run_url()
    failed = []
    for status in plan_gate_sweep(args.platform, job_results, status_states):
        try:
            emit_status.emit_status(
                repo, args.head_sha, status.context, status.state, status.description, target_url
            )
        except SystemExit:
            # emit_status exits the process on a failed post. Here that would
            # abandon every context after this one — leaving pending exactly
            # the checks this job exists to resolve — so each post is isolated
            # and the failures are reported together at the end.
            print(f"Failed to sweep {status.context}", file=sys.stderr)
            failed.append(status.context)

    if failed:
        print(f"Left without a verdict: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
