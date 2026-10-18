---
artifacts:
  - stg_raw__sales
---

# stg_raw__sales

Staging view over `raw.sales`: renames `id` to `sale_id` and casts `sale_date` to a date.

- Materialization: view.
- Grain: one row per sale (`sale_id`).
- Columns: `sale_id`, `customer_id`, `product`, `quantity`, `unit_price`, `sale_date`, `region`.
- Tests: `sale_id` is not null and unique.

## Change in this intent

A comment-only edit to the model file. No change to grain, materialization, columns, tests or upstream references.
