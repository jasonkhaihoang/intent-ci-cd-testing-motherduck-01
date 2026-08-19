"""Per-PR MotherDuck database lifecycle — pure SQL emission + drop-set derivation.

All functions are pure: no I/O, no live DB connections. SQL strings are
returned for the caller to execute via dbt-duckdb or a direct md: connection.
"""
import re
from typing import Iterable

_PR_DB_RE = re.compile(r"^pr_(\d+)_[0-9a-f]+$")


def derive_ci_database_name(pr_number: int, head_sha_short: str) -> str:
    """Deterministic per-PR database name: pr_{pr_number}_{head_sha_short}."""
    return f"pr_{pr_number}_{head_sha_short}"


def create_database_from_prod_sql(name: str, prod_db_name: str = "prd") -> str:
    """Render CREATE DATABASE <name> FROM <prod_db_name>."""
    return f"CREATE DATABASE {name} FROM {prod_db_name};"


def clear_db_retention_sql(db_name: str) -> str:
    """Render ALTER DATABASE <db_name> SET SNAPSHOT_RETENTION_DAYS = 0.

    Called as a fallback when CREATE DATABASE … FROM <db_name> fails because
    <db_name> has >0 snapshot retention incompatible with a free-plan account.
    After this call the clone can be retried. No-op on databases that already
    have 0-day retention.
    """
    return f"ALTER DATABASE {db_name} SET SNAPSHOT_RETENTION_DAYS = 0;"


def drop_database_sql(name: str) -> str:
    """Render DROP DATABASE <name>."""
    return f"DROP DATABASE {name};"


def filter_pr_databases(all_db_names: Iterable[str]) -> list[str]:
    """Return only well-formed per-PR database names (`pr_<digits>_<hex>`)."""
    return [n for n in all_db_names if _PR_DB_RE.match(n)]


def stale_pr_databases(
    pr_databases: Iterable[str],
    pr_number: int,
    current_db_name: str,
) -> list[str]:
    """Return databases for `pr_number` that are not `current_db_name`.

    Used by the gate-2 push-cleanup step to drop stale per-SHA databases
    immediately after the new one is confirmed created.
    """
    result: list[str] = []
    for name in pr_databases:
        m = _PR_DB_RE.match(name)
        if not m:
            continue
        if int(m.group(1)) == pr_number and name != current_db_name:
            result.append(name)
    return result


def databases_to_drop(
    pr_databases: Iterable[str],
    open_pr_numbers: Iterable,
    closed_pr_number: int | None,
) -> list[str]:
    """Derive the set of per-PR databases to drop.

    - When `closed_pr_number` is given (PR-close trigger), return every database
      belonging to that PR — including multiple SHAs from prior force-pushes.
    - When `closed_pr_number` is None (scheduled sweep), return every database
      whose PR number is not in `open_pr_numbers` (orphans).
    """
    open_set = {int(n) for n in open_pr_numbers}
    result: list[str] = []
    for name in pr_databases:
        m = _PR_DB_RE.match(name)
        if not m:
            continue
        pr_num = int(m.group(1))
        if closed_pr_number is not None:
            if pr_num == int(closed_pr_number):
                result.append(name)
        else:
            if pr_num not in open_set:
                result.append(name)
    return result


def _schema_from_relation_name(relation_name: str) -> str:
    """Extract schema from a dbt relation_name like '"db"."stg"."model"'."""
    if not relation_name:
        return ""
    parts = relation_name.replace('"', '').split('.')
    return parts[1] if len(parts) == 3 else ""


def extract_model_schemas(run_results: dict | None) -> dict[str, str]:
    """Extract {model_name: schema} from dbt run_results.json.

    Reads the top-level relation_name field (e.g. '"db"."stg"."model"') to get
    the actual rendered schema. Falls back to node.schema, then to 'main'.
    node.schema holds the profile-level default, not the custom schema override.
    """
    result: dict[str, str] = {}
    for r in (run_results or {}).get("results", []):
        node = r.get("node") or {}
        name = node.get("name") or r.get("unique_id", "").split(".")[-1]
        schema = (
            _schema_from_relation_name(r.get("relation_name") or "")
            or node.get("schema")
            or "main"
        )
        if name:
            result[name] = schema
    return result


def build_dive_jsx(
    db_name: str,
    model_schemas: dict[str, str],
    share_url: str | None = None,
) -> str:
    """Build Dive JSX content with fully-qualified table references.

    Generates useSQLQuery hooks as db_name.schema.model so the Dive resolves
    correctly in any MotherDuck user session, not just the CI runner's.
    Returns an empty string when model_schemas is empty (caller guards on this).

    When share_url is given (AC-10 extension, VD-3321), also exports REQUIRED_DATABASES so
    MotherDuck auto-attaches the per-PR database's read-only share for any viewer who isn't the
    owning service account, before running the Dive's queries — no manual ATTACH needed.
    """
    if not model_schemas:
        return ""
    hooks = "\n  ".join(
        f'const {{ data: {name} }} = useSQLQuery('
        f'"SELECT * FROM {db_name}.{schema}.{name} LIMIT 20");'
        for name, schema in model_schemas.items()
    )
    panels = "\n      ".join(
        f"<div><h2>{name}</h2><pre>{{JSON.stringify({name}, (_, v) => typeof v === 'bigint' ? v.toString() : v, 2)}}</pre></div>"
        for name in model_schemas
    )
    required_databases_export = ""
    if share_url:
        required_databases_export = (
            "export const REQUIRED_DATABASES = "
            f'[{{ type: "share", path: "{share_url}", alias: "{db_name}" }}];\n'
        )
    return (
        'import { useSQLQuery } from "@motherduck/react-sql-query";\n'
        f"{required_databases_export}"
        "export default function Dive() {\n"
        f"  {hooks}\n"
        "  return (\n"
        "    <div>\n"
        f"      {panels}\n"
        "    </div>\n"
        "  );\n"
        "}"
    )


_E2E_SCENARIOS = ("greenfield", "incremental-modify", "incremental-staging")


def build_scenario_matrix(scenario: str) -> list[str]:
    """Expand a `/test-ci-motherduck` scenario input into the list of scenarios to run.

    "all" → every scenario; a single scenario → single-element list.
    Unknown scenario → ValueError.
    """
    if scenario == "all":
        return list(_E2E_SCENARIOS)
    if scenario in _E2E_SCENARIOS:
        return [scenario]
    raise ValueError(
        f"unknown scenario {scenario!r}; expected 'all' or one of {list(_E2E_SCENARIOS)}"
    )


def derive_e2e_db_name(scenario: str, run_id: str) -> str:
    """Derive identifier-safe E2E database name: pr_e2e_<scenario>_<run_id_short>.

    Hyphens in `scenario` are normalised to underscores so the rendered name is a
    valid DuckDB/MotherDuck identifier. `run_id_short` is the first 8 chars of
    `run_id`, lowercased and hyphen-stripped.
    """
    if scenario not in _E2E_SCENARIOS:
        raise ValueError(
            f"unknown scenario {scenario!r}; expected one of {list(_E2E_SCENARIOS)}"
        )
    scenario_safe = scenario.replace("-", "_")
    run_id_short = run_id.lower().replace("-", "")[:8]
    return f"pr_e2e_{scenario_safe}_{run_id_short}"


_DIVE_TITLE_RE = re.compile(r"^CI build pr_(\d+)_[0-9a-f]+$")


def derive_dive_title(pr_number: int, head_sha_short: str) -> str:
    """Canonical Dive title: 'CI build pr_<N>_<sha>'. Used by cleanup (match); Gate 2 migration pending."""
    return f"CI build pr_{pr_number}_{head_sha_short}"


def list_dives_sql() -> str:
    """Render SELECT to list all Dives with their id and title."""
    return "SELECT id, title FROM MD_LIST_DIVES();"


def drop_dive_sql(dive_id: str) -> str:
    """Render SELECT * FROM MD_DELETE_DIVE(id = '<dive_id>'::UUID).

    dive_id is sourced from MD_LIST_DIVES() and is a MotherDuck-controlled UUID.
    The ::UUID cast is required by MD_DELETE_DIVE's parameter type.
    """
    return f"SELECT * FROM MD_DELETE_DIVE(id = '{dive_id}'::UUID);"


def create_share_sql(db_name: str) -> str:
    """Render CREATE OR REPLACE SHARE <db_name> FROM <db_name> (ACCESS ORGANIZATION).

    One org-scoped, read-only share per per-PR database (AC-10 extension, VD-3321): every member
    of the MotherDuck organization gets read access to this one database — no per-user
    GitHub-username-to-MotherDuck-account mapping needed, and access via a share is inherently
    read-only (only ATTACH is possible; there is no write path on a share). OR REPLACE makes this
    idempotent (a bare CREATE SHARE errors on a name collision, e.g. a Gate 2 re-run after a
    partial prior failure) and guarantees the statement's result row always carries a fresh share
    URL — no separate lookup query needed. DISCOVERABLE is the default visibility for
    ACCESS ORGANIZATION shares, so no explicit VISIBILITY clause is needed.
    """
    return f"CREATE OR REPLACE SHARE {db_name} FROM {db_name} (ACCESS ORGANIZATION);"


def drop_share_sql(db_name: str) -> str:
    """Render DROP SHARE IF EXISTS <db_name>.

    IF EXISTS makes this safe to call unconditionally alongside every DROP DATABASE /
    MD_DELETE_DIVE in cleanup_runner.py (and the ci.yml stale-per-SHA-drop step) — some per-PR
    databases never got a share (e.g. the no-models path never reaches create_share_sql), and a
    missing share must not fail cleanup.
    """
    return f"DROP SHARE IF EXISTS {db_name};"


def filter_pr_dives(all_dives: Iterable[dict]) -> list[dict]:
    """Return only Dives whose title matches the CI build pr_<N>_<sha> convention."""
    return [d for d in all_dives if _DIVE_TITLE_RE.match(d.get("title", ""))]


def stale_pr_dives(
    pr_dives: Iterable[dict],
    stale_db_names: Iterable[str],
) -> list[str]:
    """Return Dive IDs whose title matches 'CI build <db_name>' for any name in stale_db_names.

    Used by the synchronize cleanup path: for each stale database being dropped,
    the Dive with the matching title is also dropped.
    """
    titles = {f"CI build {name}" for name in stale_db_names}
    return [d["id"] for d in pr_dives if d.get("title") in titles]


def dives_to_drop(
    pr_dives: Iterable[dict],
    open_pr_numbers: Iterable,
    closed_pr_number: int | None,
) -> list[str]:
    """Return Dive IDs to drop on the PR-close or scheduled-sweep paths (AC-29).

    - closed_pr_number given (PR-close): return IDs of every Dive for that PR.
    - None (scheduled sweep): return IDs of Dives whose PR is not in open_pr_numbers.

    Callers should pass output of filter_pr_dives — the inner title guard is defensive
    and handles unfiltered input, but the canonical call site always pre-filters.
    """
    open_set = {int(n) for n in open_pr_numbers}
    result: list[str] = []
    for dive in pr_dives:
        m = _DIVE_TITLE_RE.match(dive.get("title", ""))
        if not m:
            continue
        pr_num = int(m.group(1))
        if closed_pr_number is not None:
            if pr_num == int(closed_pr_number):
                result.append(dive["id"])
        else:
            if pr_num not in open_set:
                result.append(dive["id"])
    return result
