---
kinds: [transformation]
---

# Intent: Flag sales over $500 in a new staging model `stg_sales_flagged`

## Classification

- **Action:** `work`.
- **Kinds:** `[transformation]` — the deliverables are a dbt seed and a dbt model, both artifact families that kind owns (`lib/kinds/registry.json`); one kind, so no composition applies.
- **Objective:** provide source data for `raw.sales`, then add one staging model that flags sales over $500.
- **Destination:** this domain repository, MotherDuck.
- **Rationale:** `transformation` — a seed and a model are relations in the analytical layer, which is that family's product.

## Goal

Give consumers of the `sales` source one relation that identifies high-value sales (over $500), so each consumer need not re-derive the line total. No consumer is named yet.

## Source system

**Greenfield, by user direction.** The user directed that this project be treated as greenfield ("ok let's treat this a greenfield project"), so the source data comes from a dbt seed rather than the domain table. That resolves the read-path question raised in the previous capture: the domain database is not read.

**Verified warehouse facts** (retained as context, not as a dependency):

- Domain database `prd` holds one table, `raw.sales` (schema `raw`): `sale_id` INTEGER, `customer_id` INTEGER, `product_sku` VARCHAR, `quantity` INTEGER, `unit_price` DECIMAL(10,2), `sale_ts` TIMESTAMP — none nullable.
- That table does **not** match the contract this project declares. `transformation/models/staging/sources.yml` declares source `raw` with `schema: main` and columns `id`, `customer_id`, `product`, `quantity`, `unit_price`, `sale_date`, `region`, matching `transformation/seeds/sales.csv`. Production parity (`sale_id`/`product_sku`/`sale_ts`, and no `region`) is therefore a real divergence, but it is **not in this intent's scope** under the greenfield direction.
- Ephemeral workspace `ephm_motherduck_01_new_intent_eab282dc` holds zero tables. Studio's launch disposition is `bootstrap` (revision `e6a9015a-2900-493d-a0fe-09b1bc79d631`) — a new workspace, nothing previously written — read and marked handled.

**The seed that backs the source already exists.** `transformation/seeds/sales.csv` declares the same columns as the source contract and builds to `main.sales`, which is exactly the relation `{{ source('raw','sales') }}` resolves to (source `raw`, `schema: main`). It carries 10 data rows, and their `quantity * unit_price` totals already straddle the R-03 threshold: 250.00, 200.00, 200.00, 180.00, 480.00, **500.00**, 420.00, **600.00**, 150.00, **540.00** — one row exactly at 500.00 (false under a strict `>`), two above it, seven below. `transformation/seeds/customers.csv` backs `raw.customers` the same way.

## Target

- Platform: MotherDuck.
- Sandbox destination: `ephm_motherduck_01_new_intent_eab282dc` — the Intent's ephemeral workspace, the only place this work writes data. The Domain database `prd` is read-only and is never written.
- Production: the intent branch PR, published through the platform's git path.

## Deliverables inventory

| # | Deliverable | Kind | Requirement refs | Notes |
| --- | --- | --- | --- | --- |
| 1 | `sales` seed backing `raw.sales` | `seed` | R-04@1 | Greenfield source data. **An existing seed already satisfies this outcome** — see Open questions; no new file is authored unless the shape decision says otherwise. |
| 2 | dbt model `stg_sales_flagged` | `model` | R-01@1, R-02@1, R-03@1 | Staging model over `source('raw','sales')`. `AGENTS.md` places business logic in marts — see Design pending. |

## Requirements

| ID | Revision | Requirement | Acceptance criteria | Source | Resolution | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R-01 | 1 | Build staging model `stg_sales_flagged` over the `sales` source table, exposing a `sale_total` measure and a boolean flag marking sales over $500. | The model exists and reads the `sales` source relation; its output carries `sale_total` and the flag column; population is 1:1 with that source — every source row retained, none added, none dropped; grain is one row per sale key; the flag is a boolean that is never null. | Request: "Add a staging model `stg_sales_flagged` that flags sales over $500 from the sales source table" | supplied decision | pending |
| R-02 | 1 | `sale_total` is a **derived** measure equal to `quantity * unit_price`. It is not a source column, and no source column may be presented as holding it. | Model SQL computes `quantity * unit_price` as `sale_total`; the source relation is never referenced by a `sale_total` identifier; the model's documentation states that `sale_total` is derived. | User answer this session (`sale_total_definition = derive_line_total`), against verified evidence that no total column exists in `sources.yml`, `seeds/sales.csv`, or the live `prd.raw.sales` | user decision | pending |
| R-03 | 1 | The flag is true exactly when `sale_total` is strictly greater than 500. | Boundary cases: `sale_total` 499.99 → false, 500.00 → false, 500.01 → true. The condition marks rows; it does not remove them. | Request wording "over $500", taken literally — "flags" admits one reading, so it is not asked about | supplied decision | pending |
| R-04 | 1 | Provide the `sales` seed that backs `source('raw','sales')`, so `stg_sales_flagged` can be built and exercised greenfield without depending on the domain table. | `dbt seed` materializes the seed as `main.sales` in the effective target; the seed's columns agree with the `sales` source contract in `sources.yml`; the data exercises the R-03 boundary — at least one row exactly 500.00, at least one above, at least one below. | User request this session: "compose a dbt seed for the raw.sales table", under the greenfield direction | supplied decision | pending |

## Out of scope

- No mart and no intermediate model. The objective needs neither orchestration nor a semantic-model artifact, so `kinds:` stays `[transformation]`.
- **Production parity of the seed is out of scope.** The greenfield direction sets aside the divergence between `prd.raw.sales` (`sale_id`, `product_sku`, `sale_ts`, no `region`) and the declared contract. Re-shaping the seed to mirror production would change `sources.yml` and so affect `stg_raw__sales` and `stg_raw__customers`, which select `id`, `product`, `sale_date` and `region` — it returns here as a requirement delta for approval before adoption.
- `stg_raw__sales` and its tests are **not modified**; the `sales` columns declared in `sources.yml` are **not changed**.
- The model does not filter its population.
- Currency conversion and rounding policy are not addressed.
- Re-cloning or reprovisioning the ephemeral workspace is not part of this intent's work; see Open questions.

## Open questions

- **Seed shape — the one open decision.** The requested seed already exists and already satisfies R-04's outcome, so "compose a seed" resolves to one of: use the existing `seeds/sales.csv` unchanged (no new artifact); extend its rows while keeping the declared columns; or re-shape it to mirror `prd.raw.sales`, which is a breaking contract change with the impacts listed under Out of scope. Put to the user; work that depends on it is held.
- **No material question is open on the model itself.** The outcome, its measure and its threshold are settled by the request and the user's answer.
- **Re-clone request could not be executed** (user request: "re-clone the ephemeral db from production/domain database"). No capability available to this session clones or reprovisions an ephemeral workspace: `load_tabular_to_ephemeral` loads a local file into the ephemeral workspace and can never target the domain, and the remaining capabilities are read-only inspection. The recovery skill executes no sandbox work, and the disposition is `bootstrap` (nothing previously written), so there was no prior work to route. Reported rather than emulated with a hand-rolled cross-database copy. Superseded in effect by the greenfield direction, which removes the need for the domain table.
- No take-it-as-is was requested, and none is needed.

## Design pending

Technical decisions for Design — never asked at intent:

- **Seed artifact handling** follows from the Open question above: whether the seed row is authored anew, extended, or left alone, and — if extended — whether the added rows stay strictly additive so `stg_raw__sales`'s existing behaviour is preserved.
- **Layer conflict (surface it, do not pass over it).** `AGENTS.md` defines staging as "1:1 with source tables, rename columns, filter soft-deletes" and places business logic in marts. A derived measure plus a threshold flag in a staging model departs from that. The explicit user requirement outranks the convention and the user typed the artifact as staging, so the deviation is deliberate — record it rather than silently normalizing it.
- **Model naming.** `stg_sales_flagged` departs from this repo's `stg_{source}__{table}` convention (existing: `stg_raw__sales`, `stg_raw__customers`). The user named it explicitly; keep the supplied name.
- **Dependency.** Read `source('raw','sales')` directly — the literal reading of "from the sales source table" — versus `ref('stg_raw__sales')`, which would inherit that model's renames and date cast for free and would introduce a second staging model over one source.
- **Grain key and column naming.** The declared contract calls the key `id`; the real table calls it `sale_id`. Settle which the model's output follows.
- **Flag column name.** Proposed `is_over_500`, following `AGENTS.md`'s `is_{condition}` boolean convention.
- **Materialization.** `dbt_project.yml` sets `staging: +materialized: view`; confirm the model inherits it.
- **Type and rounding** of `sale_total` (`quantity` INTEGER × `unit_price` DECIMAL(10,2)).
- **Tests.** Which unit and data tests to attach, including a boundary test at exactly 500.00 keyed to the existing seed row.
- **Not-applicable interview branches, with reasons.**
  - *Unmatched and null keys* — not applicable: a 1:1 staging view performs no join, carries no dimensional key, and feeds no dated aggregate.
  - *Consumers* — `not applicable — no named consumer yet`.
  - *SLAs / freshness* — `not applicable — on demand`.
  - *Extended scope* — not applicable: the objective requires neither orchestration nor a semantic model.
  - *Grain* — derived, not asked: one row per source sale.

## Change history

- 2026-09-21 — initial capture: R-01@1, R-02@1, R-03@1.
- 2026-09-21 — **superseded request recorded.** The first request this session asked for `stg_orders_flagged` over an `orders` source. It was replaced before any artifact was written: no `orders` source exists in this project, and no Requirement revision was ever created for it.
- 2026-09-21 — **correction of a wrong finding.** The initial capture asserted no `sales` relation existed anywhere, based on schema reads that were in fact returning the attached `sample_data` share rather than the domain database. Re-checked against real coordinates, `prd` now holds `raw.sales`, confirming the user's report of a refresh. Corrected in `## Source system`; the requirement statements were unchanged by that correction.
- 2026-09-21 — **greenfield direction and seed deliverable added.** The user directed that the project be treated as greenfield and asked for a dbt seed for `raw.sales` to build the model from. Recorded as R-04@1 and as a supplied decision resolving the read path away from the domain table. Inspection found the requested seed already exists at `transformation/seeds/sales.csv`, already backs `source('raw','sales')`, and already covers the R-03 boundary — so the deliverable's outcome is met and its shape is the single open decision. R-01@1, R-02@1 and R-03@1 are unchanged.

## Change impact

- **Additive only, as specified.** Deliverable 1 requires no schema change to the seed; deliverable 2 adds one model. No existing model, test or source declaration is modified, and `stg_raw__sales` is untouched.
- **No-impact rationale:** the seed keeps its declared columns and the model is new with no consumer, so nothing downstream of the existing models is affected. If the seed is instead re-shaped to production columns, that impact returns here for approval first.
- **Conditional impact, not authorised:** re-shaping the seed or repointing source `raw` changes what `stg_raw__sales` and `stg_raw__customers` read, and those models select `id`, `product`, `sale_date` and `region`. Such a change requires a requirement delta and approval; affected design decisions and completed tasks would be marked `needs review`.

## Approvals

- Pending — no requirement approval recorded yet.
- **Ship authorization was not carried over.** The earlier instruction "Ship it once it's good to go" was attached to the superseded `stg_orders_flagged` request, and the user replaced that request without repeating it. Shipping is therefore unauthorized by the current request and will be asked for at the ship stop, which is a hard stop.
