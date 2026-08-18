"""Apply a bundle-deploy.json manifest into a domain repo (plugin-owned initialization).

Functional core / imperative shell:
  - `plan_copies` is pure: it receives already-resolved sources and the set of existing
    destinations and returns the list of copies to perform. No filesystem calls.
  - `main` is the shell: it reads the manifest, resolves each source against `source_roots`,
    scans the target for existing destinations, calls `plan_copies`, then executes the copies.

CLI:
    bundle_deploy.py --platform fabric|motherduck --target <repo-path> [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

_BUNDLE_DIRS = {
    "fabric": "domain-ci-fabric-bundle",
    "motherduck": "domain-ci-motherduck-bundle",
}


def candidate_sources(source: str, source_roots: list[str]) -> list[str]:
    """Ordered candidate paths (relative to bundle_root) for a manifest source.

    First match wins — mirrors the `source_roots` resolution contract.
    """
    return [os.path.join(root, source) for root in source_roots]


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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=sorted(_BUNDLE_DIRS))
    parser.add_argument("--target", required=True, help="path to the domain repo")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    bundle_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    bundle_dir = os.path.join(bundle_root, _BUNDLE_DIRS[args.platform])
    with open(os.path.join(bundle_dir, "bundle-deploy.json")) as f:
        bundle = json.load(f)

    resolved = _resolve_sources(bundle, bundle_root)
    existing = _existing_destinations(bundle, args.target)
    plans = plan_copies(bundle, bundle_root, args.target, existing, resolved)

    for plan in plans:
        print(f"{'[dry-run] ' if args.dry_run else ''}{plan['mode']}: {plan['destination']}")
        if not args.dry_run:
            os.makedirs(os.path.dirname(plan["destination"]), exist_ok=True)
            shutil.copyfile(plan["source"], plan["destination"])

    print(f"{len(plans)} file(s) {'planned' if args.dry_run else 'deployed'} to {args.target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
