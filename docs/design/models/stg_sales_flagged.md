---
artifacts: [stg_sales_flagged]
---

# stg_sales_flagged

The model's durable record outlives the intent that created it: a later intent that changes this model amends
this file rather than opening a second one.

This record holds only what the code and the project cannot re-derive: why the layer, the shape and the edge
semantics are what they are, and what was rejected.

## Grain

One row per sale — unique on the source sale key (`id`), which the model presents as `sale_id`. No aggregation
and no join, so the grain is the source's own.

## Decisions

`D-01`: **The model is a staging model, not a mart**, even though it carries a derived measure and a threshold
flag, which this domain's `AGENTS.md` assigns to the marts layer ("business logic, star schema, aggregations"
against staging's "1:1 with source tables, rename columns, filter soft-deletes"). The user named the artifact
`stg_sales_flagged` and asked for it as a staging model, so the explicit requirement outranks the layer
convention and the deviation is deliberate. Cites `docs/requirement/2026-09-21-new-intent-eab282dc.md#R-01 rev 1`.
Not promoted to an ADR: the user supplied this as a requirement, so it is not a trade-off the agent made.

`D-02`: **`sale_total` is derived as `quantity * unit_price`, never sourced.** No column holding a sale total
exists in this project's `sales` source contract at any name, so the threshold comparison has nothing to
compare against until the measure is computed. The column is a computed measure and must not be documented or
presented as a source column. Cites `docs/requirement/2026-09-21-new-intent-eab282dc.md#R-02 rev 1`.

`D-03`: **The threshold is strict — `sale_total > 500`, so a sale of exactly 500.00 is not flagged.** "Over
$500" excludes the value 500 itself; the seed carries a row at exactly 500.00 precisely to hold this boundary.
Cites `docs/requirement/2026-09-21-new-intent-eab282dc.md#R-03 rev 1`.

`D-04`: **The flag is emitted as `false`, never `NULL`, when `sale_total` is null or the comparison is unknown.**
A bare `sale_total > 500` would propagate `NULL`, and the requirement makes a null flag a contract violation.
The condition is therefore written as a `case` that yields `true` or `false` and nothing else, which makes the
flag's nullability independent of the source's — the source columns are declared `NOT NULL` in production, but
this model does not rely on that to hold its own contract. Cites
`docs/requirement/2026-09-21-new-intent-eab282dc.md#R-01 rev 1`.

`D-05`: **The model reads `source('raw','sales')` directly rather than `ref`-ing the existing `stg_raw__sales`.**
The requirement states the model is built over the sales source table, and a staging model that reads another
staging model is the dependency shape this project's `dbt_project_evaluator` audit flags
(`fct_staging_dependent_on_staging`). Reading the source keeps the dependency graph staging→source and lets
this model be built and tested against the source alone. Cites
`docs/requirement/2026-09-21-new-intent-eab282dc.md#R-01 rev 1`.

`D-06`: **The output carries the source's columns under the same renamed staging contract as `stg_raw__sales`**
— `id` as `sale_id`, `sale_date` cast to a date, the remaining source columns passed through — plus the two
columns this model exists to add. Two staging models over one source with two different shapes would make every
consumer carry both contracts, so the existing staging shape is reused rather than reinvented. Cites
`docs/requirement/2026-09-21-new-intent-eab282dc.md#R-01 rev 1`.

`D-07`: **The flag column is named `is_over_500`**, following this domain's `is_{condition}` boolean convention
in `AGENTS.md`. The requirement does not name the column, so the convention selects it.

`D-08`: **The model marks rows; it does not filter them.** Every source row is retained and the flag carries the
threshold outcome, so a consumer that wants only flagged sales filters downstream, and the population stays
1:1 with the source. Cites `docs/requirement/2026-09-21-new-intent-eab282dc.md#R-03 rev 1`.

`D-09`: **The model keeps the name `stg_sales_flagged`, which departs from this repo's
`stg_{source}__{table}` convention** (the existing models are `stg_raw__sales` and `stg_raw__customers`). The
user named the artifact explicitly, so the supplied name is kept rather than normalized. Cites
`docs/requirement/2026-09-21-new-intent-eab282dc.md#R-01 rev 1`.

## Rejected

- **Placing the flag in a mart.** The layering convention points that way, but the user asked for a staging
  model by name and kind; recorded as `D-01` rather than silently relocated.
- **`ref('stg_raw__sales')` to inherit its renames and date cast.** Rejected in `D-05`: it makes a staging model
  depend on another staging model, which the project's evaluator audit flags, and it would tie this model's
  build to a second model when its source is one table.
- **Parameterizing the 500 threshold as a dbt `var`.** No requirement asks for a configurable threshold, and a
  variable becomes an interface that consumers then depend on. The literal is recorded here so the next intent
  that genuinely needs configurability knows it was considered.
- **Re-shaping the seed to mirror production's `prd.raw.sales` columns** (`sale_id`, `product_sku`, `sale_ts`,
  no `region`). Offered and declined: it would change the source contract in `sources.yml` and break
  `stg_raw__sales` and `stg_raw__customers`, which select `id`, `product`, `sale_date` and `region`.
- **Filtering to flagged rows only.** Rejected in `D-08`: "flags" marks, and filtering would make the model's
  population differ from its source.

## Rerun behaviour

Deterministic and idempotent. The model is a view over a seed relation, so every query recomputes it from the
seed's current contents: the same input always yields the same 10 rows and the same flag values, nothing is
appended, and no key can be duplicated by a rerun. Rebuilding the seed changes the output only if the seed's
rows change.

## Consumers

None known yet. The model is new, no exposure, semantic model or `CONTEXT.md` entry names it, and the
requirement records no named consumer. A later contract change to this model is therefore unconstrained by
known consumers today — which is a reason to check the DAG rather than assume none exist by the time one does.

## Supporting evidence

- `docs/design/data-slices/2026-09-21-new-intent-eab282dc-slice.md` — readiness **ready** for both deliverables;
  establishes the complete-table slice, the boundary coverage (500.00 / 540.00 / 600.00 against 7 rows below),
  and the recorded limitation that the seed carries no fractional-cent row.
- Seed profile, this session — 10 rows, 0 duplicate rows, 0 nulls in every column, `id` unique (ratio 1.0),
  `quantity` int 3–20, `unit_price` int 25/40/60, `sale_date` 2024-01-10 → 2024-06-01.
- `transformation/models/staging/sources.yml` and `transformation/dbt_project.yml` — the declared `raw.sales`
  contract, the `staging: +materialized: view` setting, and the `stg_{source}__{table}` naming convention.
- `/cache/prod-target/manifest.json` — the CD-published production manifest (invocation `4d4833e6-0f67-478e-9661-751546141ca2`,
  generated 2026-09-18). `stg_sales_flagged` is absent from it and no model in the project carries an enforced
  contract, so this intent's change is purely additive: no column is removed and no type changes, and there is
  no breaking contract delta to resolve.

## Gotchas

- **`sale_total` reads like a source column and is not one.** It is computed in the model from `quantity` and
  `unit_price`; a reader who greps the source contract for it will find nothing.
- **The seed cannot prove the cents cases.** Its `unit_price` is whole dollars, so `sale_total` never carries
  cents, while production's `unit_price` is `DECIMAL(10,2)`. `499.99` and `500.01` therefore have to come from
  unit-test fixtures with explicit literals, not from source data.
- **The seed's row 6 sits exactly on the threshold** at 500.00 and is *not* flagged. That is correct behaviour
  under `D-03`, and it is the row most likely to be mistaken for a bug when someone eyeballs the output.
- **This project's source contract is not production's shape.** The declared `raw.sales` (with `region`,
  `sale_date`) and the live `prd.raw.sales` (`product_sku`, `sale_ts`, no `region`) disagree; the model is built
  against the project's contract, per the greenfield direction.

## History

- `new-intent-eab282dc`, 2026-09-21 — record created with the model's first design: staging placement, derived
  `sale_total`, strict threshold, never-null flag, direct source dependency, reused staging column contract,
  `is_over_500` naming, mark-don't-filter population, and the supplied model name. Added `D-01`–`D-09`.
