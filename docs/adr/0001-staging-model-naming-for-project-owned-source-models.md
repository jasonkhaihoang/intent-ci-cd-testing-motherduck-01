---
status: decided
date: 2026-08-18
---

# Staging models fed by a project-owned source model use a literal name, not `stg_{source}__{table}`

The domain's staging naming convention is `stg_{source}__{table}`, where `{source}` names an external source system. `src_customers` is a project-owned source model (its data is authored in-repo, originally as a dbt seed) with no external source system. Forcing its name into the `{source}` slot would invent a source-system identifier that does not exist. Staging models fed by a project-owned source model therefore use a literal name derived from the source table (drop the `src_` prefix): `stg_customers` for the `src_customers` source model.

This clears the promotion bar because it is surprising without context — the first staging model in a fresh scaffold reads as convention-diverging next to any source-system-fed staging model — and because it sets a precedent: every later staging model fed by project-owned source data must make the same call.

## Considered Options

- **Literal name (`stg_customers`)** — chosen; faithful to the request and avoids inventing a source-system identifier for a project-owned source model.
- **`stg_seed__customers`** — would conform to the `{source}__{table}` shape by treating `seed` as the source, but invents a pseudo-source that corresponds to no real system.

## Consequences

- Staging models fed by project-owned source data use a literal name derived from the source table (drop `src_`); source-system-fed staging models continue to use `stg_{source}__{table}`.
- A future intent that onboards a real source system must not mistake literal-named source-model-fed models for source-system models.
