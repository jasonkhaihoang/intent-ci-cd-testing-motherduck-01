# Design: Sales Data Seed and Staging Model

## Architecture

- **Grain**: staging only, no marts. `stg_raw__sales` is 1:1 with the source — one row per sale transaction, unique key `sale_id`.
- **Materialization**: `sales` seed is a table; `stg_raw__sales` is a view in `main` (the project's `staging` config).
- **Approach**: seed `sales.csv` via `dbt seed` into `main`, register it as `source('raw','sales')`, and build a staging view that type-casts dates and computes `total_amount`.
- **Key decision**: register the seed as a source (rather than `ref()`ing it) so downstream models depend on a stable `source()` contract, matching the medallion source → staging pattern.

## Inventory

### Model Inventory

| Model | Layer | Grain | Materialization | Source | Columns |
| --- | --- | --- | --- | --- | --- |
| stg_raw__sales | staging | one row per sale (`sale_id`) | view | source raw.sales | sale_id, customer_id, product, quantity, unit_price, region, sale_date, total_amount |

## Source Mapping / Discovery

| Source | Schema | Table | Staging model |
| --- | --- | --- | --- |
| raw | main | sales | stg_raw__sales |

## Change Impact

Fresh build: no existing models, sources, or downstream consumers to touch. The repo's staging layer already contains `stg_raw__customers`; this adds a second source and model with no dependencies between them.

## Approvals

- [x] Design stop waived — waive_design_stop: true — 2026-08-26 14:07 (UTC)
