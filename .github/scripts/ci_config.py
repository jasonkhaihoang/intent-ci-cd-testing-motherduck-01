"""Pure helpers for ci-config.yml loading and intent-slug validation.

Extracted from preflight.py so these functions are unit-testable in isolation
and reusable without going through the CLI shell.
"""
import os
import re

try:
    import yaml
except ImportError:
    yaml = None


def locate_ci_config(root: str = ".") -> str:
    """Return the Studio-rendered ci-config.yml path: always .workflow/ci-config.yml."""
    return ".workflow/ci-config.yml"


def locate_project_dir(root: str = ".") -> str:
    """Return C6 dbt project path: transformation/ with root fallback."""
    candidate = os.path.join(root, "transformation", "dbt_project.yml")
    return "transformation" if os.path.isfile(candidate) else "."

INTENT_SLUG_RE = re.compile(r"^intent/[a-z0-9][a-z0-9\-]+$")

_FABRIC_REQUIRED_KEYS = [
    "VD_DOMAIN_SLUG",
    "VD_DOMAIN_FABRIC_WORKSPACE_ID",
    "VD_DOMAIN_FABRIC_WORKSPACE_NAME",
    "VD_DOMAIN_FABRIC_LAKEHOUSE_ID",
    "VD_DOMAIN_FABRIC_LAKEHOUSE_NAME",
]

_MOTHERDUCK_REQUIRED_KEYS = [
    "VD_DOMAIN_SLUG",
    "VD_DOMAIN_MOTHERDUCK_DATABASE",
]

# New (Studio-rendered) key -> legacy lowercase key every existing downstream
# consumer (preflight.py's GITHUB_OUTPUT writer, ci.yml's `outputs.*` refs,
# fabric_api.py) already expects. VD_DOMAIN_SCHEMA has no entry here —
# confirmed dead (VD-3440 AC-64), dropped rather than renamed.
_KEY_ALIASES = {
    "VD_DOMAIN_DATA_PLATFORM": "platform",
    "VD_DOMAIN_SLUG": "domain",
    "VD_DOMAIN_FABRIC_WORKSPACE_ID": "prod_workspace_id",
    "VD_DOMAIN_FABRIC_WORKSPACE_NAME": "prod_workspace_name",
    "VD_DOMAIN_FABRIC_LAKEHOUSE_ID": "prod_lakehouse_id",
    "VD_DOMAIN_FABRIC_LAKEHOUSE_NAME": "prod_lakehouse_name",
    "VD_DOMAIN_MOTHERDUCK_DATABASE": "prod_db_name",
    "VD_DOMAIN_CI_DBT_PROFILE": "ci_target",
    "VD_DOMAIN_CI_SPARK_COMPUTE": "spark_compute",
    "VD_DOMAIN_PROD_MANIFEST_SOURCE": "prod_manifest_source",
}

# duckdb-quack is handled below with a specific migration message before this check
_VALID_PLATFORMS = {"fabric", "motherduck"}


def _translate_config_keys(config: dict) -> dict:
    """Rename recognized VD_DOMAIN_* keys to the legacy lowercase names every
    existing consumer expects. Unrecognized keys pass through unchanged."""
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
            "error": f"Unknown platform: {platform!r}. Valid values: {', '.join(sorted(_VALID_PLATFORMS))}.",
            "line_number": None,
            "missing_keys": [],
        }

    required_keys = _MOTHERDUCK_REQUIRED_KEYS if platform == "motherduck" else _FABRIC_REQUIRED_KEYS

    missing = [k for k in required_keys if k not in config]
    if missing:
        return {
            "ok": False,
            "config": _translate_config_keys(config),
            "error": f"Missing required keys: {missing}",
            "line_number": None,
            "missing_keys": missing,
        }

    return {"ok": True, "config": _translate_config_keys(config), "error": None, "line_number": None, "missing_keys": []}
