"""Shared dbt ls invocation with file-based cache.

run_dbt_ls(cache_path) — invoke `dbt ls --select state:modified+` at most once
per provision run. On first call (cache miss) the subprocess is executed and the
result written to cache_path. On second call (cache hit) the cached list is
returned immediately without spawning a subprocess.

sys.exit(1) on non-zero subprocess returncode.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

try:
    from scripts import runner_io
except ImportError:
    import runner_io

def _make_dbt_ls_cmd(selector: str) -> list[str]:
    """Build the dbt ls command, honouring DBT_COMPILE_PROFILE / DBT_COMPILE_TARGET env vars.

    Defaults preserve Fabric behaviour (--target dbt_fabric_compile, no --profile).
    MotherDuck mode sets DBT_COMPILE_PROFILE=dbt_motherduck_compile and
    DBT_COMPILE_TARGET=compile via the workflow env block.
    """
    profile = os.environ.get("DBT_COMPILE_PROFILE", "")
    target = os.environ.get("DBT_COMPILE_TARGET", "dbt_fabric_compile")
    cmd = [
        "dbt", "ls",
        "--project-dir", os.environ.get("PROJ", "."),
        "--select", selector,
        "--resource-type", "model", "snapshot",
        "--state", os.path.abspath("prod-state"),
        "--output", "json",
        "--profiles-dir", ".github/profiles",
    ]
    if profile:
        cmd.extend(["--profile", profile])
    cmd.extend(["--target", target])
    return cmd


def _run_dbt_ls_cmd(cmd: list[str], cache_path: str, label: str) -> list[str]:
    """Shared cache-backed dbt ls runner. Returns unique_ids as a list.

    sys.exit(1) on non-zero subprocess returncode.
    """
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        runner_io.error(
            f"{label} failed (exit {result.returncode}). "
            f"stdout/stderr (first 500 chars): {(result.stdout + result.stderr)[:500]}"
        )
        sys.exit(1)

    unique_ids: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        uid = entry.get("unique_id")
        if uid:
            unique_ids.append(uid)

    cache_dir = os.path.dirname(cache_path)
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(unique_ids, f)

    return unique_ids


def run_dbt_ls(cache_path: str = "reports/dbt_ls_cache.json") -> list[str]:
    """Return unique_ids from `dbt ls state:modified+`, using a file cache.

    Reads from cache_path if it exists (cache hit — no subprocess).
    Otherwise runs the subprocess, writes the result to cache_path, and returns.
    sys.exit(1) on non-zero subprocess returncode.
    """
    return _run_dbt_ls_cmd(_make_dbt_ls_cmd("state:modified+"), cache_path, "dbt ls")


def run_dbt_ls_modified(cache_path: str = "reports/dbt_ls_modified_cache.json") -> set[str]:
    """Return unique_ids from `dbt ls state:modified` (no +), using a file cache.

    Returns a set — callers use this to distinguish roots from descendants.
    sys.exit(1) on non-zero subprocess returncode.
    """
    return set(_run_dbt_ls_cmd(_make_dbt_ls_cmd("state:modified"), cache_path, "dbt ls (state:modified)"))
