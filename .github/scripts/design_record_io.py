"""I/O for ci/design-drift: the PR's changed paths and their contents.

Shared by design_drift_runner. No gate logic here.
"""
from __future__ import annotations

import os


def read_changed_paths(path: str) -> list[str]:
    with open(path) as f:
        return [line.strip() for line in f if line.strip()]


def read_contents(paths: list[str]) -> dict[str, str]:
    contents = {}
    for path in paths:
        if os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                contents[path] = f.read()
    return contents
