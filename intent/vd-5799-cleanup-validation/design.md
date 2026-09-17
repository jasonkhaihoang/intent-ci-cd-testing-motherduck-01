# Design

## Scope

Validation bump for VD-5799 (Domain-namespaced per-PR MotherDuck cleanup) — no schema or
model-shape change, just a trailing comment on `stg_raw__sales` to trigger `state:modified`
and exercise the gate ladder against the updated `domain-ci-motherduck-bundle`.

## Changes

### Model: `stg_raw__sales`

- No column, materialization, or grain change — a trailing SQL comment only.
