"""Canonical platform discriminator values for `VD_DOMAIN_DATA_PLATFORM`.

Single source of truth for the platform enum (AC-90, VD-4910). Every consumer that
validates, defaults to, or branches on a platform imports these constants instead of
repeating the string literal — the drift between five independent spellings is what
let Studio's rename to `fabric_lakehouse` break `ci/preflight` unnoticed.

Named `platform_enum`, never `platform`: bundle entries land in `.github/scripts/`,
which is on `sys.path` for every gate runner, so a module named `platform.py` there
would shadow the standard library's `platform` module process-wide.

The platform values are flat peers — each has its own bundle and codepath. There is
deliberately no "Fabric family" grouping `fabric_lakehouse` with `fabric_warehouse`;
see docs/design/bundle-manifest-composition/README.md § Platform discriminator values.
The two Fabric kinds share only their authentication story: the dbt adapter
(`dbt-fabricspark` vs `dbt-fabric`), the transport (Livy vs TDS), the ephemeral write
target, and OneLake writability all differ, which is why each carries its own bundle.
"""

FABRIC_LAKEHOUSE = "fabric_lakehouse"
FABRIC_WAREHOUSE = "fabric_warehouse"
MOTHERDUCK = "motherduck"
DUCKDB_LOCAL = "duckdb_local"

# Ordered so argparse `choices` and validation error text render deterministically.
PLATFORMS = (FABRIC_LAKEHOUSE, FABRIC_WAREHOUSE, MOTHERDUCK, DUCKDB_LOCAL)

VALID_PLATFORMS = frozenset(PLATFORMS)
