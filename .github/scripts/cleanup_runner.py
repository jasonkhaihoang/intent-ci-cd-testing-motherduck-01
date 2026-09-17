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

Owns every I/O seam (MotherDuck connection, `gh api` for the open-PR list and the
PR head-SHA freshness re-check, DROP DATABASE execution). Filtering and drop-set
derivation live in the pure `ci_database` thin interfaces.
"""
import json
import os
import subprocess
import sys

import duckdb

import ci_database
import runner_io


class _LocalDirCursor:
    def __init__(self, rows: list[tuple]):
        self._rows = rows

    def fetchall(self) -> list[tuple]:
        return self._rows


class _LocalDirConnection:
    """Fake MotherDuck connection over a directory of `<db_name>.duckdb` files
    (ADR 0016) — used only when FAKE_WORLD_LOCAL_DUCKDB_DIR is set, mirroring
    Gate 2's own local-file approximation of `SHOW DATABASES` / `DROP DATABASE`
    for fake-world coverage (AC-97, VD-5799)."""

    def __init__(self, directory: str):
        self._dir = directory

    def execute(self, sql: str) -> _LocalDirCursor:
        stripped = sql.strip()
        upper = stripped.upper()
        if upper.startswith("SHOW DATABASES"):
            names = sorted(
                os.path.splitext(f)[0] for f in os.listdir(self._dir) if f.endswith(".duckdb")
            )
            return _LocalDirCursor([(n,) for n in names])
        if upper.startswith("DROP DATABASE"):
            name = stripped[len("DROP DATABASE"):].strip().rstrip(";").strip()
            os.remove(os.path.join(self._dir, f"{name}.duckdb"))
            return _LocalDirCursor([])
        return _LocalDirCursor([])


def _fetch_open_pr_numbers(repo: str) -> list[int]:
    """Return open PR numbers for `repo` via `gh api`."""
    result = subprocess.run(
        ["gh", "api", "--paginate", f"repos/{repo}/pulls?state=open&per_page=100"],
        capture_output=True, text=True, check=True,
    )
    return [int(pr["number"]) for pr in json.loads(result.stdout)]


def _gh_api_pr(repo: str, pr_number: int) -> dict:
    """Return `pr_number`'s live PR data via `gh api` (freshness re-check, VD-5020/VD-5041).

    Shared transport for the two freshness re-checks below — the synchronize path's head-SHA
    read and the close path's state read both need a live look at the same `gh api` endpoint
    immediately before their own destructive step, so this is one shared I/O seam rather than
    two separate `gh api` callers. Callers use the named accessors below, not this directly,
    so GitHub's JSON shape stays confined to this module instead of leaking into `main()`.
    """
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/pulls/{pr_number}"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def _fetch_pr_head_sha(repo: str, pr_number: int) -> str:
    """Return `pr_number`'s live head SHA (freshness re-check, VD-5020)."""
    return _gh_api_pr(repo, pr_number)["head"]["sha"]


def _fetch_pr_state(repo: str, pr_number: int) -> str:
    """Return `pr_number`'s live state, `"open"` or `"closed"` (freshness re-check, VD-5041)."""
    return _gh_api_pr(repo, pr_number)["state"]


def main() -> None:
    token = os.environ["MOTHERDUCK_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    domain_slug = os.environ["DOMAIN_SLUG"]
    closed_pr_env = os.environ.get("CLEANUP_PR_NUMBER")
    closed_pr_number = int(closed_pr_env) if closed_pr_env else None
    head_sha_short = os.environ.get("HEAD_SHA", "")[:7]

    runner_io.mask(token)

    local_duckdb_dir = os.environ.get("FAKE_WORLD_LOCAL_DUCKDB_DIR")
    con = _LocalDirConnection(local_duckdb_dir) if local_duckdb_dir else duckdb.connect(
        f"md:?motherduck_token={token}"
    )
    rows = con.execute("SHOW DATABASES;").fetchall()
    all_db_names = [r[0] for r in rows]
    pr_dbs = ci_database.filter_pr_databases(all_db_names, domain_slug)

    failures: list[tuple[str, str]] = []

    if closed_pr_number is not None and head_sha_short:
        # Synchronize path (AC-36): drop this PR's stale per-SHA databases.
        # VD-5020: re-check the PR's live head immediately before dropping — if a newer
        # push has landed since this run was triggered, this run is stale and must not
        # drop the newer run's live database. The newer run's own freshness check will
        # handle its own valid drop list. (The database snapshot above precedes this
        # check; that's safe because a `pr_<N>_<sha>` database existing at all implies
        # its push had already landed.)
        live_head_sha_short = _fetch_pr_head_sha(repo, closed_pr_number)[:7]
        if live_head_sha_short != head_sha_short:
            print(
                f"cleanup_runner: stale trigger for PR #{closed_pr_number} "
                f"(event head={head_sha_short}, live head={live_head_sha_short}) — "
                f"skipping stale-drop; a newer push's cleanup run supersedes this one (VD-5020)",
                flush=True,
            )
        else:
            current_db_name = ci_database.derive_ci_database_name(
                domain_slug, closed_pr_number, head_sha_short
            )
            drop_list = ci_database.stale_pr_databases(
                pr_dbs, domain_slug, closed_pr_number, current_db_name
            )
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
        skip_close_drop = False
        if closed_pr_number is not None:
            # VD-5041: re-check the PR is still closed immediately before dropping — if it
            # has been reopened since this run was triggered (and a fresh per-SHA database
            # provisioned), this run is stale and must not drop the reopened PR's live
            # database. The scheduled sweep remains authoritative and will reclaim the
            # databases whenever the PR closes for good.
            live_pr_state = _fetch_pr_state(repo, closed_pr_number)
            skip_close_drop = live_pr_state != "closed"
            open_pr_numbers: list[int] = []
            trigger = f"pr-close (PR #{closed_pr_number})"
        else:
            open_pr_numbers = _fetch_open_pr_numbers(repo)
            trigger = "scheduled sweep"

        if skip_close_drop:
            print(
                f"cleanup_runner: stale trigger for PR #{closed_pr_number} "
                f"(event=closed, live state={live_pr_state}) — skipping drop; the PR has been "
                f"reopened since this run was triggered (VD-5041)",
                flush=True,
            )
            drop_list: list[str] = []
        else:
            drop_list = ci_database.databases_to_drop(
                pr_databases=pr_dbs,
                domain_slug=domain_slug,
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
