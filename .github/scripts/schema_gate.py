"""
Diff-scoped schema gate.

For each model whose source file appears in the PR diff, enforces:
  - non-empty description
  - at least one data test (data_tests or tests key)
  - config.meta.owner present and non-empty

Exit 0 if all pass; exit 1 on any violation, with report written to --output.
"""

import argparse
import json
import os
import subprocess
import sys

from dbt_manifest import Manifest


def get_pr_changed_files(repo: str, base_sha: str, head_sha: str) -> set[str]:
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/compare/{base_sha}...{head_sha}",
         "--jq", ".files[].filename"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Error: failed to get PR diff: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    lines = result.stdout.strip().splitlines()
    return set(lines) if lines else set()


def check_model(node: dict, tested_model_ids: set | None = None) -> list[str]:
    """Return list of rule violation names for a single model node.

    `tested_model_ids` is the set of model unique_ids that have attached test
    nodes (dbt 1.8+). When None, only inline `data_tests`/`tests` are considered.
    """
    issues = []
    if not node.get("description", "").strip():
        issues.append("missing_description")
    # Check both the inline data_tests field (dbt <1.8) and the separate test nodes (dbt 1.8+)
    inline_tests = node.get("data_tests", node.get("tests", []))
    has_tests = bool(inline_tests) or (
        tested_model_ids is not None and node.get("unique_id") in tested_model_ids
    )
    if not has_tests:
        issues.append("missing_tests")
    owner = node.get("config", {}).get("meta", {}).get("owner", "")
    if not str(owner).strip():
        issues.append("missing_owner")
    return issues


def run_gate(manifest: dict | Manifest, changed_files: set[str]) -> dict:
    """Evaluate schema rules for every model whose source file is in changed_files."""
    m = manifest if isinstance(manifest, Manifest) else Manifest.from_dict(manifest)
    violations = []
    models_evaluated = 0

    for uid, node in m.nodes.items():
        if node.get("resource_type") != "model":
            continue
        if node.get("original_file_path", "") not in changed_files:
            continue
        models_evaluated += 1
        # Treat any attached test (incl. column-level) as satisfying the model-level requirement.
        tested_ids = {uid} if m.tests_for(uid) else set()
        issues = check_model(node, tested_ids)
        if issues:
            violations.append({
                "model": node.get("name", ""),
                "path": node.get("original_file_path", ""),
                "issues": issues,
            })

    return {
        "passed": len(violations) == 0,
        "models_evaluated": models_evaluated,
        "violations": violations,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="target/manifest.json")
    parser.add_argument("--repo", required=True, help="owner/repo slug")
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--output", default="reports/schema_gate.json")
    args = parser.parse_args()

    if not os.path.exists(args.manifest):
        out_dir = os.path.dirname(args.output)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump({"passed": False, "models_evaluated": 0, "violations": [],
                       "error": "manifest not found — dbt compile or parse may have failed"}, f)
        print(f"Error: manifest not found at {args.manifest}", file=sys.stderr)
        sys.exit(1)

    manifest = Manifest.from_path(args.manifest)
    changed_files = get_pr_changed_files(args.repo, args.base_sha, args.head_sha)
    result = run_gate(manifest, changed_files)

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)

    if not result["passed"]:
        for v in result["violations"]:
            print(f"FAIL {v['model']} ({v['path']}): {', '.join(v['issues'])}", file=sys.stderr)
        sys.exit(1)

    print(f"Schema gate passed: {result['models_evaluated']} model(s) evaluated.")


if __name__ == "__main__":
    main()
