"""ci/orchestration engine for the platform-neutral Schedule design contract."""
import re

_FIELD_MAX = (59, 23, 31, 12, 7)


def validate_cron(expr: str) -> bool:
    fields = expr.split()
    if len(fields) != 5:
        return False
    for field, max_value in zip(fields, _FIELD_MAX):
        for part in field.split(","):
            part = re.sub(r"/\d+$", "", part)
            if part == "*":
                continue
            match = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
            if not match:
                return False
            low = int(match.group(1))
            high = int(match.group(2)) if match.group(2) else low
            if low > high or high > max_value:
                return False
    return True


def _topo_ok(entries: list[dict]) -> bool:
    names = {entry["name"] for entry in entries if "name" in entry}
    deps = {entry["name"]: list(entry.get("depends_on", [])) for entry in entries if "name" in entry}
    if any(dep not in names for values in deps.values() for dep in values):
        return False
    state = {}

    def visit(name: str) -> bool:
        if state.get(name) == 1:
            return False
        if state.get(name) == 2:
            return True
        state[name] = 1
        if not all(visit(dep) for dep in deps[name]):
            return False
        state[name] = 2
        return True

    return all(visit(name) for name in names)


def run_orchestration_gate(schedule: list[dict] | None,
                           dbt_model_names: set[str],
                           dlt_pipeline_names: set[str]) -> dict:
    if schedule is None:
        return {"skipped": True, "findings": []}

    findings = []

    def add(rule: str, severity: str, message: str) -> None:
        findings.append({"rule": rule, "severity": severity, "message": message})

    seen = set()
    for entry in schedule:
        missing = [key for key in ("name", "cron", "timezone", "selector", "engine", "depends_on") if key not in entry]
        if missing:
            add("schedule-schema", "critical", f"schedule entry missing {missing}: {entry}")
            continue
        if entry["name"] in seen:
            add("schedule-schema", "critical", f"duplicate schedule name: {entry['name']}")
        seen.add(entry["name"])
        if entry["engine"] not in ("dbt", "dlt"):
            add("schedule-schema", "critical", f"schedule '{entry['name']}': engine must be dbt or dlt")
            continue
        if not validate_cron(entry["cron"]):
            add("cron-parses", "critical", f"schedule '{entry['name']}': invalid cron {entry['cron']!r}")
        pool = dbt_model_names if entry["engine"] == "dbt" else dlt_pipeline_names
        if entry["selector"] not in pool:
            add("no-orphan-schedule", "critical", f"schedule '{entry['name']}': selector {entry['selector']!r} resolves to no {entry['engine']} artifact")
        if int(entry.get("retries", 0)) > 3:
            add("retry-sla-sane", "advisory", f"schedule '{entry['name']}': retries={entry.get('retries')} > 3")

    if schedule and not _topo_ok(schedule):
        add("dag-acyclic-and-resolvable", "critical", "schedule dependency graph has a cycle or unresolved depends_on")

    return {"skipped": False, "findings": findings}
