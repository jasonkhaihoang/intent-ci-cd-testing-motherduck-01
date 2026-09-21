# Plan: Flag sales over $500 in `stg_sales_flagged`

The Plan artifact carries this intent's own scope and its progress — task checkboxes plus per-task
`## Execution evidence`. Durable per-artifact decisions live in the design records this plan links.

**Goal:** Add a staging model `stg_sales_flagged` that exposes a derived `sale_total` and a never-null boolean
flag marking sales over $500, built greenfield over the `raw.sales` seed.

**Approach:** Two deliverables, one of which is already satisfied. The `sales` seed exists and already backs
`source('raw','sales')`, so the work is to materialize it into the sandbox and then generate one staging view
over it. Nothing existing is modified: the model reads `source('raw','sales')` directly rather than `ref`-ing
`stg_raw__sales`, so the only new DAG edge is source → new model.

**Tech Stack:** dbt-core 1.12.5 on the `dbt-duckdb` adapter, target MotherDuck. No new packages.

## Global Constraints

Copied verbatim from the resolved Requirement and design records; every task implicitly includes these.

- **Platform:** MotherDuck. The sandbox destination is the runtime-declared ephemeral database
  (`VD_EPHM_MOTHERDUCK_DATABASE`); the Domain database is read-only and is **never** written.
- **Materialization:** the model is a staging model, so `dbt_project.yml`'s `staging: +materialized: view`
  applies.
- **Naming:** the model keeps the supplied name `stg_sales_flagged` (D-09); the flag column is `is_over_500`
  (D-07); the source key `id` is presented as `sale_id` (D-06).
- **Measure:** `sale_total` is `quantity * unit_price`, computed and never sourced; it is left **uncoerced**, so
  it is null when either input is null (D-02, D-10).
- **Threshold:** strictly `sale_total > 500` — a sale of exactly 500.00 is **not** flagged (D-03). Written as a
  literal, not a dbt `var`.
- **Flag contract:** `is_over_500` is always `true` or `false`, never null, including when `sale_total` is null
  (D-04).
- **Population:** 1:1 with the source. Every source row is retained; the flag marks, it does not filter (D-08).
- **Dependency:** read `source('raw','sales')` directly. Do **not** `ref('stg_raw__sales')` (D-05).
- **Delivery:** product code stays environment-agnostic — no `dev_mode`, no hardcoded `VD_EPHM_*` IDs, no
  profile `target` pinned to one environment, no `.add_limit()`.
- **Required tests** (`AGENTS.md`): `not_null` and `unique` on the primary key, presented as `sale_id`.

---

## Scope and impact

| Artifact | Kind | Layer | Action | requirements and acceptance criteria | Design record | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `sales` (seed) | seed | n/a | **none — existing artifact reused unchanged** | `R-04@1` | — `code is contract` | Backs `source('raw','sales')`. Outcome already met: 10 rows, declaring the same columns as the source contract. No file is authored or modified; the task materializes it into the sandbox so `R-04@1` has gate evidence. |
| `stg_sales_flagged` | model | staging | create | `R-01@1`, `R-02@1`, `R-03@1` | [`stg_sales_flagged.md`](../design/models/stg_sales_flagged.md) D-01–D-10 | One row per source sale, unique on `sale_id`; adds `sale_total` and `is_over_500`. |

**Source mapping.** `transformation/seeds/sales.csv` → `dbt seed` → `main.sales` in the ephemeral destination →
`source('raw','sales')` → `stg_sales_flagged` (staging view). The mapping is one hop into staging and stops
there; no intermediate or mart layer is in scope.

**Change impact.** Established from the compiled dependency graph in the CD-published production manifest at
`/cache/prod-target/manifest.json`, not from reading model files. `source.motherduck_domain_01.raw.sales` has
exactly one child today, `stg_raw__sales`; `stg_raw__sales` has no model children, only its own two tests;
`raw.customers` likewise feeds only `stg_raw__customers`. The project declares no exposures and no semantic
models. The new model adds a second child of the `raw.sales` source and nothing references it.

| Model | Layer | Bucket | Anticipated Change | Notes |
| --- | --- | --- | --- | --- |
| `stg_raw__sales` | staging | shared upstream | **No change expected.** It shares the `raw.sales` source with the new model, but neither its SQL nor its YAML is modified, and the seed it reads is untouched. The new model depends on the source, not on this model. | Reads the same source; unmodified. Its two tests are unaffected. |
| `stg_raw__customers` | staging | — | **No change expected.** Different source (`raw.customers`), untouched by this intent. | Listed for completeness; no dependency on the new model either way. |

No existing artifact is impacted: this intent creates one new relation and modifies none. The `sales` seed is
not a changed artifact, so `R-04@1`'s coverage is its materialization gate rather than a diff.

---

## Tasks

### Task 1: Materialize the `sales` seed in the sandbox

**Requirement refs:** `R-04@1`

**Files:**

- Create: none — this task changes no repository file. Its commit is the `## Execution evidence` line below.
- Modify: none.

- [x] **Step 1: Materialize the seed into the sandbox**
      Invoke `running-dbt-in-sandbox` to run `dbt seed` against the dev target for the `sales` seed.
- [x] **Step 2: Confirm the seed landed as the source relation**

Run: the sandbox-run skill's own `dbt seed --select sales` command against the dev target

Expected: exit 0, with `Completed successfully` and a seed insert reported for `sales`. Then the relation
`main.sales` exists in the ephemeral destination and holds **10** rows, and its columns are
`id, customer_id, product, quantity, unit_price, sale_date, region` — matching the `sales` source contract in
`transformation/models/staging/sources.yml`.

- [x] **Step 3: Commit the evidence line**

```bash
command git add docs/plans/2026-09-21-new-intent-eab282dc.md
command git commit -m "Materialize the sales seed in the sandbox"
```

### Task 2: Generate and build `stg_sales_flagged`

**Requirement refs:** `R-01@1`, `R-02@1`, `R-03@1`

**Files:**

- Create: `transformation/models/staging/stg_sales_flagged.sql`
- Modify: `transformation/models/staging/schema.yml` (add the model's entry: description, columns, and the
  `not_null` / `unique` tests on `sale_id`)

- [ ] **Step 1: Generate the model**
      Invoke `generating-dbt-model` for the `stg_sales_flagged` row. It writes the SQL selecting from
      `{{ source('raw','sales') }}` and exposes `sale_total` as `quantity * unit_price` plus `is_over_500` as a
      `case` that returns `true` or `false`, per D-02, D-03, D-04 and D-10, and adds the model's properties to
      `schema.yml`.
- [ ] **Step 2: Build the model in the sandbox**
      Invoke `running-dbt-in-sandbox` to build it against the dev target.

Run: the sandbox-run skill's own `dbt build --select stg_sales_flagged` command against the dev target

Expected: exit 0, the model created as a **view** (not a table), and its build reports success. Independent
checks on the built relation: **10** rows — one per source sale, no source row added or dropped; 2 rows with
`is_over_500 = true` (`sale_id` 8 and 10, at 600.00 and 540.00); 1 row with `is_over_500 = false` at exactly
500.00 (`sale_id` 6); the remaining 7 false; and `is_over_500` null in 0 rows.

- [ ] **Step 3: Commit the model and its properties together**

```bash
command git add transformation/models/staging/stg_sales_flagged.sql transformation/models/staging/schema.yml
command git commit -m "Add stg_sales_flagged staging model with derived sale_total and over-500 flag"
```

### Task 3: Unit and data tests for `stg_sales_flagged`

**Requirement refs:** `R-01@1`, `R-03@1`

**Files:**

- Modify: `transformation/models/staging/schema.yml` (add `unit_tests:` for the model, alongside the data tests
  from Task 2)

- [ ] **Step 1: Author the tests**
      Invoke `dbt-unit-testing` to declare, for `stg_sales_flagged`:
      a unit test over explicit input rows pinning the threshold boundary — `sale_total` 499.99 → `false`,
      500.00 → `false`, 500.01 → `true` — because the seed carries no fractional-cent row and cannot exercise
      those two cases; and a unit test pinning the never-null contract with a null `quantity` or `unit_price`
      input → `is_over_500 = false` while `sale_total` itself is null, per D-04 and D-10. Plus the data tests
      `not_null` and `unique` on `sale_id`.
- [ ] **Step 2: Run the tests — the deterministic gate**

Run: the sandbox-run skill's own `dbt test --select stg_sales_flagged` command against the dev target

Expected: exit 0, `PASS=4` — two unit tests and two data tests — with no failures, errors or warnings: unit
test on the 499.99 / 500.00 / 500.01 boundary cases, unit test on the null-input cases, `not_null` on
`sale_id`, and `unique` on `sale_id`. A test that fails the boundary (for instance flagging exactly 500.00) is
a real finding against `R-03@1`, not a test to relax.

- [ ] **Step 3: Commit the tests**

```bash
command git add transformation/models/staging/schema.yml
command git commit -m "Add boundary and null-contract tests for stg_sales_flagged"
```

## Execution evidence

Append-only — one line per task, in task order, appended only when that task's checkbox flips (artifact on disk
plus a green deterministic gate).

- [x] Task 1: `dbt deps` → exit 0 (5 packages installed; `dbt_packages/` was empty, so the gate could not run without it). Gate `dbt seed --select sales --target dev --warn-error-options '{"error":["NoNodesForSelectionCriteria"]}'` → exit 0, `Completed successfully`, `loaded seed file main.sales` **INSERT 10**; dbt's own output reports destination database `ephm_motherduck_01_new_intent_eab282dc`, schema `main` (the ephemeral sandbox, not `prd`). Relation shape from `SUMMARIZE main.sales`: exactly 7 columns `id, customer_id, product, quantity, unit_price, sale_date, region` — matching the `sales` source contract in `sources.yml` — with `count` 10 and `null_percentage` 0.00 on every column. Source file `transformation/seeds/sales.csv` sha256 `e19c7a1e1889501113307357de2a18b5f9a16c234c04e47cd99f39d79ddb8870`. No repository file changed by this task.
- [ ] Task 2: pending
- [ ] Task 3: pending

## Approvals

None. No breaking-contract delta was identified during verify, so this section's one case does not apply:
intent approval and the design stop are recorded in the Requirement artifact, and certification and ship
approval belong to the Certification artifact.
