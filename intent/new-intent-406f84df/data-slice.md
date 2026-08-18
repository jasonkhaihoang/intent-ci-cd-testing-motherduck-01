# Data slice — stg_customers

## Deliverable 2 — `stg_customers` (staging model)

### Candidate input

`raw_customers` (the dbt seed authored as Deliverable 1 of this intent): columns `id`, `name`, `signup_date`, `country`. No pre-existing domain table sits at or near this grain — the seed is the source and is authored in-scope, so there is no external table to prefer and no join to add.

### Profiling evidence

The seed contents are authored by this intent, so the driving columns are fully known rather than profiled:

- `id` — customer key, drives the grain and the `unique`/`not_null` tests.
- `signup_date` — cast to DATE in the model.
- `country` — uppercased in the model.
- `name` — passed through unchanged.

There is no prior domain data to profile for this table (greenfield for `raw_customers`).

### Sizing verdict

Bring the complete table, no sampling — the seed is 5–10 rows.

### Join expectations

None — the model reads a single seed with no joins.

### Bounded export SQL (shape)

```sql
SELECT id, name, signup_date, country
FROM raw_customers
```
