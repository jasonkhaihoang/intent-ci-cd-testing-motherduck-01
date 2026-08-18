"""Marker-based PR comment upsert.

Single owner of the `gh api` / `gh pr comment` shell calls and the tempfile
dance shared by every CI gate that posts a sticky comment. Marker constants
live with their renderers; this module is purely transport.

Public surface:
    find_by_marker(marker, pr_number, repo) -> str | None
    upsert(marker, body, pr_number, repo) -> None
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


def select_trusted_comment(comments: list[dict], marker: str, trusted_author: str) -> str | None:
    """Return the body of the last comment matching `marker` AND authored by
    `trusted_author`, or None.

    A marker-matching comment from any other account is ignored, not returned —
    this is what prevents an untrusted PR author from forging trusted metadata
    by posting their own marker-matching comment. Last-match-wins: if
    `trusted_author` posts more than once, the most recent post supersedes
    earlier ones.
    """
    match = None
    for comment in comments:
        if marker not in comment.get("body", ""):
            continue
        if comment.get("user", {}).get("login") != trusted_author:
            continue
        match = comment["body"]
    return match


def _fetch_all_comments(pr_number: str, repo: str) -> list[dict]:
    """Fetch every comment on a PR, paginated. Never raises: on gh failure or
    malformed JSON, prints a warning and returns whatever was accumulated so far.
    """
    comments: list[dict] = []
    page = 1
    while True:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/issues/{pr_number}/comments",
             "-f", f"page={page}", "-f", "per_page=100"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"Warning: failed to fetch PR comments (page {page}): {result.stderr}", file=sys.stderr)
            return comments
        try:
            page_comments = json.loads(result.stdout) if result.stdout.strip() else []
        except json.JSONDecodeError:
            print(f"Warning: could not parse PR comments JSON (page {page}).", file=sys.stderr)
            return comments
        comments.extend(page_comments)
        if len(page_comments) < 100:
            return comments
        page += 1


def find_trusted_comment(marker: str, pr_number: str, repo: str, trusted_author: str) -> str | None:
    """Fetch all PR comments and return the trusted match for `marker`, or None."""
    return select_trusted_comment(_fetch_all_comments(pr_number, repo), marker, trusted_author)


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
