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

Public surface:
  build_release_publish_commands(release_exists, asset_names=None)
  RELEASE_TAG
  ASSET_NAME
  SELECTION_MANIFEST_ASSET
  DEFER_MANIFEST_ASSET
"""

RELEASE_TAG = "dbt-docs-latest"
ASSET_NAME = "static_index.html"

# The manifest parsed with placeholder identifiers, used for `state:modified+` selection.
SELECTION_MANIFEST_ASSET = "manifest.json"
# The manifest parsed against the real production target, used for `--defer --state`.
# Fabric publishes both; MotherDuck's compile target is already the prod database, so
# its single `manifest.json` serves both roles and it publishes only the selection name.
DEFER_MANIFEST_ASSET = "manifest_prod.json"


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
