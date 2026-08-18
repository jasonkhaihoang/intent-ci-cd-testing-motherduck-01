# Plan: stg_customers staging model from a raw_customers seed

**Goal:** Add a small, verifiable dbt staging model (`stg_customers`) that reads a `raw_customers` seed and applies a trivial transform, with passing `not_null`/`unique` tests, on MotherDuck.

**Architecture:** A dbt seed `raw_customers` (5–10 rows) feeds a single staging view `stg_customers` (`cast signup_date as date`, `upper(country)`), materialized per the project's existing `staging: +materialized: view` config and built with `dbt build` against the MotherDuck ephemeral sandbox.

**Tech Stack:** dbt-core + dbt-duckdb (MotherDuck), DuckDB SQL.

## Global Constraints

- Platform: MotherDuck (`VD_DOMAIN_DATA_PLATFORM=motherduck`). Domain database is read-only; every write goes to the ephemeral sandbox `md:$VD_EPHM_MOTHERDUCK_DATABASE` (schema `$VD_EPHM_SCHEMA`, `main`). Never run `--target prod`.
- dbt project lives at `/workspace/transformation` (`dbt_project.yml`, profile `dbt_motherduck`, target `dev`). Run `dbt` plainly via the credential-injecting `dbt` shim — never `source /opt/runtime/bin/activate && dbt` or `uv run dbt` (those get no MotherDuck credential).
- Staging materialization is `view` (from `dbt_project.yml` `models.motherduck_domain_01.staging.+materialized: view`).
- Naming: seed-fed staging models use a literal name (ADR `docs/adr/0001-staging-model-naming-for-seed-fed-models.md`). Model `stg_customers`; seed `raw_customers` (drop the `raw_` prefix).
- Grain: `stg_customers` is one row per customer, keyed by `id`.
- Transform: `cast(signup_date as date)`, `upper(country)`, pass `id` and `name` through unchanged.
- Tests are Tier-1 data tests only — `not_null(id)` and `unique(id)`. No unit tests: this is a pure cast/rename staging model (`dbt-unit-testing` skips pure cast staging).
- Seed contents: 5–10 rows; columns `id`, `name`, `signup_date`, `country`; non-null unique integer `id`; `signup_date` in ISO `YYYY-MM-DD`; `country` lowercase (so `upper()` has a visible effect).
- Runtime-audit control columns (`_loaded_at`, `_dbt_invocation_id`, `_git_sha`) do NOT apply — `stg_customers` is a staging view, not a mart/gold model.

---

## Tasks

### Task 1: `raw_customers` seed (input)

**Files:**

- Create: `transformation/seeds/raw_customers.csv`

**Interfaces:**

- Consumes: nothing.
- Produces: `raw_customers` seed relation (columns `id` INTEGER, `name` VARCHAR, `signup_date` DATE/VARCHAR, `country` VARCHAR) in the sandbox — later consumed by `stg_customers` via `{{ ref('raw_customers') }}`.

- [x] **Step 1: Author the seed CSV**

Write `transformation/seeds/raw_customers.csv` with a header row `id,name,signup_date,country` and 5–10 data rows: integer `id` (1..N, unique, non-null), a non-empty `name`, `signup_date` as `YYYY-MM-DD`, and lowercase `country`.

- [x] **Step 2: Load the seed into the sandbox**

Run: `cd /workspace/transformation && dbt seed --select raw_customers --target dev && python /data/default-plugins/vibedata-data-engineering/0.45.2/scripts/ephemeral_workspace_marker.py init`

Expected: exit 0; dbt reports `raw_customers` seeded with the authored row count.

- [x] **Step 3: Commit**

```bash
git add transformation/seeds/raw_customers.csv
git commit -m "feat: add raw_customers seed"
```

### Task 2: `stg_customers` model + schema tests

**Files:**

- Create: `transformation/models/staging/stg_customers.sql`
- Create: `transformation/models/staging/schema.yml`

**Interfaces:**

- Consumes: `raw_customers` seed (from Task 1) via `{{ ref('raw_customers') }}`.
- Produces: `stg_customers` staging view (columns `id`, `name`, `signup_date` DATE, `country` UPPERCASED) and its `schema.yml` tests.

- [x] **Step 1: Author the model SQL and schema YAML**

Write `transformation/models/staging/stg_customers.sql` selecting `id`, `name`, `cast(signup_date as date) as signup_date`, `upper(country) as country` from `{{ ref('raw_customers') }}` (explicit column list, no `SELECT *`). Write `transformation/models/staging/schema.yml` declaring model `stg_customers` with `not_null` and `unique` tests on column `id`.

- [x] **Step 2: Compile check (generating-dbt-model gate)**

Run: `cd /workspace/transformation && dbt compile --select stg_customers`

Expected: exit 0; the model compiles with no column-resolution or contract errors.

- [x] **Step 3: Sandbox build (running-dbt-in-sandbox gate)**

Run: `cd /workspace/transformation && dbt build --select stg_customers --target dev && python /data/default-plugins/vibedata-data-engineering/0.45.2/scripts/ephemeral_workspace_marker.py init`

Expected: exit 0; dbt reports the `stg_customers` view created and its `not_null`/`unique` tests passed.

- [x] **Step 4: Test gate (dbt-unit-testing)**

Run: `cd /workspace/transformation && dbt test --select stg_customers`

Expected: exit 0; `not_null_stg_customers_id` and `unique_stg_customers_id` both pass.

- [x] **Step 5: Commit**

```bash
git add transformation/models/staging/stg_customers.sql transformation/models/staging/schema.yml
git commit -m "feat: add stg_customers staging model and tests"
```

## Execution evidence

- [x] Task 1: `dbt seed --select raw_customers --target dev` — exit 0 — `transformation/seeds/raw_customers.csv` — sha256:f3532495c8cef50362902fd51d1039d979a0cd1fa65334d5fbd77b978faf9d05 (8 rows loaded; 8 distinct, 8 non-null ids)
- [x] Task 2: `dbt test --select stg_customers` — exit 0 — `transformation/models/staging/stg_customers.sql` (sha256:824ff5c71319a3a2dc1e12e73d6051a1d40270156bb82a6556b07c40c449e297) + `schema.yml` (sha256:c597a3c5711cec7192aaec273c753d1499aee01957eb3e49556c818c9d59f561) — compile exit 0, `dbt build --select stg_customers --target dev` exit 0 (view created), `not_null`+`unique` on `id` PASS; 8 rows, `signup_date` DATE, `country` uppercased
