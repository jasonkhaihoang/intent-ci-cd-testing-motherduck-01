"""Pure helpers for ci-config.yml loading and intent-slug validation.

Extracted from preflight.py so these functions are unit-testable in isolation
and reusable without going through the CLI shell.
"""
import os
import re

from platform_enum import DUCKDB_LOCAL, FABRIC_LAKEHOUSE, MOTHERDUCK, PLATFORMS, VALID_PLATFORMS

try:
    import yaml
except ImportError:
    yaml = None


def locate_ci_config(root: str = ".") -> str:
    """Return the ci-config.yml path: always .workflow/ci-config.yml."""
    return ".workflow/ci-config.yml"


def locate_project_dir(root: str = ".") -> str:
    """Return C6 dbt project path: transformation/ with root fallback."""
    candidate = os.path.join(root, "transformation", "dbt_project.yml")
    return "transformation" if os.path.isfile(candidate) else "."

INTENT_SLUG_RE = re.compile(r"^intent/[a-z0-9][a-z0-9\-]+$")

# The two `*_NAME` coordinates are deliberately absent: no workflow consumes them
# (ci.yml re-exports them as preflight outputs that nothing reads downstream), and
# both the /install-ci skill and the plugin's runtime-location-contract.json declare
# them optional. Requiring them here failed an install that legitimately omitted them.
_FABRIC_REQUIRED_KEYS = [
    "VD_DOMAIN_SLUG",
    "VD_DOMAIN_FABRIC_LAKEHOUSE_WORKSPACE_ID",
    "VD_DOMAIN_FABRIC_LAKEHOUSE_ID",
]

_MOTHERDUCK_REQUIRED_KEYS = [
    "VD_DOMAIN_SLUG",
    "VD_DOMAIN_MOTHERDUCK_DATABASE",
]

# LocalDuck runs no CI against a target platform, so it has no credential/coordinate
# keys to validate — just the domain slug every platform's config carries.
_DUCKDB_LOCAL_REQUIRED_KEYS = [
    "VD_DOMAIN_SLUG",
]

# Total over platform_enum.VALID_PLATFORMS — every member has its own entry, so a
# future platform added to VALID_PLATFORMS without a matching entry here raises
# (via the dict indexing below) instead of silently inheriting Fabric's keys.
_REQUIRED_KEYS_BY_PLATFORM = {
    FABRIC_LAKEHOUSE: _FABRIC_REQUIRED_KEYS,
    MOTHERDUCK: _MOTHERDUCK_REQUIRED_KEYS,
    DUCKDB_LOCAL: _DUCKDB_LOCAL_REQUIRED_KEYS,
}

# The ADR-0018 indirection block is validated permissively on purpose: an
# unrecognised key passes through so an older repository does not break on a
# stale one (AC-11 / VD-5013). No `*_VAR` key is required here — a mapping can
# be present and correct while the Variable it names is unset, so requiring the
# key would not catch the real failure anyway. Validating that a named Variable
# actually resolves needs the workflow to pass `${{ vars[...] }}` in, which is a
# separate change across the bundles.


def _is_blank(value) -> bool:
    """True when a declared key carries no usable value.

    `KEY:` with nothing after it parses as None, and `KEY: ""` as the empty
    string. Both satisfy a presence check while breaking every consumer, which
    is the shape VD-5156 surfaced from the other direction.
    """
    return value is None or (isinstance(value, str) and value.strip() == "")


# Committed coordinate key -> legacy lowercase key every existing downstream
# consumer (preflight.py's GITHUB_OUTPUT writer, ci.yml's `outputs.*` refs,
# fabric_api.py) already expects. VD_DOMAIN_SCHEMA has no entry here —
# confirmed dead (VD-3440 AC-64), dropped rather than renamed.
_KEY_ALIASES = {
    "VD_DOMAIN_DATA_PLATFORM": "platform",
    "VD_DOMAIN_SLUG": "domain",
    "VD_DOMAIN_FABRIC_LAKEHOUSE_WORKSPACE_ID": "prod_workspace_id",
    "VD_DOMAIN_FABRIC_LAKEHOUSE_WORKSPACE_NAME": "prod_workspace_name",
    "VD_DOMAIN_FABRIC_LAKEHOUSE_ID": "prod_lakehouse_id",
    "VD_DOMAIN_FABRIC_LAKEHOUSE_NAME": "prod_lakehouse_name",
    "VD_DOMAIN_MOTHERDUCK_DATABASE": "prod_db_name",
    "VD_DOMAIN_CI_DBT_PROFILE": "ci_target",
    "VD_DOMAIN_CI_SPARK_COMPUTE": "spark_compute",
    "VD_DOMAIN_PROD_MANIFEST_SOURCE": "prod_manifest_source",
}

# duckdb-quack is handled below with a specific migration message before this check.
# The accepted values are owned by platform_enum (AC-90) so every consumer that branches
# on platform reads the same set — see docs/design/bundle-manifest-composition/README.md.
_VALID_PLATFORMS = VALID_PLATFORMS


def _translate_config_keys(config: dict) -> dict:
    """Rename recognized VD_DOMAIN_* keys to the legacy lowercase names every
    existing consumer expects. All non-coordinate indirection values pass through
    unchanged so repository owners control their committed mapping."""
    return {_KEY_ALIASES.get(k, k): v for k, v in config.items()}


def validate_intent_slug(branch_name: str) -> tuple[bool, str | None]:
    """Return (valid, branch_name_if_valid_else_None)."""
    if INTENT_SLUG_RE.match(branch_name):
        return True, branch_name
    return False, None


def parse_ci_config(yaml_str: str) -> dict:
    """Parse ci-config.yml content.

    Returns:
        {
            "ok": bool,
            "config": dict,
            "error": str | None,
            "line_number": int | None,
            "missing_keys": list[str],
        }
    """
    if yaml is None:
        return {"ok": False, "config": {}, "error": "pyyaml not installed", "line_number": None, "missing_keys": []}

    try:
        config = yaml.safe_load(yaml_str)
    except yaml.YAMLError as exc:
        line_number = None
        if hasattr(exc, "problem_mark") and exc.problem_mark is not None:
            line_number = exc.problem_mark.line + 1
        return {"ok": False, "config": {}, "error": str(exc), "line_number": line_number, "missing_keys": []}

    if config is None:
        config = {}

    if not isinstance(config, dict):
        return {
            "ok": False,
            "config": {},
            "error": "ci-config.yml must be a YAML mapping (key: value pairs), not a list or scalar",
            "line_number": None,
            "missing_keys": [],
        }

    platform = config.get("VD_DOMAIN_DATA_PLATFORM")

    if platform == "duckdb-quack":
        return {
            "ok": False,
            "config": _translate_config_keys(config),
            "error": "platform: duckdb-quack is no longer supported. Use platform: motherduck instead.",
            "line_number": None,
            "missing_keys": [],
        }

    if platform is not None and platform not in _VALID_PLATFORMS:
        return {
            "ok": False,
            "config": _translate_config_keys(config),
            "error": f"Unknown platform: {platform!r}. Valid values: {', '.join(PLATFORMS)}.",
            "line_number": None,
            "missing_keys": [],
        }

    # platform is None (VD_DOMAIN_DATA_PLATFORM omitted) is the one deliberate
    # exception that still defaults to Fabric's keys, matching prior behavior.
    # Any non-None, recognized-but-unmapped platform raises KeyError rather than
    # silently inheriting Fabric's required keys.
    required_keys = _FABRIC_REQUIRED_KEYS if platform is None else _REQUIRED_KEYS_BY_PLATFORM[platform]
    absent = [k for k in required_keys if k not in config]
    blank = [k for k in required_keys if k in config and _is_blank(config[k])]

    if absent or blank:
        parts = []
        if absent:
            parts.append(f"Missing required keys: {absent}")
        if blank:
            parts.append(f"Required keys present but empty: {blank}")
        return {
            "ok": False,
            "config": _translate_config_keys(config),
            "error": ". ".join(parts),
            "line_number": None,
            "missing_keys": absent + blank,
        }

    return {"ok": True, "config": _translate_config_keys(config), "error": None, "line_number": None, "missing_keys": []}
