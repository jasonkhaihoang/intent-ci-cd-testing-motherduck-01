---
artifacts:
  - stg_raw__sales
---

# stg_raw__sales

Staging view over `raw.sales`.

- Materialization: view.
- Grain: one row per sale (`sale_id`).
- Columns: `sale_id` (renamed from `id`), `customer_id`, `product`, `quantity`, `unit_price`, `sale_date` (cast to date), `region`.
- Tests: `sale_id` is not null and unique.

## Change in this intent

A comment-only edit to the model file. No change to grain, materialization, columns or tests.
