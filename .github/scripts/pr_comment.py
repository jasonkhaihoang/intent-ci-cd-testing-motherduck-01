"""Marker-based PR comment upsert.

Single owner of the `gh api` / `gh pr comment` shell calls and the tempfile
dance shared by every CI gate that posts a sticky comment. Marker constants
live with their renderers; this module is purely transport.

Public surface:
    find_by_marker(marker, pr_number, repo) -> str | None
    upsert(marker, body, pr_number, repo) -> None
    post_or_log(marker, body, pr_number, repo) -> None
"""

import json
import os
import subprocess
import sys
import tempfile


def find_by_marker(marker: str, pr_number: str, repo: str) -> str | None:
    """Return the id of the first PR comment containing `marker`, or None."""
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/issues/{pr_number}/comments",
         "--jq", f'.[] | select(.body | contains("{marker}")) | .id'],
        capture_output=True, text=True,
    )
    stdout = result.stdout.strip()
    return stdout.splitlines()[0] if stdout else None


def upsert(marker: str, body: str, pr_number: str, repo: str) -> None:
    """Create or update the PR comment identified by `marker`.

    Exits the process with non-zero status if the underlying `gh` call fails.
    """
    comment_id = find_by_marker(marker, pr_number, repo)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp:
        tmp.write(body)
        tmp_path = tmp.name

    try:
        if comment_id:
            result = subprocess.run(
                ["gh", "api", "--method", "PATCH",
                 f"repos/{repo}/issues/comments/{comment_id}",
                 "--field", f"body=@{tmp_path}"],
                capture_output=True, text=True,
            )
        else:
            result = subprocess.run(
                ["gh", "pr", "comment", pr_number,
                 "--repo", repo,
                 "--body-file", tmp_path],
                capture_output=True, text=True,
            )
        if result.returncode != 0:
            print(f"Failed to post PR comment: {result.stderr}", file=sys.stderr)
            sys.exit(1)
    finally:
        os.unlink(tmp_path)


def post_or_log(marker: str, body: str, pr_number: str | None, repo: str | None) -> None:
    """Upsert the PR comment, never raising: skips when `pr_number`/`repo` is
    missing (e.g. a local/manual run), and logs rather than propagates if
    `upsert` fails — a comment-post failure should never mask the caller's
    own exit code.
    """
    if not pr_number or not repo:
        return
    try:
        upsert(marker, body, pr_number, repo)
    except BaseException as e:
        print(f"Failed to post PR comment: {e}", flush=True)


def post_gate_comment(report_path, render_fn, marker, pr_number, repo, real_work_result=None):
    """Load a gate's report JSON (if present) and upsert its PR comment.

    `real_work_result` is the comment job's own `needs.<real-work-job>.result`
    string ('success' | 'failure' | 'skipped' | 'cancelled'). When the report
    is missing AND real_work_result == 'failure', the real-work job crashed
    before it could upload a report — a distinct case from a clean upstream
    skip, so it renders a dedicated error message instead of calling
    render_fn(None) (which would otherwise silently reuse the "Skipped"
    wording for a genuine in-job crash).
    """
    result = None
    try:
        with open(report_path) as f:
            result = json.load(f)
    except (OSError, json.JSONDecodeError):
        pass

    if result is None and real_work_result == "failure":
        body = (
            f"{marker}\n## ⚠️ Gate error\n\n"
            "The gate job failed before it could produce a report — check "
            "the workflow run logs for the underlying error.\n"
        )
    else:
        body = render_fn(result)

    upsert(marker, body, pr_number, repo)
