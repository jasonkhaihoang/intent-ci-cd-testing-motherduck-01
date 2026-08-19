"""Local authoring-time preview of the design-contract gates — no GitHub I/O.

Runs the same pure engines as ci/orchestration and ci/semantic-model against a locally-parsed
design.md + manifest.json, prints a findings table, and exits non-zero iff any critical finding.
Gather helpers are shared with the CI runners so preview and CI never diverge.

CLI (pinned — vd-data-engineering PL-2 calls this):
    gate_preview.py --intent-id intent/<slug> --manifest <proj>/target/manifest.json \\
        --orchestration-dir orchestration

Exit 0 = all gates pass or skip; exit 1 iff any critical finding.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from design_contract import parse_design_sections
from orchestration_gate import run_orchestration_gate
from orchestration_gate_runner import _dbt_model_names, _dlt_pipeline_names
from semantic_model_gate import run_semantic_model_gate


def _read_text(path: str) -> str:
    with open(path) as f:
        return f.read()


def _render(context: str, result: dict) -> str:
    if result.get("skipped"):
        return f"{context}: SKIPPED — no design-contract section declared"
    findings = result.get("findings") or []
    if not findings:
        return f"{context}: PASS"
    lines = [f"{context}:"]
    for finding in findings:
        lines.append(f"  [{finding['severity']}] {finding['rule']}: {finding['message']}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Local preview of design-contract gates.")
    parser.add_argument("--intent-id", required=True, help="e.g. intent/<slug>")
    parser.add_argument("--manifest", required=True, help="path to target/manifest.json")
    parser.add_argument("--orchestration-dir", default="orchestration",
                        help="directory scanned for dlt pipeline definitions")
    args = parser.parse_args(argv)

    design_text = _read_text(f"{args.intent_id}/design.md")
    sections = parse_design_sections(design_text)
    manifest = json.loads(_read_text(args.manifest)) if os.path.isfile(args.manifest) else {}

    orchestration = run_orchestration_gate(
        sections["schedule"],
        _dbt_model_names(manifest),
        _dlt_pipeline_names(args.orchestration_dir),
    )
    semantic = run_semantic_model_gate(manifest, sections["metrics"])

    print(_render("ci/orchestration", orchestration))
    print(_render("ci/semantic-model", semantic))

    critical = [
        f for result in (orchestration, semantic)
        for f in result.get("findings", [])
        if f["severity"] == "critical"
    ]
    if critical:
        print(f"\n{len(critical)} critical finding(s) — gates would block.")
        return 1
    print("\nNo critical findings — gates would pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
