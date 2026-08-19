"""Imperative shell for publishing the dbt Docs static site to GitHub Releases.

Gathers release-existence via `gh release view`, calls the pure functional core
`build_release_publish_commands` (dbt_docs_publish.py) exactly once, then dispatches every
returned `gh` command. Invoked identically by both domain-ci-fabric-bundle's and
domain-ci-motherduck-bundle's publish-prod-manifest workflows -- CLAUDE.md's functional-
architecture rule: gather I/O upfront, call the core once, dispatch effects; never re-evaluate
the domain decision afterward.
"""
import subprocess
import sys

from dbt_docs_publish import build_release_publish_commands, RELEASE_TAG


def main(target_dir: str, asset_names: list[str] | None = None) -> int:
    view = subprocess.run(["gh", "release", "view", RELEASE_TAG], capture_output=True)
    release_exists = view.returncode == 0

    if not release_exists and view.stderr and b"release not found" not in view.stderr.lower():
        print(
            f"gh release view exited {view.returncode} for a reason other than "
            f"'release not found' -- proceeding as release-absent:\n"
            f"{view.stderr.decode(errors='replace')}",
            file=sys.stderr,
        )

    for cmd in build_release_publish_commands(release_exists, asset_names):
        subprocess.run(cmd, check=True, cwd=target_dir)
    return 0


if __name__ == "__main__":
    # argv[1] is the directory every asset is read from; any further arguments name the
    # assets to publish. With none, the core defaults to the dbt Docs site alone.
    sys.exit(main(sys.argv[1], sys.argv[2:]))
