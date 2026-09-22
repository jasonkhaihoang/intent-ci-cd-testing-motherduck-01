# Verify: stg_sales_flagged — flag sales over $500

**Resolved artifact path:** `docs/verify/2026-09-21-new-intent-eab282dc.md` (existing artifact, opened not recreated).
**Revision certified:** `07754c99b87e24821801819ab0439b0ad1b01edd`, merge-base with `origin/main` (`3b063670a772763029bc95cd19d775899497d04d`; `git merge origin/main` → *Already up to date*).
**Target / data:** MotherDuck sandbox `md:ephm_motherduck_01_new_intent_eab282dc`, schema `main`; deferred to `/cache/prod-target`. The Domain database `prd` was never written.

## Certification

`verdict: returned`

Reasoning: two of the three deterministic suites are green and the delivered code is correct, but **`R-03@1` cannot be covered**, because its own acceptance criteria name boundary cases the approved input cannot represent. `R-03@1` reads: *"The flag is true exactly when `sale_total` is strictly greater than 500"*, with acceptance criteria *"`sale_total` 499.99 → false, 500.00 → false, 500.01 → true."* The `500.00 → false` case and the strict-greater semantics are demonstrably covered; `499.99 → false` and `500.01 → true` are not, and cannot be: dbt types unit-test fixture literals from the input relation's column types, and `main.sales.unit_price` is INTEGER, so the cents are destroyed before the model runs. The row is therefore not covered, and a downgraded claim does not advance.

**Primitive to return to: `requirement`.** The acceptance criteria must be restated to the boundary cases the approved source can actually exercise — or a cents-carrying source authorised. The model code, the tests as shipped, and the project configuration are all correct as they stand; this is not a `plan` gap (everything the plan could execute was executed) and not a `design` gap in the approach (staging over the seed, the derived measure, and the never-null `CASE` are all sound and verified).

**Companion finding that must ride the same loop:** `docs/design/models/stg_sales_flagged.md` line 123 asserts *"The seed cannot prove the cents cases … 499.99 and 500.01 therefore have to come from unit-test fixtures with explicit literals, not from source data."* That claim is disproven by the compiled fixture, so that durable record needs a design amendment. Amending it here would be out of stage, so it is left flagged rather than edited.

Nothing in this certification is a defect in what was built: the population is 1:1, the flag is never null, the threshold is strict, and zero rows disagree with an independent recalculation. The failure is one of *provable coverage*, and it returns to the requirement that names the cases.

## Coverage

One row per approved requirement and per Plan scope row, plus the kind's not-applicable `Execution evidence:` line. `R-01@1`–`R-04@1` are the approved revision set (`approved_continue`, 2026-09-21T08:34:45Z); no revision is superseded and no pending change is open. The Requirement artifact's acceptance criteria are carried inside each requirement row, as that artifact holds no separate success-criteria section.

| Source | Item | Covered by | Evidence | At revision |
| --- | --- | --- | --- | --- |
| Requirement artifact requirement | `R-01@1` — staging model over the sales source, exposing `sale_total` and a boolean flag; 1:1 population; one row per sale key; flag never null | Sandbox build gate, manifest identity, independent query | `dbt build --select stg_sales_flagged …` exit 0, `PASS=5`, `OK created sql view model main.stg_sales_flagged`; manifest relation `"ephm_motherduck_01_new_intent_eab282dc"."main"."stg_sales_flagged"`, `materialized` view, 9 columns; independent query → 10 rows, 10 distinct `sale_id`, `n_flag_null` **0**, `n_dropped` 0, `n_extra` 0 | `07754c99b87e24821801819ab0439b0ad1b01edd` |
| Requirement artifact requirement | `R-02@1` — `sale_total` derived as `quantity * unit_price`, never sourced, documented as derived | Compiled SQL inspection, manifest column descriptions, independent recomputation | `quantity * unit_price as sale_total` in the `renamed` CTE; column description *"Computed in this model and never read from the source, which holds no sale-total column under any name"*; `n_mismatch_vs_recalc` **0** against `s.quantity * s.unit_price` | `07754c99b87e24821801819ab0439b0ad1b01edd` |
| Requirement artifact requirement | `R-03@1` — flag true exactly when `sale_total` strictly > 500; acceptance cases 499.99 → false, **500.00 → false**, **500.01 → true** | **NOT COVERED** — 500.00 → false and the strict operator are covered; 499.99 and 500.01 are not exercisable through the approved input | Covered part: `test_sale_total_over_500_flags_only_strictly_over_500` PASS (`5 x 100 = 500` → false; `1 x 501 = 501` → true; `2 x 300 = 600` → true) plus `n_at_500_wrongly_flagged` **0** over the real source. Uncovered part: `target/compiled/motherduck_domain_01/models/staging/schema.yml/models/staging/test_sale_total_over_500_flags_only_strictly_over_500.sql` shows `cast(499.99 as INTEGER)` / `cast(500.01 as INTEGER)` — the input column is INTEGER, so sub-dollar cases cannot reach the model and the open interval (500, 501) is untestable | `07754c99b87e24821801819ab0439b0ad1b01edd` |
| Requirement artifact requirement | `R-04@1` — seed backs `source('raw','sales')`, columns agree with `sources.yml`, data exercises the R-03 boundary | Seed gate, catalog shape, row-level inspection | `dbt seed --select sales --target dev …` exit 0, `loaded seed file main.sales` **INSERT 10**; `SUMMARIZE main.sales` → exactly the 7 contract columns, `count` 10, `null_percentage` 0.00 on every column; values include one row at exactly 500.00, two above (600.00, 540.00) and seven below | `07754c99b87e24821801819ab0439b0ad1b01edd` |
| Plan artifact scope | `sales` (seed) — *none, existing artifact reused unchanged* | `git diff` shows no seed file touched; seed materialization gate | No repository file changed for this row; `transformation/seeds/sales.csv` sha256 `e19c7a1e1889501113307357de2a18b5f9a16c234c04e47cd99f39d79ddb8870`; materialised `INSERT 10` | `07754c99b87e24821801819ab0439b0ad1b01edd` |
| Plan artifact scope | `stg_sales_flagged` (model, staging, create) | Sandbox build gate + independent acceptance disproofs | `stg_sales_flagged.sql` sha256 `a48a9e4b55020262f0ae7a18803d274ed16293a3831a25c0f510aac1bfad666b`; build `PASS=5`; 2 data tests + 2 unit tests PASS | `07754c99b87e24821801819ab0439b0ad1b01edd` |
| Kind (not applicable) | `transformation` `Execution evidence:` marker reads `not applicable` | not applicable | The playbook's own stated reason: *"this kind runs no external pipeline"* — there is no pipeline execution to receipt, so this line is its own covering evidence and not a gap | — |

**Baseline disclosure.** No golden-baseline dataset is configured for `stg_sales_flagged`; the row-level claims above rest on **independent recomputation** from the source relation (`quantity * unit_price` and the `> 500` predicate recomputed against `main.sales`, joined on `sale_id`), which is a different evidence source from a golden-baseline comparison and is stated here rather than left implicit.

## Gate results

| Gate | Command | Exit code | Outcome | Rev |
| --- | --- | --- | --- | --- |
| Origin sync | `git fetch origin main && git rev-parse --verify origin/main && git merge origin/main --no-edit` | 0 | pass (*Already up to date*; merge-base `3b06367`) | `07754c99b87e24821801819ab0439b0ad1b01edd` |
| Seed materialization | `dbt seed --select sales --target dev --warn-error-options '{"error":["NoNodesForSelectionCriteria"]}'` | 0 | pass (`INSERT 10`) | `07754c99b87e24821801819ab0439b0ad1b01edd` |
| Model generation compile | `dbt compile --select stg_sales_flagged --target dev --warn-error-options '{"error":["NoNodesForSelectionCriteria"]}'` | 0 | pass | `07754c99b87e24821801819ab0439b0ad1b01edd` |
| Sandbox build (model + attached tests) | `dbt build --select stg_sales_flagged --target dev --defer --state /cache/prod-target --warn-error-options '{"error":["NoNodesForSelectionCriteria"]}'` | 0 | pass (`PASS=5 ERROR=0`) | `07754c99b87e24821801819ab0439b0ad1b01edd` |
| Real-data tests — data tests | `dbt test --select stg_sales_flagged --exclude test_type:unit --target dev --defer --state /cache/prod-target --warn-error-options '{"error":["NoNodesForSelectionCriteria"]}'` | 0 | pass (`PASS=4 ERROR=0`) | `07754c99b87e24821801819ab0439b0ad1b01edd` |
| Real-data tests — unit tests | `dbt test --select 'test_type:unit' --target dev --defer --state /cache/prod-target --warn-error-options '{"error":["NoNodesForSelectionCriteria"]}'` | 0 | pass (`PASS=4 ERROR=0`) | `07754c99b87e24821801819ab0439b0ad1b01edd` |
| Acceptance disproofs — population closure, key integrity, formula recomputation, threshold boundary | `lakehouse_query` over `main.stg_sales_flagged` joined to `main.sales` (one statement) | 0 | pass (`n_flag_null` 0, `n_at_500_wrongly_flagged` 0, `n_mismatch_vs_recalc` 0, `n_dropped` 0, `n_extra` 0) — but see the `R-03@1` coverage row: this proves only the representable boundary | `07754c99b87e24821801819ab0439b0ad1b01edd` |
| Project audit (`evaluating-dbt-project`) | `dbt build --select package:dbt_project_evaluator --vars '{dbt_project_evaluator_enabled: true}' --target dev --warn-error-options '{"error":["NoNodesForSelectionCriteria"]}'` | 0 | pass (`PASS=67 WARN=13 ERROR=0`; **0 error-severity findings**, so the halt does not fire) | `07754c99b87e24821801819ab0439b0ad1b01edd` |
| Dev-artifact scan | `grep -rnE "dev_mode\|add_limit\|ephm_motherduck_01" transformation/ --include=*.sql --include=*.yml --include=*.py \| grep -vE '^transformation/(target\|dbt_packages)/'` | 1 | pass — grep's exit 1 is the *no-match* signal; zero hits in source (all earlier hits were in the gitignored `target/`) | `07754c99b87e24821801819ab0439b0ad1b01edd` |
| Weakening — data tests | `python3 …/scripts/diff_data_tests.py /tmp/base-schema.yml /tmp/head-schema.yml` (both revisions materialised via `git show`) | 0 | pass (`{"weaker": [], "stronger": [], "ambiguous": []}`) | `07754c99b87e24821801819ab0439b0ad1b01edd` |
| Weakening — enforced contract | `python3 …/scripts/diff_manifest_contract.py --materialize <rev> /workspace/transformation /tmp/<rev>-manifest.json` for both revisions, then the differ | 0 | pass (`{"weaker": [], "stronger": []}` — no enforced contract exists in this project, so nothing was weakened) | `07754c99b87e24821801819ab0439b0ad1b01edd` |

**Alignment checks (step 7).** *Plan ↔ built:* both Plan scope rows have completed tasks with evidence; the full diff versus base `3b06367` is 8 files and additions only, with nothing built outside a scope row. *Design ↔ built:* model present; grain one row per sale unique on `sale_id` matches `#Grain`; materialization `view` matches `dbt_project.yml`'s `staging: +materialized: view`; no `unique_key` expected (not incremental); the built column set is exactly the nine `D-06` describes; `depends_on.nodes` is the source alone, matching `D-05`; `D-03`, `D-04`, `D-07`, `D-09` each match the built artifact. No `unique_key`, column, or materialization mismatch. *Documentation:* all nine columns carry descriptions, and each term the design record introduces (`sale_total`) is defined in `CONTEXT.md`. *Requirement ↔ design:* not re-litigated here; no outright contradiction found.

**LLM judge — semantic residue (each judgment quotes the text judged).** Quoting `D-02` *"`sale_total` is derived as `quantity * unit_price`, never sourced"* against the built `quantity * unit_price as sale_total`: matches. Quoting `D-03` *"The threshold is strict — `sale_total > 500`, so a sale of exactly 500.00 is not flagged"* against the built `when sale_total > 500 then true`: matches, and the source row at exactly 500.00 is observed unflagged. Quoting `D-04` *"written as a `case` that yields `true` or `false` and nothing else"* against the built `case … else false end`: matches, with 0 null flags observed. Quoting `D-08` *"Every source row is retained and the flag carries the threshold outcome"* against a built model with no `WHERE` clause and 0 dropped / 0 extra rows: matches. Quoting `R-03@1`'s acceptance text *"499.99 → false, 500.00 → false, 500.01 → true"* against the delivered evidence: **two of the three named cases are undemonstrated** — this is the residue, and it is the finding the certification returns on. The judge does not mark the `R-03@1` row covered.

**Non-blocking findings surfaced to the user (step 12), not filed as tracked issues:**

1. `fct_model_directories` (warning) flags `stg_sales_flagged` — *and both existing project models identically* — wanting `models/staging/raw/stg_sales_flagged.sql` rather than `models/staging/stg_sales_flagged.sql`. Pre-existing project structure; the new model was placed beside its two siblings as `D-06`/`D-09` intend. Moving it is a project-wide decision, not this intent's.
2. The project audit's other 12 warnings are Elementary-package and project-wide concerns, none naming this intent's artifacts: `fct_model_naming_conventions` (30 rows, every one an Elementary model), `fct_root_models` (16 rows, every one an Elementary model), `fct_missing_primary_key_tests`, `fct_undocumented_models`, `fct_source_directories`, `fct_sources_without_freshness`, `fct_undocumented_sources`, `fct_model_fanout`, `fct_source_fanout`, `fct_too_many_joins`, and the two coverage checks. All are `warning` severity; none is `error`, so the audit did not halt.
3. **Environment condition, root-caused not worked around:** the literal gate command first exited 2 on the Elementary package's own `on-run-end` hook (`Catalog Error: Table with name dbt_artifacts_hashes does not exist!`), reproducing identically on the untouched `stg_raw__sales`. Root cause: `elementary.upload_dbt_artifacts()` → `get_artifacts_hashes()` queries a table created only by Elementary's 32 models, which no sandbox materializes. Resolved **in the sandbox only, with no repository change**, by running `dbt run --select package:elementary` first. Project config, the profile, and the adapter were deliberately left alone; this domain's `dbt_project.yml` carries no `disable_dbt_artifacts_autoupload` / `disable_run_results` vars, which Studio's templates set elsewhere.
4. `sale_total`'s SQL type is inherited, not declared: INTEGER in the sandbox (whole-dollar seed values), DECIMAL(10,2) in production. Leaving it untyped is correct for a staging view, but the column description does not say so.

## Reviewer verdicts

Append-only. One verdict per reviewer dispatch, in dispatch order, each pasted verbatim.

### Dispatch 1 — `design-reviewer` (design stage)

```json
{
  "verdict": "APPROVE_WITH_WARNINGS",
  "summary": "The design for stg_sales_flagged is buildable and traceable. D-01 through D-09 all cite an approved requirement revision or an existing project convention, the grain is stated as one row per source sale keyed on sale_id, and the intended shape diffed against the production manifest at /cache/prod-target/manifest.json is purely additive: stg_sales_flagged is absent from that manifest and no model in the project carries an enforced contract, so nothing is removed or retyped and there is no breaking contract delta. Step 0 ADR-promotion pass: of the nine decisions this first-authored record introduces, none clears the bar. D-01, D-03, D-08 and D-09 are supplied decisions recorded as such in the Requirement and are requirements rather than agent-made trade-offs; D-02 is a user decision. D-04 is fixed by R-01's own never-null flag criterion. D-05, D-06 and D-07 were selected by existing conventions (the dbt_project_evaluator graph rule, the existing staging column contract, and the is_{condition} naming convention respectively) rather than by a trade-off between plausible unsettled alternatives. docs/adr/ contains no ADR files, so no bar-clearing decision is missing a file. One non-derivable edge choice is nevertheless unrecorded.",
  "issues": [
    {
      "severity": "warning",
      "message": "The NULL-handling decision is recorded for the flag but not for the new column sale_total itself. D-04 states that a null comparison yields false, but nothing states whether sale_total preserves NULL when quantity or unit_price is NULL, or coerces it to zero. The source columns are declared NOT NULL so the practical effect is nil today, yet the discipline requires a NULL-handling decision for every new column, and a later run against a null-bearing source would have to guess. The behaviour is also not recoverable from the code alone, since a future reader cannot tell whether the plain product or a coalesce was intended.",
      "location": "docs/design/models/stg_sales_flagged.md#Decisions"
    },
    {
      "severity": "info",
      "message": "Materialization is not restated as a decision in the record; it is inherited from dbt_project.yml's staging: +materialized: view and appears only under Supporting evidence. That is acceptable for a durable record, because copying a value the project config already declares is the second source of truth the template warns against. Flagging it only so that the Plan artifact's Scope and impact row carries materialization explicitly, which is where the medallion inventory expects it.",
      "location": "docs/design/models/stg_sales_flagged.md#Supporting evidence"
    }
  ],
  "next_step": "Add a decision recording sale_total's own NULL semantics, then re-dispatch this contract.",
  "notes": "Self-review. This verdict was produced inline by the same agent session that authored the design records, because on this runtime a dispatched subagent does not return control to the parent. It therefore lacks an independent reviewer's perspective, and its APPROVE on a later dispatch is not evidence of independent review."
}
```

### Dispatch 2 — `design-reviewer` (design stage, after the warning was fixed)

```json
{
  "verdict": "APPROVE",
  "summary": "The single warning from dispatch 1 is resolved. D-10 now records sale_total's NULL semantics: the column is the plain product quantity * unit_price, deliberately left uncoerced, and is therefore null when either input is null rather than asserted as zero. The reasoning is stated and the consequence is checked against the other decisions, since D-04 already resolves a null comparison to false, so the never-null flag contract in R-01 holds without coercing this column. D-10 cites R-02 rev 1 and the record's History names it as added without amending or superseding any earlier decision. Re-checked on the fixed revision: every decision still carries a qualified citation or names the convention that selected it, the grain is unchanged, the production-manifest diff is still purely additive, and the Step 0 ADR-promotion pass is unchanged because D-10, like D-04, is fixed by an approved requirement's own criterion rather than by a trade-off between unsettled alternatives.",
  "issues": [],
  "next_step": "",
  "notes": "Self-review. This verdict was produced inline by the same agent session that authored the design records, because on this runtime a dispatched subagent does not return control to the parent. It therefore lacks an independent reviewer's perspective, and its APPROVE is not evidence of independent review. The dispatch-1 finding was verified against the record and fixed rather than waived."
}
```

### Dispatch 3 — `code-reviewer` (verify stage)

Applied inline, read-only, as a fresh adversarial pass over the implementation artifacts named in the playbook (`transformation/models/staging/stg_sales_flagged.sql`, sha256 `a48a9e4b55020262f0ae7a18803d274ed16293a3831a25c0f510aac1bfad666b`; `transformation/models/staging/schema.yml`, sha256 `e361fb4d8b808f143bcac16d491d74905c10c5be1965269d52ff417e82ef4db7`), with the change's scale (`product`, publish-bound) and the Requirement artifact plus `docs/design/models/stg_sales_flagged.md` as design context.

```json
{
  "verdict": "BLOCK",
  "summary": "The implementation is correct and clean. stg_sales_flagged reads source('raw','sales') directly — the manifest's depends_on.nodes lists the source alone, not stg_raw__sales as D-05 requires — derives sale_total as quantity * unit_price in exactly one place, and emits is_over_500 as a CASE that can yield only true or false, so the never-null flag contract holds independently of the source's nullability. Independent checks confirm 10 rows, 10 distinct sale_id, 0 null flags, the row at exactly 500.00 unflagged, and 0 rows disagreeing with a recalculation against the source. It is blocked on one thing only, and that thing is not in the code: the accepted contract's own boundary acceptance criteria cannot be demonstrated.",
  "issues": [
    {
      "severity": "error",
      "message": "R-03@1's acceptance criteria state 'Boundary cases: sale_total 499.99 → false, 500.00 → false, 500.01 → true.' The 499.99 and 500.01 cases cannot be exercised through the approved input. dbt types unit-test fixture literals from the input relation's column types, and main.sales.unit_price is INTEGER, so a literal 499.99 compiles to cast(499.99 as INTEGER) and the cents never reach the model — shown literally in target/compiled/motherduck_domain_01/models/staging/schema.yml/models/staging/test_sale_total_over_500_flags_only_strictly_over_500.sql. The shipped tests pin the boundary at 500 vs 501, which leaves the whole open interval (500, 501) untestable: an implementation using '> 500' and one using '>= 501' are indistinguishable here and both pass, although only the former is correct against production's unit_price DECIMAL(10,2), where a 500.50 sale would be wrongly unflagged by the latter. This is not fixable in the model, in the tests, or in the project config, and sources.yml may not be changed (the Requirement's Out of scope says the sales columns declared there are not changed).",
      "location": "transformation/models/staging/schema.yml (unit_tests); docs/requirement/2026-09-21-new-intent-eab282dc.md#R-03 rev 1"
    },
    {
      "severity": "warning",
      "message": "Plan Task 3 Step 1 specified fixtures for 499.99 / 500.00 / 500.01, and Step 2 expected 'PASS=4 — two unit tests and two data tests' over exactly those cases. What shipped is a different, integer-only boundary design. The substitution is justified and documented in the task's own Execution evidence, but the task as written was not delivered as written, so the Plan artifact's Task 3 text and its delivered evidence no longer describe the same tests.",
      "location": "docs/plans/2026-09-21-new-intent-eab282dc.md#Task 3"
    },
    {
      "severity": "warning",
      "message": "The durable design record's Gotcha states 'The seed cannot prove the cents cases. Its unit_price is whole dollars, so sale_total never carries cents, while production's unit_price is DECIMAL(10,2). 499.99 and 500.01 therefore have to come from unit-test fixtures with explicit literals, not from source data.' That second sentence is false as written: dbt retypes fixture literals from the input relation, so the fixtures it relies on cannot carry cents either. A durable record holding a disproven claim will mislead the next intent that touches this model, which is precisely what a Gotcha exists to prevent.",
      "location": "docs/design/models/stg_sales_flagged.md#Gotchas (line 123)"
    },
    {
      "severity": "info",
      "message": "The final projection is 'select * from flagged', with the explicit column list living in the renamed CTE. That matches both sibling staging models, so it is the repo's convention and not an inconsistency, but it does mean a future source column would flow through this model unreviewed.",
      "location": "transformation/models/staging/stg_sales_flagged.sql"
    },
    {
      "severity": "info",
      "message": "sale_total's SQL type is inherited from the source rather than declared: INTEGER in the sandbox and DECIMAL(10,2) in production. Leaving a staging view untyped is the right call, but neither the column description nor the design record states that the type is inherited, so a reader comparing sandbox output to production could mistake the difference for a bug.",
      "location": "transformation/models/staging/schema.yml#sale_total"
    }
  ],
  "next_step": "Return to capturing-requirements: restate R-03@1's acceptance criteria to the boundary cases the approved source can actually exercise (500.00 → false and 501 → true under a strict-greater operator), or authorise a source that carries cents. Amend docs/design/models/stg_sales_flagged.md's Gotcha in the same loop, and align the Plan artifact's Task 3 text with the tests actually delivered. The model SQL needs no change.",
  "notes": "Applied inline by the verify stage because this runtime does not return a dispatched subagent's verdict to its parent. It is therefore a self-review by the session that authored the artifacts, not independent review, and carries that limitation explicitly. Every check above was run against the artifacts at 07754c99b87e24821801819ab0439b0ad1b01edd, not recalled."
}
```

## Approvals

Left for `shipping`. No ship approval is recorded: `## Certification` reads `returned`, so Ship may not proceed and no approval may be appended from inference.
