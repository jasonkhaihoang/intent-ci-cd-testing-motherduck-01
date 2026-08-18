"""
Fetch prod-state/manifest.json for Slim CI deferral (AWAP v1.4 Phase 2).

Modes (from ci-config.yml prod_manifest_source.mode):
  artifact  — download the manifests from the fixed-tag CD release via gh CLI (default)
  onelake   — download from OneLake Files path via Fabric UAMI

Falls back to greenfield dbt parse when no manifest is available.

Outputs:
  prod-state/manifest.json
  prod-state/source.json  — {mode, source, head_sha, retrieved_at}
  GITHUB_OUTPUT: greenfield_fallback=true|false
"""

import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from typing import NamedTuple

import ci_config
import fabric_transport
import runner_io
# Same literal the CD publish uploads to — imported rather than restated so the
# read and write sides cannot drift apart.
from dbt_docs_publish import RELEASE_TAG


ONELAKE_DFS = "https://onelake.dfs.fabric.microsoft.com"


# ─── Artifact-mode result types (VD-1596 Phase 2) ─────────────────────────────
#
# Artifact mode distinguishes three outcomes:
#   - success    : manifest fetched and written to prod-state/
#   - greenfield : zero successful CD runs on `main` ever — operator should
#                  expect a full build. Caller invokes fetch_greenfield().
#   - error      : any other fetch failure. Caller must NOT collapse to
#                  greenfield; instead exit non-zero with category + reason
#                  so the PR comment can route the operator to remediation.
#
# Categories (artifact mode):
#   transient — gh CLI non-zero, retryable stderr, network/timeout
#   parse     — manifest absent from the release, or invalid JSON inside it
# (`config` is onelake-mode-only since VD-4418: artifact mode reads a fixed tag and
# has no required ci-config.yml key left to be missing.)
# (`auth` is onelake-mode-only, not reachable in artifact mode which uses the
# repo `GITHUB_TOKEN` — see §4.2 of the design doc and OnelakeResult below.)

class ArtifactResult(NamedTuple):
    status: str  # "success" | "greenfield" | "error"
    category: str | None = None
    reason: str | None = None


# ─── Onelake-mode result type (VD-3216) ───────────────────────────────────────
#
# Mirrors ArtifactResult. A 404 on the fixed canonical OneLake manifest path is
# the confirmed-greenfield signal: domain-deploy always publishes to this same
# path with no retention/rotation window, so 404 there is structurally
# equivalent to artifact mode's "zero successful CD runs ever". Any other
# failure is a platform error — never collapsed to greenfield.
#
# Categories (onelake mode):
#   config    — missing workspace_id/lakehouse_id/file_path in ci-config.yml
#   auth      — Fabric UAMI token acquisition failure, or 401/403 on the fetch
#   transient — 5xx, network error, or timeout
#   parse     — response body is not valid JSON

class OnelakeResult(NamedTuple):
    status: str  # "success" | "greenfield" | "error"
    category: str | None = None
    reason: str | None = None


# ─── Output helpers ───────────────────────────────────────────────────────────

def write_source_json(mode: str, source: str, head_sha: str) -> None:
    os.makedirs("prod-state", exist_ok=True)
    data = {
        "mode": mode,
        "source": source,
        "head_sha": head_sha,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    with open("prod-state/source.json", "w") as f:
        json.dump(data, f, indent=2)


# ─── Fetch modes ──────────────────────────────────────────────────────────────

def _repo_is_visible(repo: str) -> bool:
    """Whether the acting token can read `repo` at all.

    Disambiguates the 404 `gh` reports for a genuinely absent release from the 404 it
    reports for a repo the token cannot see. A non-zero exit here is itself treated as
    "not visible": if we cannot establish visibility we must not claim greenfield.
    """
    probe = subprocess.run(
        ["gh", "api", f"repos/{repo}", "--silent"], capture_output=True, text=True
    )
    return probe.returncode == 0


def fetch_artifact_mode(cfg: dict) -> ArtifactResult:
    """Download the manifests from the fixed-tag CD release.

    Returns an ArtifactResult — see ArtifactResult docstring for the three
    possible statuses and category mapping.

    The manifests moved from an Actions artifact to a release asset (VD-4418) so
    an Intent can read them too: a release asset is repository *contents*, which
    the brokered agent GitHub token covers, while `gh run download` needs Actions
    read, which it excludes. The mode keeps the name `artifact` because it is the
    operator-facing `prod_manifest_source.mode` value and the alternative is
    still `onelake`; only the transport underneath changed.
    """
    repo = os.environ.get("REPO", "")
    head_sha = os.environ.get("HEAD_SHA", "")

    with tempfile.TemporaryDirectory() as tmpdir:
        dl_result = subprocess.run(
            [
                "gh", "release", "download", RELEASE_TAG,
                # Matches manifest.json and manifest_prod.json, and excludes the
                # docs asset that shares this release.
                "--pattern", "manifest*.json",
                "--dir", tmpdir,
                "--repo", repo,
            ],
            capture_output=True, text=True,
        )
        if dl_result.returncode != 0:
            # `gh`'s channel placement for CLI error text is not a documented
            # contract — check both streams so the greenfield signal below is
            # not missed if a future `gh` version emits it on stdout.
            combined_output = f"{dl_result.stdout} {dl_result.stderr}".lower()
            if "release not found" in combined_output or "no assets match" in combined_output:
                # Two candidate greenfield signals, replacing "zero successful CD runs
                # ever": the release has never been cut, or it exists (the docs asset
                # is there) but carries no manifest yet. A domain's first-ever PR — and
                # a domain still on a bundle that predates VD-4418 — must reach
                # greenfield, not a platform error (VD-4402).
                #
                # But `gh` prints "release not found" for ANY 404 on the tag lookup,
                # including a repo the token cannot see and a workflow whose
                # `permissions:` block lost `contents: read` — both customer-editable.
                # Treating those as greenfield would silently full-rebuild while
                # reporting success, which is exactly what AC-14 forbids. The old
                # implementation had a structural signal (`if not runs:`) that this
                # wording match replaced, so confirm repo visibility before believing
                # the 404.
                if not _repo_is_visible(repo):
                    reason = (
                        f"Cannot read repository {repo} — the '{RELEASE_TAG}' release "
                        "lookup 404'd and so did the repository itself, so this is a "
                        "permission or visibility failure, not a missing release."
                    )
                    runner_io.warning(reason)
                    return ArtifactResult("error", "auth", reason)
                runner_io.notice(
                    "No prod manifest published on the CD release — true "
                    "greenfield (full build)."
                )
                return ArtifactResult("greenfield")
            reason = (
                f"gh release download failed for tag {RELEASE_TAG}: "
                f"{dl_result.stderr.strip() or 'exit ' + str(dl_result.returncode)}"
            )
            runner_io.warning(reason)
            return ArtifactResult("error", "transient", reason)

        manifest_src = os.path.join(tmpdir, "manifest.json")
        if not os.path.exists(manifest_src):
            # A release carrying manifest_prod.json but not manifest.json is a
            # malformed publish, not greenfield — never collapse it to one.
            reason = (
                f"manifest.json not found among the '{RELEASE_TAG}' release assets."
            )
            runner_io.warning(reason)
            return ArtifactResult("error", "parse", reason)

        # Validate the manifest is parseable JSON before declaring success —
        # downstream Slim CI will choke on a malformed file with a worse error.
        try:
            with open(manifest_src) as f:
                json.load(f)
        except (ValueError, OSError) as e:
            reason = (
                f"manifest.json on the '{RELEASE_TAG}' release is not valid JSON: {e}"
            )
            runner_io.warning(reason)
            return ArtifactResult("error", "parse", reason)

        os.makedirs("prod-state", exist_ok=True)
        shutil.copy2(manifest_src, "prod-state/manifest.json")
        # Also copy prod-target manifest for --defer resolution in gates 2/4 (VD-2142).
        manifest_prod_src = os.path.join(tmpdir, "manifest_prod.json")
        if os.path.exists(manifest_prod_src):
            shutil.copy2(manifest_prod_src, "prod-state/manifest_prod.json")

    # The release is clobbered in place on every publish, so it has no run id or
    # per-publish SHA to cite — the tag is the whole provenance.
    write_source_json(
        mode="artifact",
        source=f"{repo} release {RELEASE_TAG}",
        head_sha=head_sha,
    )
    print(f"Prod manifest fetched from the '{RELEASE_TAG}' release.", flush=True)
    return ArtifactResult("success")


def fetch_onelake_mode(cfg: dict) -> OnelakeResult:
    """Download manifest from OneLake Files path via Fabric UAMI.

    Returns an OnelakeResult — see OnelakeResult docstring for the three
    possible statuses and category mapping (VD-3216).
    """
    workspace_id = cfg.get("workspace_id", "")
    lakehouse_id = cfg.get("lakehouse_id", "")
    file_path = cfg.get("file_path", "")
    head_sha = os.environ.get("HEAD_SHA", "")

    if not all([workspace_id, lakehouse_id, file_path]):
        reason = (
            "prod_manifest_source.workspace_id, lakehouse_id, and file_path "
            "are all required for onelake mode."
        )
        runner_io.error(reason)
        return OnelakeResult("error", "config", reason)

    base_url = os.environ.get("ONELAKE_DFS_BASE_URL", ONELAKE_DFS)
    url = f"{base_url}/{workspace_id}/{lakehouse_id}/{file_path}"

    try:
        token = fabric_transport.get_token("storage")
    except (subprocess.CalledProcessError, ValueError, KeyError) as e:
        reason = f"Fabric UAMI token acquisition failed: {e}"
        runner_io.warning(reason)
        return OnelakeResult("error", "auth", reason)

    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # The single legitimate greenfield signal: domain-deploy always
            # publishes to this same fixed path with no retention window, so
            # a 404 there is the onelake equivalent of "zero prior publishes".
            runner_io.notice(
                "No manifest found at the OneLake prod-state path — true "
                "greenfield (full build)."
            )
            return OnelakeResult("greenfield")
        category = "auth" if e.code in (401, 403) else "transient"
        reason = f"OneLake manifest fetch failed (HTTP {e.code})."
        runner_io.warning(reason)
        return OnelakeResult("error", category, reason)
    except urllib.error.URLError as e:
        reason = f"OneLake manifest fetch failed (network error): {e.reason}"
        runner_io.warning(reason)
        return OnelakeResult("error", "transient", reason)

    # Validate the manifest is parseable JSON before declaring success —
    # mirrors artifact mode's parse validation.
    try:
        json.loads(content)
    except ValueError as e:
        reason = f"OneLake manifest at {file_path} is not valid JSON: {e}"
        runner_io.warning(reason)
        return OnelakeResult("error", "parse", reason)

    os.makedirs("prod-state", exist_ok=True)
    with open("prod-state/manifest.json", "wb") as f:
        f.write(content)

    write_source_json(
        mode="onelake",
        source=f"{workspace_id}/{lakehouse_id}/{file_path}",
        head_sha=head_sha,
    )
    print(f"OneLake manifest fetched from {url}.", flush=True)
    return OnelakeResult("success")


def fetch_greenfield() -> None:
    """Emit a minimal `prod-state/manifest.json` so `state:modified+` selects everything.

    Greenfield = no CD-published manifest available. By design we want Slim CI to
    degrade to a full build (every model is `state:new` against the empty previous
    state). To do that we always write a minimal manifest with `nodes: {}` and
    `sources: {}` — the parse output of the current branch is NEVER used as the
    `--state` source, because that would make `state:modified+` resolve to ∅ and
    Slim CI would silently build nothing.

    A best-effort `dbt deps` + `dbt parse` runs purely as a diagnostic so project-
    level errors surface in the CI log; their outputs are intentionally discarded.
    See ephemeral-ci-workflow-design-v1.4.md §4.3.
    """
    head_sha = os.environ.get("HEAD_SHA", "")
    print("⚠️  No prod manifest available — greenfield fallback (full build).", flush=True)

    # Diagnostic only: surface project-level errors. Output NOT used as prod manifest.
    deps = subprocess.run(
        ["dbt", "deps", "--profiles-dir", ".github/profiles", "--target", "dbt_quality"],
        capture_output=True, text=True,
    )
    if deps.returncode != 0:
        runner_io.warning(
            f"dbt deps failed (exit {deps.returncode}). "
            f"stdout/stderr (first 300 chars): "
            f"{(deps.stdout + deps.stderr)[:300]}"
        )

    parse = subprocess.run(
        [
            "dbt", "parse",
            "--profiles-dir", ".github/profiles",
            "--target", "dbt_quality",
            "--exclude", "package:elementary",
        ],
        capture_output=True, text=True,
    )
    if parse.returncode != 0:
        # dbt prints parse errors to stdout (not stderr); include both.
        runner_io.warning(
            f"dbt parse failed (exit {parse.returncode}). "
            f"stdout/stderr (first 500 chars): "
            f"{(parse.stdout + parse.stderr)[:500]}"
        )

    # Always emit minimal manifest. Empty `nodes` makes every current-branch
    # model count as `state:new`, so `state:modified+` selects everything →
    # Slim CI degrades to a full build. This is the design intent for
    # greenfield: AWAP v1.4 §4.3.
    os.makedirs("prod-state", exist_ok=True)
    minimal = {
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json",
            "dbt_version": "0.0.0",
        },
        "nodes": {},
        "sources": {},
        "macros": {},
        "docs": {},
        "exposures": {},
        "metrics": {},
        "groups": {},
        "selectors": {},
        "disabled": {},
        "parent_map": {},
        "child_map": {},
        "group_map": {},
        "saved_queries": {},
        "semantic_models": {},
        "unit_tests": {},
        "functions": {},
    }
    with open("prod-state/manifest.json", "w") as f:
        json.dump(minimal, f, indent=2)
    write_source_json(
        mode="greenfield",
        source="minimal manifest (full build — no prod state available)",
        head_sha=head_sha,
    )


# ─── Config ───────────────────────────────────────────────────────────────────

def load_config() -> dict | None:
    """Return parsed ci-config.yml, or None when the file is absent.

    A wholly missing ci-config.yml means the repo has not been onboarded to
    Slim CI; callers treat that as greenfield (not a platform error).
    """
    config_path = ci_config.locate_ci_config()
    if not os.path.exists(config_path):
        runner_io.warning("ci-config.yml not found — using greenfield fallback.")
        return None
    with open(config_path) as f:
        yaml_str = f.read()
    return ci_config.parse_ci_config(yaml_str)["config"]


# ─── Entry point ──────────────────────────────────────────────────────────────

def _emit_platform_error(mode: str, category: str, reason: str) -> None:
    """Surface a non-greenfield platform error to the runner + PR comment path.

    Writes structured outputs that `ci.yml`'s "Post gate-1 comment" step picks
    up and renders via `notify_render.render_gate_1_comment(... platform_error=…)`.
    Does NOT write `prod-state/source.json` with `mode: greenfield` — by design,
    a platform error must be distinguishable from a true greenfield run.
    """
    runner_io.set_output("greenfield_fallback", "false")
    runner_io.set_output("mode", mode)
    runner_io.set_output("category", category)
    runner_io.set_output("reason", reason)
    runner_io.error(f"Platform error ({mode}/{category}): {reason}")


def _apply_fetch_result(mode: str, result: ArtifactResult | OnelakeResult) -> None:
    """Dispatch on a fetch result's status — shared by artifact and onelake mode.

    Both ArtifactResult and OnelakeResult carry the same (status, category,
    reason) shape, so the success/greenfield/error branching is identical;
    only the mode name threaded into the platform-error output differs.
    """
    if result.status == "success":
        runner_io.set_output("greenfield_fallback", "false")
    elif result.status == "greenfield":
        fetch_greenfield()
        runner_io.set_output("greenfield_fallback", "true")
    else:  # error — distinguish from greenfield, exit non-zero
        _emit_platform_error(mode, result.category or "transient", result.reason or "")
        sys.exit(1)


def main() -> None:
    config = load_config()
    if config is None:
        # Repo not onboarded to Slim CI — greenfield without platform-error
        # noise. Preserves backwards compatibility for un-onboarded repos.
        fetch_greenfield()
        runner_io.set_output("greenfield_fallback", "true")
        print("fetch-prod-state complete.", flush=True)
        return

    manifest_cfg = config.get("prod_manifest_source") or {}
    mode = manifest_cfg.get("mode", "artifact")

    if mode == "artifact":
        _apply_fetch_result("artifact", fetch_artifact_mode(manifest_cfg))
    elif mode == "onelake":
        _apply_fetch_result("onelake", fetch_onelake_mode(manifest_cfg))
    else:
        runner_io.warning(f"Unknown prod_manifest_source.mode '{mode}' — using greenfield fallback.")
        fetch_greenfield()
        runner_io.set_output("greenfield_fallback", "true")

    print("fetch-prod-state complete.", flush=True)


if __name__ == "__main__":
    main()
