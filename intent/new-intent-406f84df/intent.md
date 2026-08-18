---
kinds: [transformation]
---

# Intent: Add a verifiable staging model (stg_customers) from a raw_customers seed

## Goal

Demonstrate a small, end-to-end verifiable dbt build on MotherDuck: load a tiny customer seed, stage it with a trivial transform, and prove it compiles, materializes, and passes tests. This establishes a minimal, reproducible example of the domain's dbt seed → staging flow.

## Source system

A self-authored dbt seed CSV `seeds/raw_customers.csv` (columns: `id`, `name`, `signup_date`, `country`) — no external source system. The repo's `transformation/` project is a fresh scaffold with no existing source wiring (no `sources.yml`, no models, no seeds); the pre-existing `raw.*` / `stg.stg_salescloud__*` / `mrt.*` relations in the domain database are Salesforce Sales Cloud artifacts with no source definitions in this repo. A dbt seed is therefore the idiomatic, self-contained choice (the project already declares `seed-paths: ['seeds']`).

## Target

MotherDuck ephemeral sandbox — `md:$VD_EPHM_MOTHERDUCK_DATABASE`, schema `$VD_EPHM_SCHEMA` (main) — via the `transformation/` dbt project (profile `dbt_motherduck`). The domain database is read-only; the seed and model materialize in the ephemeral sandbox.

## Objects in scope

- `seeds/raw_customers.csv` — dbt seed producing table `raw_customers` (5–10 rows).
- `models/staging/stg_customers.sql` — staging view: one row per customer, grain keyed by `id`; casts `signup_date` to DATE and uppercases `country`.
- `models/staging/schema.yml` — tests on `stg_customers`: `not_null(id)`, `unique(id)`.

## Deliverables inventory

| # | Deliverable | Kind | Notes |
| --- | --- | --- | --- |
| 1 | `raw_customers` seed (`seeds/raw_customers.csv`) | mart/model | dbt seed, loads via `dbt seed`; grain: one row per customer, key `id` |
| 2 | `stg_customers` staging model | mart/model | staging view; cast `signup_date` → DATE, `upper(country)`; grain keyed by `id` |
| 3 | `schema.yml` tests for `stg_customers` | mart/model | `not_null(id)`, `unique(id)` |

## Consumers

None — this is a self-contained verification example; no mart, exposure, or semantic model consumes it yet.

## Metric definitions

None — `stg_customers` is a shape/type transform only (cast + uppercase); no aggregations or business metrics.

## SLAs / freshness

None — static seed loaded once; no refresh cadence.

## Success criteria

- `dbt build` exits 0 in the sandbox: the seed loads, the model compiles and materializes, and tests pass.
- `raw_customers` holds 5–10 rows; `stg_customers` materializes one row per customer (same row count as the seed).
- `signup_date` is DATE type and `country` is uppercase in `stg_customers`.
- `not_null(id)` and `unique(id)` both pass.
- Verification returns a row count plus sample output.

## Out of scope

- Marts/dims/facts beyond the single staging model.
- Orchestration pipelines and semantic models — `kinds` stays `[transformation]`.
- dlt ingestion pipelines and real source-system integration (e.g. the pre-existing Salesforce Sales Cloud `raw.*` tables).
- Incremental loading and dbt contract enforcement.

## Open questions

- None.

## Approvals

- [x] User approved intent — 2026-08-18 09:20 (UTC)
