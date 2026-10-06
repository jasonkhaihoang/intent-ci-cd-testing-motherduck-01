"""Shared dbt/adapter version resolution and pinned install (VD-5832).

`resolve_installed_versions` is the promoted publish-side implementation (previously
`publish_manifest_release._resolve_dbt_versions`) -- both the publish workflow and a Gate 1
consumer must read installed-package metadata identically, or "the same version" could mean
two different things between them.

`pin_install_recorded_versions` is the consume-side thin interface: it installs exactly the
versions recorded in a baseline's provenance, so a disagreement surfaces as an install
failure (AC-105/106) rather than a post-hoc comparison.
"""
import importlib.metadata
import re
import subprocess
from typing import NamedTuple


# The only adapter packages the publish workflows ever install (`dbt-fabricspark` for a Fabric
# Lakehouse, `dbt-fabric` for a Fabric Warehouse, `dbt-duckdb` for MotherDuck) -- an allowlist
# rather than a blocklist of dbt-core's own transitive non-adapter packages (dbt-common,
# dbt-adapters, dbt-protos, dbt-core-experimental-parser, ...), because that set is dbt-core's
# internal implementation detail and changes across dbt-core releases without notice.
_KNOWN_ADAPTER_PACKAGES = frozenset({"dbt-fabricspark", "dbt-fabric", "dbt-duckdb"})

_PACKAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+!-]*")


def resolve_installed_versions() -> tuple[str, str, str]:
    """Return (dbt_version, adapter_name, adapter_version) via installed package metadata.

    `dbt --version` has no stable, documented JSON schema for adapter info on the dbt-core
    major version these workflows install (`--version --json` is not a real flag; the real
    one, `--format json`, only documents a bare `{"version": ...}` shape for a newer dbt
    major). Reading `importlib.metadata` instead avoids depending on either.

    Candidates are collected deterministically (sorted by name) rather than returning
    whichever `importlib.metadata.distributions()` happens to yield first: a silent,
    iteration-order-dependent pick would misattribute provenance if a second dbt-*
    package were ever transitively installed, with no way for a consumer to detect it.
    Exactly one installed distribution from `_KNOWN_ADAPTER_PACKAGES` is required; zero or
    more than one is a hard failure rather than a guess.
    """
    dbt_version = importlib.metadata.version("dbt-core")
    candidates = {
        dist.metadata["Name"]: dist.version
        for dist in importlib.metadata.distributions()
        if dist.metadata["Name"] in _KNOWN_ADAPTER_PACKAGES
    }
    if not candidates:
        raise RuntimeError("no dbt adapter package found among installed distributions")
    if len(candidates) > 1:
        raise RuntimeError(
            f"ambiguous dbt adapter: found {len(candidates)} candidate packages "
            f"{sorted(candidates)!r} -- expected exactly one"
        )
    adapter_name = next(iter(candidates))
    return dbt_version, adapter_name, candidates[adapter_name]


class PinInstallResult(NamedTuple):
    success: bool
    reason: str | None = None


def pin_install_recorded_versions(recorded: dict) -> PinInstallResult:
    """Install the exact dbt/adapter versions recorded in a baseline's provenance,
    overriding the floating-floor install ci.yml already ran in the same job.

    A version that cannot be installed (yanked, nonexistent, unknown package) is reported,
    not raised -- the caller maps it to a `version_mismatch` error.
    """
    dbt_version = recorded["dbt_version"]
    adapter_name = recorded["adapter_name"]
    adapter_version = recorded["adapter_version"]
    # These go into pip's argv: a value that pip could read as an option must never reach it.
    if not (_PACKAGE_NAME.fullmatch(adapter_name) and _VERSION.fullmatch(dbt_version) and _VERSION.fullmatch(adapter_version)):
        return PinInstallResult(
            False,
            f"recorded provenance is not installable: adapter_name={adapter_name!r} "
            f"dbt_version={dbt_version!r} adapter_version={adapter_version!r}",
        )
    result = subprocess.run(
        ["pip", "install", "--quiet", f"dbt-core=={dbt_version}", f"{adapter_name}=={adapter_version}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # One line only: the reason is written to $GITHUB_OUTPUT as `key=value`, and pip's
        # stderr is multi-line (the final ERROR line is the diagnosis; earlier lines can be huge).
        error_lines = [ln for ln in result.stderr.splitlines() if ln.startswith("ERROR:")]
        detail = (error_lines[-1] if error_lines else result.stderr.strip().replace("\n", " ")) or f"exit {result.returncode}"
        reason = (
            f"could not install the baseline's recorded dbt-core=={dbt_version} "
            f"{adapter_name}=={adapter_version}: {detail[:300]}"
        )
        return PinInstallResult(False, reason)

    # pip only adds packages: the floor install may already have put a different adapter on
    # PATH, so a zero exit does not prove the recorded adapter is the one present.
    try:
        importlib.metadata.version(adapter_name)
    except importlib.metadata.PackageNotFoundError:
        return PinInstallResult(
            False,
            f"pip install reported success for {adapter_name}=={adapter_version}, "
            f"but {adapter_name} is not installed afterward.",
        )
    return PinInstallResult(True)
