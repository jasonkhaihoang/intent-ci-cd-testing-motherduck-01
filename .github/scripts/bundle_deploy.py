"""Apply a bundle-deploy.json manifest into a domain repo (plugin-owned initialization).

Functional core / imperative shell:
  - `plan_copies` is pure: it receives already-resolved sources and the set of existing
    destinations and returns the list of copies to perform. No filesystem calls.
  - `main` is the shell: it reads the manifest, resolves each source against `source_roots`,
    scans the target for existing destinations, calls `plan_copies`, then executes the copies.

CLI:
    bundle_deploy.py --platform fabric_lakehouse|motherduck --target <repo-path> [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from platform_enum import FABRIC_LAKEHOUSE, MOTHERDUCK

# Keyed wider than platform_enum.VALID_PLATFORMS: DuckDB-local receives global-common
# content but runs no CI, so it has no ci-config.yml platform value to validate (D11).
_BUNDLE_DIRS = {
    FABRIC_LAKEHOUSE: "domain-ci-fabric-bundle",
    MOTHERDUCK: "domain-ci-motherduck-bundle",
    "duckdb": "domain-ci-duckdb-bundle",
}

# The fixed set of named delivery groups (design D2). Fixed, not derived from which groups
# happen to have entries in a given common manifest — a group with zero entries today (e.g.
# in a test fixture) is still a valid group, not an undefined one.
_KNOWN_GROUPS = {"ci-common", "global-common"}


def candidate_sources(source: str, source_roots: list[str]) -> list[str]:
    """Ordered candidate paths (relative to bundle_root) for a manifest source.

    First match wins — mirrors the `source_roots` resolution contract.
    """
    return [os.path.join(root, source) for root in source_roots]


def merge_manifests(common: dict, platform_manifest: dict, platform_name: str) -> tuple[list[dict], list[str]]:
    """Merge the common manifest's group-entitled entries with a platform's own entries.

    Pure function: no filesystem access. Collects every violation in one pass rather than
    stopping at the first (AC-BMC-16) — a rejection response names every problem at once.
    Returns (merged_files, []) on success, or ([], violations) on any violation.
    """
    violations: list[str] = []

    platforms = common.get("platforms", {})
    if platform_name not in platforms:
        violations.append(f"unsupported platform: {platform_name!r} is not declared in the platform registry")
        entitled_groups: list[str] = []
    else:
        entitled_groups = platforms[platform_name].get("groups", [])

    seen_groups: set[str] = set()
    for group in entitled_groups:
        if group not in _KNOWN_GROUPS:
            violations.append(f"platform {platform_name!r} names undefined grouping {group!r}")
        if group in seen_groups:
            violations.append(f"platform {platform_name!r} declares grouping {group!r} more than once")
        seen_groups.add(group)

    filtered_common = [
        entry for entry in common.get("files", [])
        if entry.get("group") in entitled_groups
    ]
    platform_entries = platform_manifest.get("files", [])

    # AC-BMC-06: same-manifest (platform's own) destination collision.
    seen_platform_dests: dict[str, str] = {}
    for entry in platform_entries:
        dest = entry["destination"]
        if dest in seen_platform_dests:
            violations.append(
                f"platform {platform_name!r} declares two entries at destination {dest!r}"
            )
        seen_platform_dests[dest] = entry["source"]

    # AC-BMC-23: cross-manifest (common vs. platform-specific) destination collision.
    common_dests = {entry["destination"] for entry in filtered_common}
    for entry in platform_entries:
        if entry["destination"] in common_dests:
            violations.append(
                f"platform {platform_name!r}: entry at destination {entry['destination']!r} "
                "collides with a common-manifest entry"
            )

    if violations:
        return [], violations

    return filtered_common + platform_entries, []


def plan_copies(bundle: dict,
                bundle_root: str,
                target_root: str,
                existing_destinations: set[str],
                resolved_sources: dict[str, str]) -> list[dict]:
    """Pure planner: which files to copy and how. No filesystem access.

    `resolved_sources` maps each manifest source to its resolved path relative to
    `bundle_root`. `existing_destinations` is the set of destination paths (as written in
    the manifest) that already exist under `target_root`.
    """
    plans = []
    for entry in bundle["files"]:
        dest_rel = entry["destination"]
        mode = entry.get("mode", "overwrite")
        if mode == "skip_if_exists" and dest_rel in existing_destinations:
            continue
        resolved = resolved_sources[entry["source"]]
        plans.append({
            "source": os.path.join(bundle_root, resolved),
            "destination": os.path.join(target_root, dest_rel),
            "mode": mode,
        })
    return plans


def _resolve_sources(bundle: dict, bundle_root: str) -> dict[str, str]:
    resolved = {}
    for entry in bundle["files"]:
        for candidate in candidate_sources(entry["source"], bundle["source_roots"]):
            if os.path.isfile(os.path.join(bundle_root, candidate)):
                resolved[entry["source"]] = candidate
                break
        else:
            raise FileNotFoundError(
                f"bundle source {entry['source']!r} not found under any source_root {bundle['source_roots']}"
            )
    return resolved


def _existing_destinations(bundle: dict, target_root: str) -> set[str]:
    return {
        entry["destination"]
        for entry in bundle["files"]
        if os.path.exists(os.path.join(target_root, entry["destination"]))
    }


def _apply_copy(source: str, destination: str) -> None:
    """Copy source to destination, preserving source's permission bits
    (shutil.copy, not shutil.copyfile — a bundle-owned hook file must land
    executable, and copyfile drops the mode bits)."""
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.copy(source, destination)


def main(argv: list[str], bundle_root: str | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=sorted(_BUNDLE_DIRS))
    parser.add_argument("--target", required=True, help="path to the domain repo")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if bundle_root is None:
        bundle_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    with open(os.path.join(bundle_root, "shared", "bundle-deploy.json")) as f:
        common = json.load(f)
    bundle_dir = os.path.join(bundle_root, _BUNDLE_DIRS[args.platform])
    with open(os.path.join(bundle_dir, "bundle-deploy.json")) as f:
        platform_manifest = json.load(f)

    merged_files, violations = merge_manifests(common, platform_manifest, args.platform)
    if violations:
        for v in violations:
            print(f"REJECTED: {v}", file=sys.stderr)
        return 1

    bundle = {
        "source_roots": platform_manifest.get("source_roots", ["shared", _BUNDLE_DIRS[args.platform]]),
        "files": merged_files,
    }
    resolved = _resolve_sources(bundle, bundle_root)
    existing = _existing_destinations(bundle, args.target)
    plans = plan_copies(bundle, bundle_root, args.target, existing, resolved)

    for plan in plans:
        print(f"{'[dry-run] ' if args.dry_run else ''}{plan['mode']}: {plan['destination']}")
        if not args.dry_run:
            _apply_copy(plan["source"], plan["destination"])

    print(f"{len(plans)} file(s) {'planned' if args.dry_run else 'deployed'} to {args.target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
