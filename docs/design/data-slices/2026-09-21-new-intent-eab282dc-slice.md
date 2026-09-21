# Data slice — `stg_sales_flagged` and its `sales` seed

Supporting design evidence for the approved requirement revisions `R-01@1, R-02@1, R-03@1, R-04@1` in
`docs/requirement/2026-09-21-new-intent-eab282dc.md`. This is not a second requirement record.

Sizing trace: the intents' source is greenfield by user direction, so the only input is the committed seed
`transformation/seeds/sales.csv`, which builds to `main.sales` — the relation `{{ source('raw','sales') }}`
resolves to. The domain table `prd.raw.sales` was deliberately **not** selected: the greenfield direction
removed it from scope, so no slice is drawn from it.

## Deliverable 1 — `sales` seed backing `raw.sales` (R-04@1)

- **Candidate:** `transformation/seeds/sales.csv`, 10 data rows, 7 columns.
- **Slice:** **complete table** — the input is small (10 rows), so nothing is sampled or stratified.
- **Evidence:** profile of the seed, this session: 10 rows, 0 duplicate rows, unique row ratio 1.0, 0 nulls in
  every column; `id` int with 10 distinct values (ratio 1.0); `quantity` int 3–20; `unit_price` int 25/40/60;
  `region` 3 distinct (US 6, CA 2, DE 2); `product` 3 distinct (Widget A 4, Widget B 3, Widget C 3).
- **Joins:** none.
- **Readiness:** **ready.** No source gap.

## Deliverable 2 — `stg_sales_flagged` (R-01@1, R-02@1, R-03@1)

- **Candidate:** the same seed relation at the required grain. It is already one row per sale and retains both
  measure components (`quantity`, `unit_price`) that R-02's derived measure needs, so the accepted measure can
  be reproduced exactly at the target grain without re-aggregation.
- **Slice:** **complete table** — all 10 rows, which is the whole population.
- **Boundary coverage** (`sale_total` = `quantity × unit_price`), against R-03's strict `> 500`:

  | Row | `id` | `quantity` × `unit_price` | `sale_total` | R-03 flag |
  | --- | --- | --- | --- | --- |
  | 6 | 6 | 20 × 25.00 | **500.00** | `false` — the exact-boundary case |
  | 8 | 8 | 15 × 40.00 | 600.00 | `true` |
  | 10 | 10 | 9 × 60.00 | 540.00 | `true` |
  | 1,2,3,4,5,7,9 | — | — | 250, 200, 200, 180, 480, 420, 150 | `false` |

  So the slice carries 2 rows above the threshold, 1 row exactly on it, and 7 below — the boundary is
  represented on both sides by real rows.
- **Joins:** none. The model is 1:1 over its source, so there is no join expectation to establish.
- **Export shape:** not applicable — the build input is the seed relation itself, read whole. No bounded export
  or subset query is prescribed.
- **Readiness:** **ready**, with one recorded coverage limitation (below).

## Observable limitations

- **No fractional-cent row.** `unit_price` in the seed is whole dollars only, so `sale_total` never carries
  cents. R-03's acceptance cases `499.99` and `500.01` therefore have **no corresponding source row** and must
  be exercised by `dbt-unit-testing` fixtures with explicit literals, not by slice data. This is a limitation of
  the input, not a business decision, and it does not block the slice.
- **Production carries a wider type.** The real `prd.raw.sales.unit_price` is `DECIMAL(10,2)`, so cents are
  possible in production while the seed cannot represent them. Recorded because it bounds what the seed can
  prove about the rule.
- **Static data, no freshness anchor.** A seed has no ingestion cadence, so no freshness threshold applies and
  none is invented. R's SLAs are `not applicable — on demand`.

## Findings against the approved revisions

- `R-01@1` — **confirms.** The slice is 1:1 with its source and every row is retained, which is the population
  the requirement states.
- `R-02@1` — **confirms.** Both components of the derived measure (`quantity`, `unit_price`) are present and
  non-null, so the derivation is computable for every row.
- `R-03@1` — **confirms, with the limitation above.** The threshold boundary is represented by real rows at
  500.00, 540.00 and 600.00.
- `R-04@1` — **confirms.** The existing seed already meets the deliverable's outcome.

No business conflict is returned: nothing in this evidence contradicts an approved revision, and no revision
needs amending.

## Readiness summary

Both deliverables: **ready**. No unresolved source gap blocks design or a build.
