---
status: decided
date: 2026-08-18
---

# Seed-fed staging models use a literal name, not `stg_{source}__{table}`

The domain's staging naming convention is `stg_{source}__{table}`, where `{source}` names an external source system. A dbt seed has no external source system — it is a version-controlled CSV owned by the project itself. Forcing a seed's name into the `{source}` slot would invent a source-system identifier that does not exist. Seed-fed staging models therefore use a literal name derived from the seed table (drop the `raw_` prefix): `stg_customers` for the `raw_customers` seed.

This clears the promotion bar because it is surprising without context — the first staging model in a fresh scaffold reads as convention-diverging next to any source-system-fed staging model — and because it sets a precedent: every later seed-fed staging model must make the same call.

## Considered Options

- **Literal name (`stg_customers`)** — chosen; faithful to the request and avoids inventing a source-system identifier for a project-owned seed.
- **`stg_seed__customers`** — would conform to the `{source}__{table}` shape by treating `seed` as the source, but invents a pseudo-source that corresponds to no real system.

## Consequences

- Seed-fed staging models use a literal name derived from the seed table (drop `raw_`); source-system-fed staging models continue to use `stg_{source}__{table}`.
- A future intent that onboards a real source system must not mistake literal-named seed models for source-system models.
