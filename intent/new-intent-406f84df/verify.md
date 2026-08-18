# Verify: stg_customers staging model from a raw_customers seed

## Certification

certified — all six Coverage rows are covered by green deterministic gates (`dbt build` and `dbt test` exit 0, project audit `ERROR=0`, dev-artifact scan clean) and the code-reviewer returned APPROVE; propose shipping.

## Coverage

| Source | Item | Covered by | Evidence |
| --- | --- | --- | --- |
| intent.md success criteria | `dbt build` exits 0 (seed loads, model compiles + materializes, tests pass) | Sandbox build gate | `dbt build --select stg_customers --target dev` — exit 0 |
| intent.md success criteria | `raw_customers` holds 5–10 rows; `stg_customers` one row per customer (same count) | Read-only lakehouse query | 8 rows in both `raw_customers` and `stg_customers` |
| intent.md success criteria | `signup_date` is DATE, `country` is uppercase | lakehouse_schema + query | `signup_date` DATE; `country` e.g. `UNITED STATES` |
| intent.md success criteria | `not_null(id)` and `unique(id)` pass | dbt test gate | `dbt test --select stg_customers` — exit 0 (both PASS) |
| intent.md success criteria | Verification returns row count + sample output | Read-only lakehouse query | 8-row sample of `stg_customers` returned |
| design.md Model Inventory | `stg_customers` staging view, grain keyed by `id` | compile + build gates | `dbt compile --select stg_customers` exit 0; view created |

## Gate results

| Gate | Command | Exit code | Outcome |
| --- | --- | --- | --- |
| Golden replay | (no baseline named in `design.md`) | n/a | skipped |
| Project audit | `dbt run --select package:dbt_project_evaluator` then `dbt test --select package:dbt_project_evaluator` | 0 | pass — `ERROR=0`; 8 warnings all from `elementary` package models, none from `stg_customers` |
| Dev-artifact scan | `grep -rnE 'dev_mode\|add_limit\|--target prod' models/ seeds/` | 0 | pass — no hits |
| Clean-diff gate | `git push -u origin HEAD` | 0 | pass — "Everything up-to-date"; no build artifacts on the branch |
| Contract publishing (`publishing-dbt-contracts`) | (not called — staging model, no enforced contract) | n/a | n/a |
| Model documentation (`documenting-dbt-models`) | (already satisfied — `schema.yml` carries model + column descriptions) | n/a | n/a |
| PR open | `gh pr create --base main --head intent/new-intent-406f84df` | 0 | pass — https://github.com/jasonkhaihoang/intent-ci-cd-testing-motherduck-01/pull/1 |

## Reviewer verdicts

```json
{
  "verdict": "APPROVE",
  "summary": "ADR-promotion pass clean: only the stg_customers naming decision clears the bar, and docs/adr/0001-staging-model-naming-for-seed-fed-models.md exists on disk with status: decided, is cited in design.md line 8, is correctly numbered 0001 (sole ADR), and holds only structural facts plus the decision's own subject names (no conversation-derived example value/identifier/row content). Grain, staging-view materialization (verified against dbt_project.yml), seed-over-source rationale, Bronze Adequacy, Change Impact, and scope are all complete and consistent. The mart-layer control-column invariant does not apply (no mart added or changed; staging view only).",
  "issues": [],
  "next_step": "Proceed past the design stop and dispatch planning."
}
```

```json
{
  "verdict": "APPROVE",
  "summary": "stg_customers is a correct 1:1 seed→staging transform. Grain (one row per customer, keyed by id) is preserved and documented in both the SQL header comment and the schema.yml description. The model uses an explicit column list (no SELECT *), CAST(signup_date AS DATE) and UPPER(country) with no joins, no branching, and no business logic. Tier-1 not_null + unique on the grain column id is present and structural (not a mirror of the SQL). No enforced contract, no runtime-audit control columns, and no unit tests are required for a staging view with a pure cast/rename transform, so their absence is correct. ref('raw_customers') is the correct reference for a project-owned dbt seed (source() is inapplicable absent a source system, per design.md and ADR-0001). The seed's 8 rows have unique, non-null integer ids and lowercase ISO-signup dates, so the declared uniqueness/not-null contract holds. sha256 hashes of all three changed artifacts match the plan.md Execution evidence.",
  "issues": [
    {
      "severity": "info",
      "message": "Column list is indented 4 spaces; the SQL style guide specifies 2 spaces per level. Cosmetic only, does not affect correctness.",
      "location": "transformation/models/staging/stg_customers.sql"
    },
    {
      "severity": "info",
      "message": "Only the grain column id carries not_null/unique. The dbt pattern 'always-test-the-pk-at-least-one-non-null-business-column' is a should-do (not a Tier-1 must) and is optional here; a not_null on name would be advisory only and is not required for a seed-fed staging demo.",
      "location": "transformation/models/staging/schema.yml"
    }
  ]
}
```

The code-reviewer's info note on SQL indentation was resolved: `stg_customers.sql` was re-indented to 2 spaces and the model re-built (`dbt build` exit 0, tests PASS).

## Approvals

- [x] User approved ship — 2026-08-18 11:49 (UTC)
