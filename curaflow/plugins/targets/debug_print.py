from __future__ import annotations

import json
from typing import Any

import yaml

from ...cli import APP_DIRS  # reuse directory map
from ...plugin_registry import target_plugin
from ...utils import write_text_atomic

"""Debug target plugin for inspecting dependencies.

This plugin loads each dependency (YAML for sources, JSON for targets),
prints their contents to stdout, and writes a JSON snapshot of the merged
view to the target file so that it participates in normal dependency
tracking and diffs.
"""


def _load_dep(dep: str) -> Any:
    p_yaml = APP_DIRS["sources"] / f"{dep}.yaml"
    if p_yaml.exists():
        return yaml.safe_load(p_yaml.read_text(encoding="utf-8"))
    p_json = APP_DIRS["targets"] / f"{dep}.json"
    if p_json.exists():
        return json.loads(p_json.read_text(encoding="utf-8"))
    return None


@target_plugin("debug_print")
def build_debug_print(name: str, deps: list[str], params: dict[str, object]) -> dict[str, Any]:
    from rich import print as rprint

    merged: dict[str, Any] = {}
    for d in deps:
        obj = _load_dep(d)
        merged[d] = obj
        rprint(f"[bold cyan]DEBUG target {name}[/bold cyan] dep=[yellow]{d}[/yellow]")
        if isinstance(obj, dict) and "extractions" in obj:
            rprint("[cyan]extractions:[/cyan]")
            rprint(obj["extractions"])
        else:
            rprint(obj)

    outp = APP_DIRS["targets"] / f"{name}.json"
    prev = json.loads(outp.read_text(encoding="utf-8")) if outp.exists() else None
    write_text_atomic(outp, json.dumps(merged, ensure_ascii=False, indent=2))

    return {"previous": prev, "current": merged, "output_path": str(outp)}


__all__ = ["build_debug_print"]
