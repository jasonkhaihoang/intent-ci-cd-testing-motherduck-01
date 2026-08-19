# Design: stg_customers staging model from a project-owned src_customers model

## Architecture

- **Grain** — `stg_customers` is one row per customer, keyed by `id`.
- **Approach** — a project-owned source model `src_customers` (8 rows, `materialized='table'`) feeds a single staging view `stg_customers` that performs a trivial shape/type transform: cast `signup_date` to DATE, `upper(country)`, pass `id` and `customer_name` through. Materialization follows the project's layer config (`staging: +materialized: view` in `dbt_project.yml`; `src_customers` overrides to `table`).
- **Source model over seed** — the repo's dbt project has no existing source wiring (empty `models/`, `seeds/`, no `sources.yml`), so `src_customers` is authored in-repo as a dbt model rather than a source + manual insert. This keeps the data version-controlled and self-contained, and — unlike a dbt seed — it is part of the deployment-manifest closure (`dbt ls --resource-type model`), so the CI's model-only `dbt run` materializes it and `stg_customers` can `ref()` it.
- **Naming** — `stg_customers` per the request. The domain's `stg_{source}__{table}` convention presupposes an external source system; a project-owned source model has no source system to name, so the literal name is used. Recorded in `docs/adr/0001-staging-model-naming-for-project-owned-source-models.md`.

## Inventory

### Model Inventory

| Model | Layer | Grain | Materialization | Dependencies | Status |
| --- | --- | --- | --- | --- | --- |
| src_customers | staging | one row per customer, keyed by `id` | table | none (in-repo literal rows) | working |
| stg_customers | staging | one row per customer, keyed by `id` | view | `ref('src_customers')` | working |

## Source Mapping / Discovery

- `src_customers` (dbt model, authored in-scope; columns `id`, `customer_name`, `signup_date`, `country`; 8 rows) → `stg_customers` (staging view).

## Change Impact

No existing artifacts impacted — fresh build target. The repo's dbt project has an empty `models/` directory; the pre-existing `stg_salescloud__*` / `mrt.*` relations live only in the domain database with no source definitions in this repo, so neither model `ref()`s them nor is reachable from them.

## Approvals

- [x] User approved design — 2026-08-18 (UTC)
