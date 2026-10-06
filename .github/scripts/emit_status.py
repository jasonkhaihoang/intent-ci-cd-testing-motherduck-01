"""
GitHub commit status emitter.

Posts a commit status to the GitHub Statuses API via urllib.
Reads GITHUB_REPOSITORY, GITHUB_SHA, and GH_TOKEN (or GITHUB_TOKEN) from environment.

Usage:
    emit_status.py --context ci/static-check --state pending \
        --description "Running..." --target-url URL
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


# GitHub truncates a longer description; callers that compose one need to know
# where the cut falls so they can stop somewhere honest rather than mid-word.
DESCRIPTION_LIMIT = 140


def emit_status(repo: str, sha: str, context: str, state: str, description: str, target_url: str) -> None:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    base_url = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")
    url = f"{base_url}/repos/{repo}/statuses/{sha}"
    payload = json.dumps({
        "state": state,
        "context": context,
        "description": description[:DESCRIPTION_LIMIT],
        "target_url": target_url,
    }).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode(errors="replace")
            if resp.status not in (200, 201):
                print(f"Unexpected HTTP {resp.status} posting commit status: {body}", file=sys.stderr)
                sys.exit(1)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"Failed to post commit status: HTTP {e.code} — {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Failed to post commit status (network): {e.reason}", file=sys.stderr)
        sys.exit(1)


_STATUS_READ_ATTEMPTS = 3
_STATUS_READ_BACKOFF_SECONDS = 2
# Eleven own contexts today, but the SHA's statuses are shared with every other
# app posting on it. The cap bounds the loop by its own count rather than by
# trusting the continuation link it is following.
_STATUS_PAGE_LIMIT = 10


def _next_page_url(headers) -> str:
    """The `rel="next"` URL from a Link header, or "" when the page is the last."""
    link = (headers or {}).get("Link", "") if hasattr(headers, "get") else ""
    for part in link.split(","):
        if 'rel="next"' in part and "<" in part and ">" in part:
            return part[part.index("<") + 1:part.index(">")]
    return ""


def _get_json(url: str, token: str):
    """GET with a bounded retry, because the caller cannot proceed without it."""
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    for attempt in range(1, _STATUS_READ_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode(errors="replace")), resp.headers
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            if e.code < 500 or attempt == _STATUS_READ_ATTEMPTS:
                print(f"Failed to read commit statuses: HTTP {e.code} — {detail}", file=sys.stderr)
                sys.exit(1)
            reason = f"HTTP {e.code}"
        except urllib.error.URLError as e:
            if attempt == _STATUS_READ_ATTEMPTS:
                print(f"Failed to read commit statuses (network): {e.reason}", file=sys.stderr)
                sys.exit(1)
            reason = str(e.reason)
        print(f"Commit-status read attempt {attempt} failed ({reason}); retrying", file=sys.stderr)
        time.sleep(_STATUS_READ_BACKOFF_SECONDS * attempt)


def fetch_status_states(repo: str, sha: str) -> dict:
    """The latest state per context already posted for a commit.

    The combined-status endpoint collapses each context to its most recent
    status, which is exactly the question the sweep asks: does this required
    context already carry a verdict? Reading it beats inferring one from job
    results — a job that dies before its runner posts anything concludes as
    `failure` while its context is still `pending` (VD-5918).

    Exits non-zero rather than returning a partial map: a context missing
    because the read was truncated is indistinguishable from one that has no
    verdict, and the caller would post a failure over a gate's own success.
    """
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    base_url = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")
    url = f"{base_url}/repos/{repo}/commits/{sha}/status?per_page=100"

    states = {}
    for _ in range(_STATUS_PAGE_LIMIT):
        body, headers = _get_json(url, token)
        for status in body.get("statuses", []):
            states[status["context"]] = status["state"]
        url = _next_page_url(headers)
        if not url:
            return states

    print(
        f"Commit statuses for {sha} exceed {_STATUS_PAGE_LIMIT} pages; refusing to act on a "
        "partial read",
        file=sys.stderr,
    )
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", required=True)
    parser.add_argument("--state", required=True, choices=["pending", "success", "failure", "error"])
    parser.add_argument("--description", required=True)
    parser.add_argument("--target-url", default="")
    args = parser.parse_args()

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    sha = os.environ.get("GITHUB_SHA", "")

    if not repo or not sha:
        print("GITHUB_REPOSITORY and GITHUB_SHA env vars are required", file=sys.stderr)
        sys.exit(1)

    emit_status(repo, sha, args.context, args.state, args.description, args.target_url)
    print(f"Status posted: {args.context} -> {args.state}")


if __name__ == "__main__":
    main()
