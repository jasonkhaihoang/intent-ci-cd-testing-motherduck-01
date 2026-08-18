"""dbt manifest domain module.

One Manifest type loaded once per script, encapsulating project-owned filtering,
physical-model filtering, dbt 1.8+ test indexing and dbt <1.8 inline-test
fallback, source vs node lookup, and upstream walking. Pure after construction.

Public surface:
  Manifest.from_path(path) / .from_dict(d)
  .own_models()                       — uid -> node, project-owned models only
  .physical_models()                  — uid -> node, excludes view/ephemeral
  .tests_for(model_uid)               — set of test names attached to model
  .pk_tests_for(model_uid, column)    — set of test names for one column
  .upstreams_of(uid)                  — recursive depends_on.nodes walk
  .node(uid)                          — node lookup; None if absent
  .source(uid)                        — source lookup; None if absent
"""
from __future__ import annotations

import json
import os
from typing import Iterable


_NON_PHYSICAL_MATERIALIZATIONS = {"view", "ephemeral"}


class Manifest:
    """Domain wrapper around a dbt manifest dict. Zero I/O after construction."""

    def __init__(self, raw: dict) -> None:
        self._raw = raw or {}
        self._nodes: dict = self._raw.get("nodes") or {}
        self._sources: dict = self._raw.get("sources") or {}
        self._project_name: str | None = (self._raw.get("metadata") or {}).get("project_name")
        # Lazy indices, built on first access.
        self._tests_by_model: dict[str, set[str]] | None = None
        self._tests_by_model_col: dict[tuple[str, str], set[str]] | None = None

    # ─── construction ────────────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, raw: dict) -> "Manifest":
        return cls(raw)

    @classmethod
    def from_path(cls, path: str) -> "Manifest":
        if not os.path.exists(path):
            return cls({})
        with open(path) as f:
            return cls(json.load(f))

    # ─── model filters ───────────────────────────────────────────────────────

    def own_models(self) -> dict[str, dict]:
        """Project-owned models only. Filters by package_name == project_name."""
        return {uid: n for uid, n in self._nodes.items() if self._is_own_model(n)}

    def physical_models(self) -> dict[str, dict]:
        """Project-owned models with a physical materialization (excludes view/ephemeral)."""
        return {uid: n for uid, n in self.own_models().items() if not self._is_non_physical(n)}

    def _is_own_model(self, node: dict) -> bool:
        if node.get("resource_type") != "model":
            return False
        if self._project_name:
            return node.get("package_name") == self._project_name
        return True

    @staticmethod
    def _is_non_physical(node: dict) -> bool:
        materialized = (node.get("config") or {}).get("materialized", "")
        return materialized in _NON_PHYSICAL_MATERIALIZATIONS

    # ─── test indices ────────────────────────────────────────────────────────

    def _build_test_indices(self) -> None:
        """Build dbt 1.8+ test-node indices keyed by (model_uid) and (model_uid, column)."""
        by_model: dict[str, set[str]] = {}
        by_col: dict[tuple[str, str], set[str]] = {}
        for node in self._nodes.values():
            rtype = node.get("resource_type")
            if rtype not in ("test", "unit_test"):
                continue
            attached = node.get("attached_node") or node.get("model")
            if not attached:
                continue
            test_name = (node.get("test_metadata") or {}).get("name") or node.get("name") or ""
            # Always register the attachment even if the test has no extractable name —
            # callers that just check "does this model have any test?" rely on presence.
            by_model.setdefault(attached, set()).add(test_name)
            col = node.get("column_name") or ""
            if col and test_name:
                by_col.setdefault((attached, col), set()).add(test_name)
        self._tests_by_model = by_model
        self._tests_by_model_col = by_col

    def tests_for(self, model_uid: str) -> set[str]:
        """Return the set of test names attached to a model (dbt 1.8+ test nodes)."""
        if self._tests_by_model is None:
            self._build_test_indices()
        return set(self._tests_by_model.get(model_uid, set()))  # type: ignore[union-attr]

    def pk_tests_for(self, model_uid: str, column: str) -> set[str]:
        """Return test names for a column, merging dbt 1.8+ test nodes and <1.8 inline."""
        if self._tests_by_model_col is None:
            self._build_test_indices()
        from_nodes = set(self._tests_by_model_col.get((model_uid, column), set()))  # type: ignore[union-attr]
        node = self._nodes.get(model_uid) or {}
        col = (node.get("columns") or {}).get(column) or {}
        return from_nodes | _column_inline_tests(col)

    # ─── upstream walking ────────────────────────────────────────────────────

    def upstreams_of(self, uid: str) -> set[str]:
        """Recursively walk depends_on.nodes; return reachable IDs (excluding start)."""
        seen: set[str] = set()
        stack: list[str] = [uid]
        while stack:
            current = stack.pop()
            node = self._nodes.get(current) or self._sources.get(current)
            if node is None:
                continue
            for dep in (node.get("depends_on") or {}).get("nodes") or []:
                if dep == uid or dep in seen:
                    continue
                seen.add(dep)
                stack.append(dep)
        return seen

    # ─── node / source lookup ────────────────────────────────────────────────

    def node(self, uid: str) -> dict | None:
        return self._nodes.get(uid)

    def source(self, uid: str) -> dict | None:
        return self._sources.get(uid)

    @property
    def nodes(self) -> dict:
        """Underlying nodes dict — used by consumers that iterate the full node table."""
        return self._nodes


def _column_inline_tests(col: dict) -> set[str]:
    raw = col.get("data_tests", col.get("tests", [])) or []
    return _normalize_test_names(raw)


def _normalize_test_names(raw: Iterable) -> set[str]:
    out: set[str] = set()
    for t in raw:
        if isinstance(t, dict):
            name = t.get("name") or ""
        else:
            name = str(t)
        if name:
            out.add(name)
    return out
