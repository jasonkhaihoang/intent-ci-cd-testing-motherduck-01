---
kinds: [transformation]
express: true
waive_design_stop: true
---

# Intent: Seed raw customers dataset and build stg_raw__customers

## Goal
Load a small raw `customers` dataset into the MotherDuck sandbox, register it as a dbt source, and build the first staging model over it. This proves the seed → source → staging path end-to-end and establishes the repo's first committed source and staging layer.

## Source system
Customers (sample dataset, seeded via dbt `seeds/customers.csv`).

## Target
MotherDuck sandbox (`md:$VD_EPHM_MOTHERDUCK_DATABASE`), `main` schema for both the seeded source table and the staging view.

## Objects in scope
- `main.customers` (seeded raw table, registered as source `raw`)
- `stg_raw__customers` (staging view)

## Deliverables inventory

| # | Deliverable | Kind | Notes |
| --- | --- | --- | --- |
| 1 | `customers` seed + dbt source registration | mart/model | `customers.csv` seeds into `main`; `sources.yml` registers it as `source('raw','customers')` |
| 2 | `stg_raw__customers` staging model | mart/model | 1:1 rename (`id`→`customer_id`, `name`→`customer_name`) + date type-safety |

## Success criteria
- `dbt seed` materializes `main.customers` in the sandbox.
- `stg_raw__customers` builds via `dbt build` and reads from `source('raw','customers')`.

## Out of scope
- No marts, no ingestion (dlt) pipeline, no orchestration, no semantic model.

## Open questions
- None

## Approvals

`express: true` — intent proceeds without a separate approval round-trip per the user's "minimal, no unnecessary workflow" instruction.
