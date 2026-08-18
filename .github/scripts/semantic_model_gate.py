"""ci/semantic-model engine — static validation of dbt MetricFlow objects.

Pure engine over a parsed dbt manifest's `semantic_models` and `metrics`. dbt parse owns
MetricFlow parsing into the manifest; this gate does not walk YAML files. Checks are static:
design conformance, model-dependency resolution, measure-reference resolution, and metadata
presence. Live `mf query` verification (AC-43) is deferred.

C5 protocol: returns {"skipped": bool, "findings": [{"rule", "severity", "message"}]}.
"""


def _measure_refs(metric: dict) -> set[str]:
    """Collect measure names a metric references, tolerant of dbt metric shapes."""
    params = metric.get("type_params") or {}
    refs = set()
    measure = params.get("measure")
    if isinstance(measure, dict) and measure.get("name"):
        refs.add(measure["name"])
    for key in ("measures", "input_measures"):
        for item in params.get(key) or []:
            if isinstance(item, dict) and item.get("name"):
                refs.add(item["name"])
    for key in ("numerator", "denominator"):
        part = params.get(key)
        if isinstance(part, dict) and part.get("name"):
            refs.add(part["name"])
    return refs


def run_semantic_model_gate(manifest: dict, design_metrics: list[str] | None) -> dict:
    semantic_models = manifest.get("semantic_models") or {}
    metrics = manifest.get("metrics") or {}
    nodes = manifest.get("nodes") or {}

    has_semantic_objects = bool(semantic_models) or bool(metrics)
    if not has_semantic_objects and design_metrics is None:
        return {"skipped": True, "findings": []}

    findings = []

    def add(rule: str, severity: str, message: str) -> None:
        findings.append({"rule": rule, "severity": severity, "message": message})

    # metricflow-parses: every semantic model's model dependency resolves in the manifest.
    for uid, sm in semantic_models.items():
        deps = (sm.get("depends_on") or {}).get("nodes") or []
        for dep in deps:
            if dep not in nodes:
                add("metricflow-parses", "critical",
                    f"semantic model '{sm.get('name', uid)}': model dependency {dep!r} not in manifest")

    # references-resolve: every measure a metric references exists among semantic-model measures.
    all_measures = {
        measure["name"]
        for sm in semantic_models.values()
        for measure in (sm.get("measures") or [])
        if measure.get("name")
    }
    for uid, metric in metrics.items():
        for ref in _measure_refs(metric):
            if ref not in all_measures:
                add("references-resolve", "critical",
                    f"metric '{metric.get('name', uid)}': measure {ref!r} resolves to no semantic-model measure")

    # metadata-present: semantic models, metrics, and measures carry descriptions.
    for uid, sm in semantic_models.items():
        if not (sm.get("description") or "").strip():
            add("metadata-present", "critical", f"semantic model '{sm.get('name', uid)}' has no description")
        for measure in sm.get("measures") or []:
            if not (measure.get("description") or "").strip():
                add("metadata-present", "critical",
                    f"measure '{measure.get('name', '?')}' in '{sm.get('name', uid)}' has no description")
    for uid, metric in metrics.items():
        if not (metric.get("description") or "").strip():
            add("metadata-present", "critical", f"metric '{metric.get('name', uid)}' has no description")

    # design-conformance: the design contract is the source of truth for declared metrics.
    metric_names = {m.get("name") for m in metrics.values()}
    if design_metrics is None:
        if has_semantic_objects:
            add("design-conformance", "critical",
                "manifest declares semantic objects but the design contract has no ## Semantic Model section")
    else:
        for declared in design_metrics:
            if declared not in metric_names:
                add("design-conformance", "critical",
                    f"design contract declares metric {declared!r} but it is absent from the MetricFlow definitions")

    return {"skipped": False, "findings": findings}
