from __future__ import annotations

import json
from typing import Any

import yaml

from ...cli import APP_DIRS  # reuse directory map
from ...plugin_registry import target_plugin
from ...utils import write_text_atomic

"""Concat JSON/YAML sources into a single JSON object target.

Each dependency is loaded (YAML for sources, JSON for other targets) and stored under
its dependency name as a key in the resulting object.
"""


def _load_dep(dep: str) -> Any:
    p_yaml = APP_DIRS["sources"] / f"{dep}.yaml"
    if p_yaml.exists():
        return yaml.safe_load(p_yaml.read_text(encoding="utf-8"))
    p_json = APP_DIRS["targets"] / f"{dep}.json"
    if p_json.exists():
        return json.loads(p_json.read_text(encoding="utf-8"))
    return None


@target_plugin("concat_json")
def build_concat_json(name: str, deps: list[str], params: dict[str, object]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for d in deps:
        merged[d] = _load_dep(d)
    outp = APP_DIRS["targets"] / f"{name}.json"
    prev = json.loads(outp.read_text(encoding="utf-8")) if outp.exists() else None
    write_text_atomic(outp, json.dumps(merged, ensure_ascii=False, indent=2))
    # params currently unused; placeholder for future transform directives.
    return {"previous": prev, "current": merged, "output_path": str(outp)}


__all__ = ["build_concat_json"]
