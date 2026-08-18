# Design: stg_customers staging model from a raw_customers seed

## Architecture

- **Grain** — `stg_customers` is one row per customer, keyed by `id`.
- **Approach** — a dbt seed `raw_customers` (5–10 rows) feeds a single staging view `stg_customers` that performs a trivial shape/type transform: cast `signup_date` to DATE, `upper(country)`, pass `id` and `name` through. Materialization follows the project's existing layer config (`staging: +materialized: view` in `dbt_project.yml`).
- **Seed over source** — the repo's dbt project has no existing source wiring (empty `models/`, `seeds/`, no `sources.yml`), so a dbt seed is chosen over a source + manual insert: it is version-controlled, self-contained, and `dbt build` runs seed → run → test in one pass. The pre-existing `raw.*` / `stg.stg_salescloud__*` / `mrt.*` relations in the domain database are Salesforce Sales Cloud artifacts with no source definitions in this repo and are unrelated to this model.
- **Naming** — `stg_customers` per the request. The domain's `stg_{source}__{table}` convention presupposes an external source system; a self-authored seed has no source system to name, so the literal name is used. Recorded in `docs/adr/0001-staging-model-naming-for-seed-fed-models.md`.

## Inventory

### Model Inventory

| Model | Layer | Grain | Materialization | Dependencies | Status |
| --- | --- | --- | --- | --- | --- |
| stg_customers | staging | one row per customer, keyed by `id` | view | `ref('raw_customers')` | working |

`raw_customers` is a seed (loaded via `dbt seed`), not a model — it is an input, so it has no Inventory row of its own.

## Source Mapping / Discovery

- `raw_customers` (dbt seed, authored in-scope; columns `id`, `name`, `signup_date`, `country`; 5–10 rows) → `stg_customers` (staging view).

**Bronze Adequacy: Ready (by construction).** The seed is authored by this intent with clean, typed data — non-null, unique integer `id`, ISO `YYYY-MM-DD` `signup_date`, text `name`/`country`. It does not pre-exist in the domain catalog (it materializes in the ephemeral sandbox at build time), so there is no pre-existing bronze table to profile; its absence from the domain is by design, not a missing ingestion run.

## Change Impact

No existing artifacts impacted — fresh build target. The repo's dbt project has an empty `models/` directory and no `target/manifest.json`; the pre-existing `stg_salescloud__*` / `mrt.*` relations live only in the domain database with no source definitions in this repo, so `stg_customers` neither `ref()`s them nor is reachable from them.

## Approvals

- [x] User approved design — 2026-08-18 09:46 (UTC)
