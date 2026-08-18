---
kinds: [transformation]
---

# Intent: Fix CI failures for stg_customers

## Goal

Fix the CI failures on the `stg_customers` staging model from PR #1 so the build is green: repair the sqlfluff indentation violations and convert the `raw_customers` seed into a dbt source model (`src_customers`) so it is part of the deployment-manifest closure and materializes under the CI's model-only `dbt run`.

## Source system

A project-owned source model `transformation/models/staging/src_customers.sql` (columns `id`, `name`, `signup_date`, `country`; 8 rows), feeding `transformation/models/staging/stg_customers.sql`.

## Target

MotherDuck ephemeral sandbox via the `transformation/` dbt project (profile `dbt_motherduck`); the domain database is read-only.

## Objects in scope

- `transformation/models/staging/src_customers.sql` — dbt model (table) replacing the former `raw_customers` seed.
- `transformation/models/staging/stg_customers.sql` — staging view; sqlfluff indentation fixed.
- `transformation/models/staging/schema.yml` — documents both models; `not_null(id)` + `unique(id)` tests on `stg_customers`.
- `docs/adr/0001-staging-model-naming-for-project-owned-source-models.md` — the recorded naming decision, updated for the source-model mechanism.

## Success criteria

- `ci/static-check` passes sqlfluff and the dbt scorecard (no violations).
- `ci/run` builds `src_customers` and `stg_customers` successfully (no `dbt seed` step required).
