from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import curaflow.cli as cli
from curaflow.dag import SourceSpec
from curaflow.plugin_registry import source_plugin

_current_running = 0
_max_running_seen = 0


@source_plugin("test_concurrent_source")
async def _concurrent_source(
    name: str, params: dict[str, object]
) -> tuple[bool, dict[str, object], list[dict[str, object]]]:
    """Test plugin that simulates work to exercise concurrency limits."""
    global _current_running, _max_running_seen
    _current_running += 1
    _max_running_seen = max(_max_running_seen, _current_running)
    # Small sleep to allow overlap if concurrency is >1
    await asyncio.sleep(0.01)
    _current_running -= 1
    return True, {"name": name, "params": params}, []


@source_plugin("test_dynamic_source")
async def _dynamic_source(
    name: str, params: dict[str, object]
) -> tuple[bool, dict[str, object], list[dict[str, object]]]:
    """Test plugin that emits a single dynamic child source when run on the root."""
    if name == "root":
        children: list[dict[str, object]] = [
            {
                "name": "child",
                "plugin": "test_dynamic_source",
                "params": {},
            }
        ]
        return True, {"name": name}, children
    # Children themselves do not fan out further
    return False, {"name": name}, []


def _override_app_dirs(tmp_path: Path) -> dict[str, Path]:
    """Point APP_DIRS to a temporary workspace, returning the previous mapping."""
    old = {k: v for k, v in cli.APP_DIRS.items()}
    cli.APP_DIRS.update(
        {
            "meta": tmp_path / ".curaflow/meta",
            "diffs": tmp_path / ".curaflow/diffs",
            "sources": tmp_path / "data/sources",
            "targets": tmp_path / "data/targets",
        }
    )
    return old


def _restore_app_dirs(old: dict[str, Path]) -> None:
    cli.APP_DIRS.update(old)


def test_fetch_parallel_respects_max_concurrent(tmp_path: Path) -> None:
    """Ensure `_fetch_parallel` never exceeds the configured concurrency limit."""
    old_app_dirs = _override_app_dirs(tmp_path)
    try:
        global _current_running, _max_running_seen
        _current_running = 0
        _max_running_seen = 0

        raw_sources: dict[str, dict[str, Any]] = {
            f"s{i}": {"name": f"s{i}", "plugin": "test_concurrent_source", "params": {}}
            for i in range(5)
        }
        sources = cast(dict[str, SourceSpec], raw_sources)

        changed_any = asyncio.run(cli._fetch_parallel(sources, max_concurrent=2))
        assert changed_any is True
        # At least some parallelism, but never exceed the semaphore limit
        assert 1 <= _max_running_seen <= 2
    finally:
        _restore_app_dirs(old_app_dirs)


def test_fetch_parallel_persists_dynamic_children(tmp_path: Path) -> None:
    """Dynamic children discovered during fetch are written to the meta registry."""
    old_app_dirs = _override_app_dirs(tmp_path)
    try:
        raw_sources: dict[str, dict[str, Any]] = {
            "root": {"name": "root", "plugin": "test_dynamic_source", "params": {}}
        }
        sources = cast(dict[str, SourceSpec], raw_sources)

        changed_any = asyncio.run(cli._fetch_parallel(sources, max_concurrent=4))
        assert changed_any is True

        dyn_path = cli.APP_DIRS["meta"] / "sources_dynamic.json"
        assert dyn_path.exists()
        data = json.loads(dyn_path.read_text(encoding="utf-8"))
        names = {entry["name"] for entry in data}
        assert "child" in names
    finally:
        _restore_app_dirs(old_app_dirs)
