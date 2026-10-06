# Intent

CI verification run for the MotherDuck bundle.

Bump `stg_raw__sales` so `state:modified+` resolves to exactly that model, then drive the
full gate ladder against it. The design in `design.md` describes that model and only that
model, so `ci/design-drift` has an accurate contract to compare the manifest against.
