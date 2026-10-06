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
from dbt_version_provenance import resolve_installed_versions


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    dbt_version, adapter_name, adapter_version = resolve_installed_versions()
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

    try:
        existing = subprocess.run(
            ["gh", "release", "list", "--limit", "1000", "--json", "tagName,createdAt"],
            capture_output=True, check=True,
        )
    except subprocess.CalledProcessError as exc:
        # Matches _gather_release_state's existing safety net for `gh release view`: a
        # bare CalledProcessError with no visible reason is exactly what made three
        # separate real CI failures on this exact call undiagnosable without guessing
        # (VD-5839). Print everything available -- stdout included, since a partial
        # response before a mid-stream failure can also be diagnostic.
        print(
            f"gh release list exited {exc.returncode}:\n"
            f"stderr: {(exc.stderr or b'').decode(errors='replace')}\n"
            f"stdout: {(exc.output or b'').decode(errors='replace')}",
            file=sys.stderr,
        )
        raise
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
