# motherduck-domain-01 Data Product

**Owner:** {Team Name}
**Sources:** {Salesforce | QuickBooks | PostgreSQL | etc.}
**Refresh:** {Daily at 6 AM UTC | Hourly | Real-time}

---

## Medallion Layers

### Staging (Bronze → Silver)

- **Naming:** `stg_{source}__{table}`
- **Materialization:** Views
- **Purpose:** 1:1 with source tables, rename columns, filter soft-deletes

### Marts (Silver → Gold)

- **Naming:** `fct_{process}` or `dim_{entity}`
- **Materialization:** Tables
- **Purpose:** Business logic, star schema, aggregations

### Semantic

- **Naming:** `{domain}_metrics.yml`
- **Purpose:** Metric definitions for consistency

---

## Naming Conventions

| Type            | Pattern                 | Example                       |
| --------------- | ----------------------- | ----------------------------- |
| Staging model   | `stg_{source}__{table}` | `stg_salesforce__opportunity` |
| Fact table      | `fct_{process}`         | `fct_pipeline_daily`          |
| Dimension table | `dim_{entity}`          | `dim_account`                 |
| Primary key     | `{entity}_id`           | `opportunity_id`              |
| Date column     | `{event}_date`          | `close_date`                  |
| Boolean column  | `is_{condition}`        | `is_closed_won`               |
| Amount column   | `{metric}_amount`       | `total_amount`                |

---

## Business Rules

### {Rule 1 Name}

{Brief description}

```sql
-- Example SQL
WHERE is_deleted = FALSE
  AND amount > 0
```

### {Rule 2 Name}

{Brief description}

```sql
-- Example SQL
CASE
  WHEN stage_name = 'Closed Won' AND is_closed = TRUE THEN TRUE
  ELSE FALSE
END AS is_closed_won
```

---

## Validation Standards

**Tolerance:**

- Row count: ±2% acceptable, ±10% fails build
- Currency amounts: ±$1,000 or 1% acceptable, ±5% fails build

**Required Tests:**

- `not_null` on all primary keys
- `unique` on all primary keys
- `relationships` on all foreign keys

---

## Fabric Configuration

- **Workspace:** MOTHERDUCK-DOMAIN-01\_MAIN
- **Lakehouse:** MOTHERDUCK-DOMAIN-01\_LH
- **Schema:** dbo
- **Ephemeral Prefix:** {domain}_fb_

---

## Context & Decision Memory Precedence

This repo's own `CONTEXT.md` (root) and `docs/adr/` are durable, committed memory: the
ubiquitous language and past architectural decisions the agents building, fixing, and
advising on this domain's data products rely on across intents. When a source of truth
conflicts with another, resolve it in this order, most specific first:

1. **The current intent's own `intent/<slug>/design.md`** — the in-flight record for the
   work happening right now; it can temporarily diverge from a stale ADR until that ADR is
   reconciled.
2. **This repo's own `CONTEXT.md` and `docs/adr/`** — durable, cross-intent, committed.
3. **The agent runtime's own ephemeral working memory** (not committed to this repo) —
   fills gaps the two sources above don't cover, but never overrides a documented
   convention or an accepted decision.

Neither `CONTEXT.md` nor `docs/adr/` ever holds an example value, identifier, or row
content seen in conversation — only structural facts (a term's meaning, a decision and its
reasoning).
