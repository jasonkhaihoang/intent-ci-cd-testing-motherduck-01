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
import urllib.error
import urllib.request


def emit_status(repo: str, sha: str, context: str, state: str, description: str, target_url: str) -> None:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    base_url = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")
    url = f"{base_url}/repos/{repo}/statuses/{sha}"
    payload = json.dumps({
        "state": state,
        "context": context,
        "description": description[:140],
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
