"""Which model design records a PR touches (pure).

The Build agent writes durable design records under docs/design/** (model, pipeline, area);
there is no per-intent design document. ci/design-drift reads only the model records a PR
changes, so the shell passes the PR's changed paths and their contents.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import yaml

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass(frozen=True)
class DesignRecord:
    path: str
    kind: str
    artifacts: tuple[str, ...]
    text: str


def _artifacts(path: str, text: str) -> tuple[str, ...]:
    match = _FRONTMATTER.match(text)
    if not match:
        return ()
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return ()
    if not isinstance(data, dict):
        raise ValueError(f"{path}: frontmatter must be a mapping")
    return tuple(str(name) for name in data.get("artifacts") or [])


def _kind(path: str) -> str:
    if path.startswith("docs/design/models/"):
        return "model"
    return "other"


def select_design_records(changed_paths: list[str], contents: dict[str, str]) -> list[DesignRecord]:
    return [
        DesignRecord(path, _kind(path), _artifacts(path, contents[path]), contents[path])
        for path in sorted(changed_paths)
        if path.startswith("docs/design/") and path.endswith(".md") and path in contents
    ]
