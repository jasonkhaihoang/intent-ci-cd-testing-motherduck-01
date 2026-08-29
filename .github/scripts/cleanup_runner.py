"""Thin shell — reclaim per-PR MotherDuck databases (AC-29).

Invoked by `database-cleanup.yml` on three triggers:
  - `pull_request_target: synchronize` — CLEANUP_PR_NUMBER + HEAD_SHA set; drops
    stale per-SHA databases for the pushed PR (AC-36)
  - `pull_request_target: closed`      — CLEANUP_PR_NUMBER set; drops all databases
    for the closed PR (AC-29)
  - `schedule` / `workflow_dispatch`   — CLEANUP_PR_NUMBER unset; sweeps orphans

The database is the only reclaimable asset: no share and no Dive is created for it
(AC-93, VD-5012), so `DROP DATABASE` is unconditional and there is no share-before-
database ordering to honour.

Owns every I/O seam (MotherDuck connection, `gh api` for open-PR list, DROP DATABASE
execution). Filtering and drop-set derivation live in the pure `ci_database` thin
interfaces.
"""
import json
import os
import subprocess
import sys

import duckdb

import ci_database
import runner_io


def _fetch_open_pr_numbers(repo: str) -> list[int]:
    """Return open PR numbers for `repo` via `gh api`."""
    result = subprocess.run(
        ["gh", "api", "--paginate", f"repos/{repo}/pulls?state=open&per_page=100"],
        capture_output=True, text=True, check=True,
    )
    return [int(pr["number"]) for pr in json.loads(result.stdout)]


def main() -> None:
    token = os.environ["MOTHERDUCK_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    closed_pr_env = os.environ.get("CLEANUP_PR_NUMBER")
    closed_pr_number = int(closed_pr_env) if closed_pr_env else None
    head_sha_short = os.environ.get("HEAD_SHA", "")[:7]

    runner_io.mask(token)

    con = duckdb.connect(f"md:?motherduck_token={token}")
    rows = con.execute("SHOW DATABASES;").fetchall()
    all_db_names = [r[0] for r in rows]
    pr_dbs = ci_database.filter_pr_databases(all_db_names)

    failures: list[tuple[str, str]] = []

    if closed_pr_number is not None and head_sha_short:
        # Synchronize path (AC-36): drop this PR's stale per-SHA databases.
        current_db_name = ci_database.derive_ci_database_name(closed_pr_number, head_sha_short)
        drop_list = ci_database.stale_pr_databases(pr_dbs, closed_pr_number, current_db_name)
        trigger = f"synchronize (PR #{closed_pr_number}, keeping {current_db_name})"

        print(
            f"cleanup_runner: trigger={trigger} pr_databases={len(pr_dbs)} "
            f"stale_to_drop={len(drop_list)}",
            flush=True,
        )

        for name in drop_list:
            sql = ci_database.drop_database_sql(name)
            print(f"  -> {sql}", flush=True)
            try:
                con.execute(sql)
            except Exception as exc:  # best-effort: log and continue
                print(f"     FAILED: {exc}", file=sys.stderr, flush=True)
                failures.append((name, str(exc)))

    else:
        # PR-close or scheduled sweep paths.
        if closed_pr_number is not None:
            open_pr_numbers: list[int] = []
            trigger = f"pr-close (PR #{closed_pr_number})"
        else:
            open_pr_numbers = _fetch_open_pr_numbers(repo)
            trigger = "scheduled sweep"

        drop_list = ci_database.databases_to_drop(
            pr_databases=pr_dbs,
            open_pr_numbers=open_pr_numbers,
            closed_pr_number=closed_pr_number,
        )

        print(
            f"cleanup_runner: trigger={trigger} pr_databases={len(pr_dbs)} "
            f"to_drop={len(drop_list)}",
            flush=True,
        )

        for name in drop_list:
            sql = ci_database.drop_database_sql(name)
            print(f"  -> {sql}", flush=True)
            try:
                con.execute(sql)
            except Exception as exc:  # best-effort: log and continue
                print(f"     FAILED: {exc}", file=sys.stderr, flush=True)
                failures.append((name, str(exc)))

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
