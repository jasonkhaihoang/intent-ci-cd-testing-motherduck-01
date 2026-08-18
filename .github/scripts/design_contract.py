"""Parse Schedule and Semantic Model sections from intent/<slug>/design.md."""
import re

import yaml


_H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _section_body(text: str, title: str) -> str | None:
    headings = list(_H2.finditer(text))
    for idx, heading in enumerate(headings):
        if heading.group(1).strip().lower() != title.lower():
            continue
        start = heading.end()
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(text)
        return text[start:end]
    return None


def _yaml_block(section: str | None) -> str | None:
    if section is None:
        return None
    match = re.search(r"```yaml\s*\n(.*?)```", section, re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else None


def _load(block: str, label: str) -> dict:
    try:
        return yaml.safe_load(block) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{label} section YAML invalid: {exc}") from exc


def parse_design_sections(design_text: str) -> dict:
    out = {"schedule": None, "metrics": None}

    schedule_block = _yaml_block(_section_body(design_text, "Schedule"))
    if schedule_block is not None:
        data = _load(schedule_block, "Schedule")
        out["schedule"] = [
            {
                "name": str(entry["name"]),
                "cron": str(entry["cron"]),
                "timezone": str(entry["timezone"]),
                "selector": str(entry["selector"]),
                "engine": str(entry["engine"]),
                "depends_on": list(entry.get("depends_on", [])),
                "retries": int(entry.get("retries", 0)),
            }
            for entry in data.get("schedules", [])
        ]

    metrics_block = _yaml_block(_section_body(design_text, "Semantic Model"))
    if metrics_block is not None:
        data = _load(metrics_block, "Semantic Model")
        out["metrics"] = [str(metric) for metric in data.get("metrics", [])]

    return out
