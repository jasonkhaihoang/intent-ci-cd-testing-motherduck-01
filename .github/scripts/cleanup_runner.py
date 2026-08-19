"""Thin shell — reclaim per-PR MotherDuck databases and Dives (AC-29).

Invoked by `database-cleanup.yml` on three triggers:
  - `pull_request_target: synchronize` — CLEANUP_PR_NUMBER + HEAD_SHA set; drops
    stale per-SHA databases and their Dives for the pushed PR (AC-36, AC-37)
  - `pull_request_target: closed`      — CLEANUP_PR_NUMBER set; drops all databases
    for the closed PR (AC-29)
  - `schedule` / `workflow_dispatch`   — CLEANUP_PR_NUMBER unset; sweeps orphans

Owns every I/O seam (MotherDuck connection, `gh api` for open-PR list,
DROP DATABASE / MD_DROP_DIVE execution). Filtering and drop-set derivation
live in the pure `ci_database` thin interfaces.
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
        # Synchronize path (AC-36, AC-37): drop stale per-SHA databases and their Dives.
        current_db_name = ci_database.derive_ci_database_name(closed_pr_number, head_sha_short)
        drop_list = ci_database.stale_pr_databases(pr_dbs, closed_pr_number, current_db_name)
        trigger = f"synchronize (PR #{closed_pr_number}, keeping {current_db_name})"

        print(
            f"cleanup_runner: trigger={trigger} pr_databases={len(pr_dbs)} "
            f"stale_to_drop={len(drop_list)}",
            flush=True,
        )

        for name in drop_list:
            # VD-3477: share must drop before its database — MotherDuck refuses
            # DROP DATABASE while a share still references it.
            share_sql = ci_database.drop_share_sql(name)
            print(f"  -> {share_sql}", flush=True)
            try:
                con.execute(share_sql)
            except Exception as exc:  # best-effort: log and continue
                print(f"     FAILED: {exc}", file=sys.stderr, flush=True)
                failures.append((name, str(exc)))

            sql = ci_database.drop_database_sql(name)
            print(f"  -> {sql}", flush=True)
            try:
                con.execute(sql)
            except Exception as exc:  # best-effort: log and continue
                print(f"     FAILED: {exc}", file=sys.stderr, flush=True)
                failures.append((name, str(exc)))

        # AC-37: delete Dives matching the planned drop list (best-effort; Dive deletion
        # runs even if a DB drop failed — a Dive without a backing database is harmless).
        dive_rows = con.execute(ci_database.list_dives_sql()).fetchall()
        all_dives = [{"id": r[0], "title": r[1]} for r in dive_rows]
        pr_dives = ci_database.filter_pr_dives(all_dives)
        dive_ids_to_drop = ci_database.stale_pr_dives(pr_dives, stale_db_names=drop_list)

        print(
            f"cleanup_runner: pr_dives={len(pr_dives)} stale_dives_to_drop={len(dive_ids_to_drop)}",
            flush=True,
        )

        for dive_id in dive_ids_to_drop:
            sql = ci_database.drop_dive_sql(dive_id)
            print(f"  -> {sql}", flush=True)
            try:
                con.execute(sql)
            except Exception as exc:  # best-effort: log and continue
                print(f"     FAILED: {exc}", file=sys.stderr, flush=True)
                failures.append((dive_id, str(exc)))

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
            # VD-3477: share must drop before its database — MotherDuck refuses
            # DROP DATABASE while a share still references it.
            share_sql = ci_database.drop_share_sql(name)
            print(f"  -> {share_sql}", flush=True)
            try:
                con.execute(share_sql)
            except Exception as exc:  # best-effort: log and continue
                print(f"     FAILED: {exc}", file=sys.stderr, flush=True)
                failures.append((name, str(exc)))

            sql = ci_database.drop_database_sql(name)
            print(f"  -> {sql}", flush=True)
            try:
                con.execute(sql)
            except Exception as exc:  # best-effort: log and continue
                print(f"     FAILED: {exc}", file=sys.stderr, flush=True)
                failures.append((name, str(exc)))

        # AC-29: drop per-PR Dives alongside databases (list-and-match by title)
        dive_rows = con.execute(ci_database.list_dives_sql()).fetchall()
        all_dives = [{"id": r[0], "title": r[1]} for r in dive_rows]
        pr_dives = ci_database.filter_pr_dives(all_dives)
        dive_ids_to_drop = ci_database.dives_to_drop(
            pr_dives=pr_dives,
            open_pr_numbers=open_pr_numbers,  # [] on PR-close path; unused when closed_pr_number set
            closed_pr_number=closed_pr_number,
        )

        print(
            f"cleanup_runner: pr_dives={len(pr_dives)} dives_to_drop={len(dive_ids_to_drop)}",
            flush=True,
        )

        for dive_id in dive_ids_to_drop:
            sql = ci_database.drop_dive_sql(dive_id)
            print(f"  -> {sql}", flush=True)
            try:
                con.execute(sql)
            except Exception as exc:  # best-effort: log and continue; appends to shared failures list
                print(f"     FAILED: {exc}", file=sys.stderr, flush=True)
                failures.append((dive_id, str(exc)))

        # Orphan-share reconciliation (scheduled sweep only): a share whose name matches the
        # pr_<N>_<sha> convention but has no live database anywhere is unreachable by every other
        # cleanup path (all of them key off a currently-existing database name), so this is the
        # only place that can ever recover it.
        if closed_pr_number is None:
            share_rows = con.execute(
                "SELECT name FROM MD_INFORMATION_SCHEMA.OWNED_SHARES;"
            ).fetchall()
            all_share_names = [r[0] for r in share_rows]
            pr_shares = ci_database.filter_pr_databases(all_share_names)
            orphan_shares = [n for n in pr_shares if n not in pr_dbs]

            print(
                f"cleanup_runner: pr_shares={len(pr_shares)} orphan_shares={len(orphan_shares)}",
                flush=True,
            )

            for name in orphan_shares:
                share_sql = ci_database.drop_share_sql(name)
                print(f"  -> {share_sql}", flush=True)
                try:
                    con.execute(share_sql)
                except Exception as exc:  # best-effort: log and continue
                    print(f"     FAILED: {exc}", file=sys.stderr, flush=True)
                    failures.append((name, str(exc)))

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
