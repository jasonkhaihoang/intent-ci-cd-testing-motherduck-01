# Design: Seed raw customers dataset and build stg_raw__customers

## Architecture

- **Grain**: staging only, no marts. `stg_raw__customers` is 1:1 with the source — one row per customer, unique key `customer_id`.
- **Materialization**: `customers` seed is a table; `stg_raw__customers` is a view in `main` (the project's `staging` config).
- **Approach**: seed `customers.csv` via `dbt seed` into `main`, register it as `source('raw','customers')`, and build a thin rename/type-safety staging view over it.
- **Key decision**: register the seed as a source (rather than `ref()`ing it) so downstream models depend on a stable `source()` contract, matching the medallion source → staging pattern.

## Inventory

### Model Inventory

| Model | Layer | Grain | Materialization | Source | Columns |
| --- | --- | --- | --- | --- | --- |
| stg_raw__customers | staging | one row per customer (`customer_id`) | view | source raw.customers | customer_id, customer_name, signup_date, country |

## Source Mapping / Discovery

| Source | Schema | Table | Staging model |
| --- | --- | --- | --- |
| raw | main | customers | stg_raw__customers |

## Change Impact

Fresh build: no existing models, sources, or downstream consumers to touch. The repo's staging layer is empty; this is the first committed source and model, so no-impact.

## Approvals

- [x] Design stop waived — waive_design_stop: true — 2026-08-19 09:32 (UTC)
