"""Imperative shell for the immutable per-build manifest release (AC-14..AC-18).

Gathers, for `dbt-manifest-<sha>`: whether it exists, and if so, per-asset presence and content
match against this run's assets -- yielding one of `absent` / `complete_match` / `incomplete` /
`complete_mismatch`. Builds `manifest-source.json` (ADR-0027/D-12's five fields) from job-local
scalars. Calls `dbt_docs_publish.build_manifest_release_commands` exactly once with that gathered
state and dispatches every returned `gh` command, then does the same for
`dbt_docs_publish.build_prune_commands` over the full `dbt-manifest-*` release set. Invoked
identically by both bundles' publish-prod-manifest workflows, immediately before the existing
`publish_dbt_docs_release.py` step, so a failure here never touches `dbt-docs-latest`.
"""
import datetime
import hashlib
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path

from dbt_docs_publish import (
    MANIFEST_RELEASE_TAG_PREFIX,
    PROVENANCE_ASSET,
    build_manifest_release_commands,
    build_prune_commands,
    classify_release_state,
    manifest_release_tag,
)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# The only adapter packages either publish workflow ever installs (`pip install "dbt-core>=1.8"
# "dbt-fabricspark>=1.8" ...` for Fabric / `pip install "dbt-duckdb" ...` for MotherDuck) --
# an allowlist rather than a blocklist of dbt-core's own transitive non-adapter packages
# (dbt-common, dbt-adapters, dbt-protos, dbt-core-experimental-parser, ...), because that set
# is dbt-core's internal implementation detail and changes across dbt-core releases without
# notice (PR #555 review finding, and confirmed live: an earlier blocklist attempt here
# false-positived "ambiguous adapter" on this PR's own real CI run when dbt-core pulled in
# two more transitive packages the blocklist didn't yet know about).
_KNOWN_ADAPTER_PACKAGES = frozenset({"dbt-fabricspark", "dbt-duckdb"})


def _resolve_dbt_versions() -> tuple[str, str, str]:
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


def _download_release_asset(tag: str, asset: str, dest) -> None:
    subprocess.run(
        ["gh", "release", "download", tag, "--pattern", asset, "--output", str(dest), "--clobber"],
        check=True,
    )


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _gather_release_state(tag: str, target_dir: str, expected_assets: list[str]):
    """Return (state, assets_to_upload) for build_manifest_release_commands.

    `expected_assets` is every asset this run must publish under the release: the manifests
    plus manifest-source.json. Content match ignores manifest-source.json's `published_at`
    field, which differs on every run by design. All I/O (existence check, per-asset
    download, hashing) lives here; the actual four-way classification is
    `classify_release_state`'s pure decision, not inline branching in this shell.
    """
    view = subprocess.run(
        ["gh", "release", "view", tag, "--json", "assets"], capture_output=True
    )
    if view.returncode != 0:
        if view.stderr and b"release not found" not in view.stderr.lower():
            # Matches publish_dbt_docs_release.py's own safety net: a non-zero exit for a
            # reason other than "release not found" (auth, rate limit, network) must not be
            # silently folded into "absent" without at least surfacing why, since "absent"
            # drives a create -- and creating a release the caller couldn't actually see is
            # a different failure than one that genuinely doesn't exist yet.
            print(
                f"gh release view exited {view.returncode} for {tag} for a reason other than "
                f"'release not found' -- proceeding as release-absent:\n"
                f"{view.stderr.decode(errors='replace')}",
                file=sys.stderr,
            )
        return "absent", expected_assets

    remote_assets = {a["name"] for a in json.loads(view.stdout or b"{}").get("assets", [])}
    missing = [a for a in expected_assets if a not in remote_assets]

    differing = list(missing)
    if missing != expected_assets:
        tmp_dir = Path(target_dir) / ".manifest-release-compare"
        tmp_dir.mkdir(exist_ok=True)
        for asset in expected_assets:
            if asset in missing:
                continue
            local_path = Path(target_dir) / asset
            remote_path = tmp_dir / asset
            _download_release_asset(tag, asset, remote_path)
            if asset == PROVENANCE_ASSET:
                local_payload = dict(json.loads(local_path.read_bytes()))
                remote_payload = dict(json.loads(remote_path.read_bytes()))
                local_payload.pop("published_at", None)
                remote_payload.pop("published_at", None)
                if local_payload != remote_payload:
                    differing.append(asset)
            elif _sha256(local_path) != _sha256(remote_path):
                differing.append(asset)

    state = classify_release_state(True, expected_assets, missing, differing)
    assets_to_upload = expected_assets if state == "absent" else differing
    return state, assets_to_upload


def main(target_dir: str, sha: str, asset_names: list[str]) -> int:
    target = Path(target_dir)
    dbt_version, adapter_name, adapter_version = _resolve_dbt_versions()
    provenance = {
        "build_sha": sha,
        "published_at": _now_iso(),
        "dbt_version": dbt_version,
        "adapter_name": adapter_name,
        "adapter_version": adapter_version,
    }
    (target / PROVENANCE_ASSET).write_text(json.dumps(provenance))

    expected_assets = [*asset_names, PROVENANCE_ASSET]
    tag = manifest_release_tag(sha)
    state, assets_to_upload = _gather_release_state(tag, target_dir, expected_assets)

    for cmd in build_manifest_release_commands(state, sha, assets_to_upload):
        subprocess.run(cmd, check=True, cwd=target_dir)

    existing = subprocess.run(
        ["gh", "release", "list", "--limit", "1000", "--json", "tagName,createdAt"],
        capture_output=True, check=True,
    )
    releases = [
        (r["tagName"], r["createdAt"])
        for r in json.loads(existing.stdout or b"[]")
        if r["tagName"].startswith(MANIFEST_RELEASE_TAG_PREFIX)
    ]
    for cmd in build_prune_commands(releases):
        subprocess.run(cmd, check=True, cwd=target_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3:]))
