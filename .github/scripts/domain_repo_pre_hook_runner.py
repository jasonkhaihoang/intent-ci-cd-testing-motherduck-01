"""Shell for the domain-repo pre-push hook: gathers git state, calls the pure
core (domain_repo_pre_hook.py) exactly once, renders the result.

Reads git's actual pre-push protocol: the ref-update lines
("<local ref> <local sha1> <remote ref> <remote sha1>") on stdin. The
comparison base for each ref update is the remote_sha itself — literally
"what the remote already has" (functional spec's Inputs section) — falling
back to merge-base(HEAD, origin/HEAD) only for a brand-new branch push
(remote_sha is the all-zero hash).

Fails open (exit 0, allow) on anything that is not a confident dirty verdict:
not a git checkout, no ref updates on stdin, no resolvable comparison point
for a new branch, or any unexpected error in main(). A confirmed finding
from the core is always blocked once the shell has enough state to call it.

Known residual limitation, not silently dropped: gather_changed_files diffs
with --diff-filter=ACMRT (no D), so a pure deletion of a previously-published
disqualifying path is never itself flagged (Finding 1's fix) — but this also
means a file added and then deleted entirely within the commits being pushed
is invisible to this check altogether (no add, no delete, nothing to diff).
Full historical-blob scanning across the whole pushed range is out of scope
for this chunk.
"""
from __future__ import annotations

import subprocess
import sys

from domain_repo_pre_hook import evaluate_publish, render_block_message

_MAX_SCAN_BYTES = 65536
_ZERO_SHA = "0" * 40


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def parse_ref_updates(stdin_bytes: bytes) -> list[dict]:
    updates = []
    for line in _decode(stdin_bytes).splitlines():
        if not line.strip():
            continue
        local_ref, local_sha, remote_ref, remote_sha = line.split()
        updates.append({
            "local_ref": local_ref, "local_sha": local_sha,
            "remote_ref": remote_ref, "remote_sha": remote_sha,
        })
    return updates


def resolve_comparison_base(run, remote_sha: str) -> str | None:
    if remote_sha and remote_sha != _ZERO_SHA:
        return remote_sha

    ref_result = run(["git", "rev-parse", "--abbrev-ref", "origin/HEAD"])
    base_ref = _decode(ref_result.stdout).strip() if ref_result.returncode == 0 else "origin/main"

    merge_base_result = run(["git", "merge-base", "HEAD", base_ref])
    if merge_base_result.returncode != 0:
        return None
    return _decode(merge_base_result.stdout).strip() or None


def gather_changed_files(run, base: str | None, local_sha: str) -> list[str]:
    """Files changed/added by this push. Deletions (diff-filter D) are
    deliberately excluded: the core classifies by path string alone and
    can't tell a deletion from an addition, so a pure deletion of a
    previously-published disqualifying path must not itself produce a
    finding — see this module's docstring for the residual gap this
    leaves (an add-then-delete within the same push)."""
    if base is not None:
        result = run(["git", "diff", "--name-only", "--diff-filter=ACMRT", f"{base}..{local_sha}"])
    else:
        result = run(["git", "ls-tree", "-r", "--name-only", local_sha])
    return [line for line in _decode(result.stdout).splitlines() if line]


def force_added_ignored_paths(run, files: list[str]) -> set[str]:
    if not files:
        return set()
    result = run(["git", "check-ignore", "--no-index", "--"] + files)
    return {line for line in _decode(result.stdout).splitlines() if line}


def path_in_history(run, base: str | None, path: str) -> bool:
    if base is None:
        return False
    result = run(["git", "cat-file", "-e", f"{base}:{path}"])
    return result.returncode == 0


def read_file_head(run, local_sha: str, path: str, max_bytes: int = _MAX_SCAN_BYTES) -> bytes | None:
    """The first max_bytes of `path` in the commit being pushed (local_sha),
    not the working tree. Capped to bound memory/regex cost on a pathological
    large file — a secret starting after this offset is not scanned; see this
    plan's Coverage note for the tradeoff."""
    result = run(["git", "show", f"{local_sha}:{path}"])
    if result.returncode != 0:
        return None
    return result.stdout[:max_bytes]


def run_hook(run, stdin_bytes: bytes) -> dict:
    """Gather → call, once, for every ref update in this push. Same return
    shape as evaluate_publish; {"decision": "allow", "findings": []} when
    there is nothing to evaluate."""
    updates = parse_ref_updates(stdin_bytes)
    all_entries = []
    for update in updates:
        local_sha = update["local_sha"]
        base = resolve_comparison_base(run, update["remote_sha"])
        files = gather_changed_files(run, base, local_sha)
        if not files:
            continue
        ignored = force_added_ignored_paths(run, files)
        for path in files:
            content = read_file_head(run, local_sha, path)
            all_entries.append({
                "path": path,
                "force_added_ignored": path in ignored,
                "content": content,
                "in_history": path_in_history(run, base, path),
            })
    if not all_entries:
        return {"decision": "allow", "findings": []}
    return evaluate_publish(all_entries)


def main(argv: list[str]) -> int:
    try:
        def run(cmd: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(cmd, capture_output=True)

        if run(["git", "rev-parse", "--is-inside-work-tree"]).returncode != 0:
            return 0

        result = run_hook(run, sys.stdin.buffer.read())
        if result["decision"] == "block":
            sys.stderr.write(render_block_message(result["findings"]) + "\n")
            return 2
        return 0
    except Exception as exc:
        sys.stderr.write(f"domain-repo-pre-hook: unexpected error, allowing push: {exc}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
