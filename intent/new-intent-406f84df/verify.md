# Verify: stg_customers staging model from a raw_customers seed

## Certification

Placeholder.

## Coverage

| Source | Item | Covered by | Evidence |
| --- | --- | --- | --- |

## Gate results

| Gate | Command | Exit code | Outcome |
| --- | --- | --- | --- |

## Reviewer verdicts

```json
{
  "verdict": "APPROVE",
  "summary": "ADR-promotion pass clean: only the stg_customers naming decision clears the bar, and docs/adr/0001-staging-model-naming-for-seed-fed-models.md exists on disk with status: decided, is cited in design.md line 8, is correctly numbered 0001 (sole ADR), and holds only structural facts plus the decision's own subject names (no conversation-derived example value/identifier/row content). Grain, staging-view materialization (verified against dbt_project.yml), seed-over-source rationale, Bronze Adequacy, Change Impact, and scope are all complete and consistent. The mart-layer control-column invariant does not apply (no mart added or changed; staging view only).",
  "issues": [],
  "next_step": "Proceed past the design stop and dispatch planning."
}
```

## Approvals
