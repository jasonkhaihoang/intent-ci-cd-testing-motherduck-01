# Design

## Scope

Add a fake sales dataset as a dbt seed and build a staging model from it.

## Changes

### Seed: `sales.csv`

- 10 sample sales records with columns: `id`, `customer_id`, `product`, `quantity`, `unit_price`, `sale_date`, `region`
- Registered as dbt source `raw.sales` in `sources.yml`

### Model: `stg_raw__sales`

- Staging view over `raw.sales`
- Renames `id` → `sale_id`
- Type-casts `sale_date` to `date`
- Materialized as view (staging layer default)
- Documented in `schema.yml` with column descriptions and tests (`not_null`, `unique` on `sale_id`)
