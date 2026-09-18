"""Fixed-tag GitHub Release publish command builder.

Pure thin interface (CLAUDE.md functional-core rule): given whether the `dbt-docs-latest`
GitHub Release already exists, returns the ordered `gh` argv command sequence to publish
assets to it. No I/O — the caller resolves release-existence (e.g. via
`gh release view RELEASE_TAG`) and executes the returned commands.

The tag is named for the dbt Docs site because that was its first payload; it is a
fixed, clobbered address rather than a version, and the prod-state manifests share it
(VD-4418) rather than minting a second release.

RELEASE_TAG and the asset-name constants are exported so the caller's own existence-check
and download commands target the same literals this module publishes to, instead of
duplicating the strings.

Also carries the AC-14..AC-18 command builders for the immutable per-build release
(`dbt-manifest-<sha>`): `build_manifest_release_commands` (create/upload/repair/reject by
release state) and `build_prune_commands` (count-based retention). Extending this module
rather than adding a second one follows CLAUDE.md's module-reuse rule — this file already
owns "which `gh` commands to run to publish a release."

Public surface:
  build_release_publish_commands(release_exists, asset_names=None)
  build_manifest_release_commands(release_state, sha, assets_to_upload)
  build_prune_commands(existing_releases, keep=10)
  classify_release_state(release_exists, expected_assets, missing, differing)
  manifest_release_tag(sha)
  ManifestReleaseMismatchError
  RELEASE_TAG
  ASSET_NAME
  SELECTION_MANIFEST_ASSET
  DEFER_MANIFEST_ASSET
  PROVENANCE_ASSET
  MANIFEST_RELEASE_TAG_PREFIX
"""

RELEASE_TAG = "dbt-docs-latest"
ASSET_NAME = "static_index.html"

# The manifest parsed with placeholder identifiers, used for `state:modified+` selection.
SELECTION_MANIFEST_ASSET = "manifest.json"
# The manifest parsed against the real production target, used for `--defer --state`.
# Fabric publishes both; MotherDuck's compile target is already the prod database, so
# its single `manifest.json` serves both roles and it publishes only the selection name.
DEFER_MANIFEST_ASSET = "manifest_prod.json"

# ADR-0027/D-12 provenance asset, published to both the per-build and `dbt-docs-latest` releases.
PROVENANCE_ASSET = "manifest-source.json"

MANIFEST_RELEASE_TAG_PREFIX = "dbt-manifest-"


class ManifestReleaseMismatchError(Exception):
    """Raised when an existing per-build release's assets differ from this run's (AC-18)."""


def manifest_release_tag(sha: str) -> str:
    return f"{MANIFEST_RELEASE_TAG_PREFIX}{sha}"


def classify_release_state(
    release_exists: bool, expected_assets: list[str], missing: list[str], differing: list[str]
) -> str:
    """Classify a `dbt-manifest-<sha>` release into one of the four
    `build_manifest_release_commands` states, from four pre-gathered facts:

    - `release_exists`: whether the release row itself exists at all (from `gh release
      view`'s exit code) — this must be checked directly, never inferred from asset
      presence: a release that exists but carries *none* of the expected assets (e.g.
      every asset was stripped from it) still has `missing == expected_assets`, which
      would be indistinguishable from a genuinely absent release if `missing` were the
      only signal (PR #555 review finding — the earlier three-argument version conflated
      the two, and `build_manifest_release_commands` would then issue `gh release create`
      against an already-existing tag, a hard error).
    - `expected_assets`: every asset this run must publish under the release.
    - `missing`: which of those the release does not currently carry at all.
    - `differing`: which of those the release carries with content that doesn't match this
      run's (content comparison, including the missing ones, is the shell's job — this
      function only turns the result into a state name).

    This is domain logic (a decision table), not I/O, so it is a pure thin interface
    alongside `build_manifest_release_commands` rather than inline branching in the shell
    that gathers `missing`/`differing` — CLAUDE.md's functional-core rule.
    """
    if not release_exists:
        return "absent"
    if not differing:
        return "complete_match"
    if missing:
        return "incomplete"
    return "complete_mismatch"


def build_manifest_release_commands(
    release_state: str, sha: str, assets_to_upload: list[str]
) -> list[list[str]]:
    """Return the gh command sequence for the immutable per-build release (AC-14, AC-18).

    `release_state` is a pre-gathered scalar — one of the four states the shell computes by
    comparing this run's assets against an existing `dbt-manifest-<sha>` release, if any:

    - `"absent"`: no such release exists yet. Create it (`--target` pins it to the exact
      build commit, matching D-11's "immutable by construction") and upload every asset.
    - `"complete_match"`: the release exists and already carries every expected asset with
      matching content. No-op — re-publishing the same commit must not error (AC-18).
    - `"incomplete"`: the release exists but a prior run left it partial (e.g. created, then
      failed mid-upload). Repair it by uploading only the assets the shell found missing or
      differing, rather than treating a resumable failure as a hard mismatch.
    - `"complete_mismatch"`: the release exists, is complete, but its content differs from
      this run's — a genuine integrity conflict. Hard failure, never retried automatically.

    The core makes no I/O and re-derives nothing about "now" or "does it exist" -- those are
    gathered once by the shell and passed in.
    """
    tag = manifest_release_tag(sha)
    if release_state == "absent":
        create_cmd = [
            "gh", "release", "create", tag, "--target", sha, "--title", tag, "--notes", "",
        ]
        upload_cmd = ["gh", "release", "upload", tag, *assets_to_upload, "--clobber"]
        return [create_cmd, upload_cmd]
    if release_state == "complete_match":
        return []
    if release_state == "incomplete":
        return [["gh", "release", "upload", tag, *assets_to_upload, "--clobber"]]
    if release_state == "complete_mismatch":
        raise ManifestReleaseMismatchError(
            f"{tag} already exists with assets that differ from this run's build"
        )
    raise ValueError(f"unknown release_state: {release_state!r}")


def build_prune_commands(
    existing_releases: list[tuple[str, str]], keep: int = 10
) -> list[list[str]]:
    """Return delete commands pruning `dbt-manifest-*` releases beyond the `keep` newest.

    `existing_releases` is the full, prefix-filtered `(tag, created_at)` set the shell already
    gathered (via a single `--limit 1000` call well past the CLI's default page size) — this function never
    re-queries GitHub. Sorted by `(created_at, tag)` descending: creation time orders newest
    first, and the tag breaks ties deterministically when two releases share a timestamp
    (AC-16). The newest `keep` are retained; everything older is deleted along with its tag.
    """
    ordered = sorted(existing_releases, key=lambda r: (r[1], r[0]), reverse=True)
    to_prune = list(reversed(ordered[keep:]))
    return [["gh", "release", "delete", tag, "--yes", "--cleanup-tag"] for tag, _ in to_prune]


def build_release_publish_commands(
    release_exists: bool, asset_names: list[str] | None = None
) -> list[list[str]]:
    """Return the gh command sequence to publish assets to the fixed-tag release.

    When the release is absent, the release must be created before assets can be
    uploaded to it, so the create command is returned first. When the release already
    exists, only the clobber-upload command runs.

    `asset_names` defaults to the dbt Docs site alone. The prod-state manifests ride
    this same release (VD-4418): they are repository *contents*, which the brokered
    agent GitHub token can read, whereas an Actions artifact needs Actions read and is
    therefore unreachable from an Intent. All assets go in one `upload` invocation --
    `gh` accepts several, and one command keeps the publish atomic per run.
    """
    assets = list(asset_names) if asset_names else [ASSET_NAME]
    upload_cmd = ["gh", "release", "upload", RELEASE_TAG, *assets, "--clobber"]
    if release_exists:
        return [upload_cmd]

    create_cmd = ["gh", "release", "create", RELEASE_TAG, "--title", RELEASE_TAG, "--notes", ""]
    return [create_cmd, upload_cmd]
