from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import yaml

from ...cli import APP_DIRS
from ...plugin_registry import target_plugin
from ...qml_target_common import _walk_path
from ...utils import write_text_atomic


@target_plugin("watch")
def watch_target(name: str, deps: list[str], params: dict[str, object]) -> dict[str, Any]:
    """Generic watch target.

    Summarises selected fields from a YAML source into a compact JSON
    document suitable for change detection.

    Expected params::

        list_key: str              # dotted path to list of records
        fields:                    # mapping output_field -> input_field
          codigo: "codigo"
          slug: "slug"
          logo: "logo"

    The resulting JSON is shaped as::

        {
          "list_key": "...",
          "fields": { ... },
          "items": [
            {"codigo": "...", "slug": "...", "logo": "..."},
            ...
          ]
        }

    ``build()`` will compute structural diffs between successive versions of
    this JSON via :func:`deep_diff`, and callers can also archive snapshots
    for richer, domain-specific analysis.
    """

    if not deps:
        raise ValueError("watch target requires at least one dependency (the source YAML)")

    source_dep = deps[0]
    src_path = APP_DIRS["sources"] / f"{source_dep}.yaml"
    if not src_path.exists():
        raise FileNotFoundError(
            f"Source YAML for dependency '{source_dep}' not found at {src_path}"
        )

    data = yaml.safe_load(src_path.read_text(encoding="utf-8")) or {}

    list_key_param = params.get("list_key", "")
    if not isinstance(list_key_param, str):
        raise ValueError("watch target requires 'list_key' (str)")

    fields_param = params.get("fields")
    if not isinstance(fields_param, Mapping) or not fields_param:
        raise ValueError("watch target requires 'fields' (mapping)")

    # Normalise field mapping to strings
    fields: dict[str, str] = {str(k): str(v) for k, v in fields_param.items()}

    # Resolve the list of records from the source document
    raw_items: Any = _walk_path(data, list_key_param)
    if isinstance(raw_items, list):
        records = [r for r in raw_items if isinstance(r, Mapping)]
    else:
        records = []

    items: list[dict[str, Any]] = []
    for rec in records:
        out: dict[str, Any] = {}
        for out_field, in_field in fields.items():
            if in_field in rec:
                out[out_field] = rec[in_field]
        if out:
            items.append(out)

    summary_path = APP_DIRS["targets"] / f"{name}.json"

    previous = None
    if summary_path.exists():
        try:
            previous = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            previous = None

    current = {
        "list_key": list_key_param,
        "fields": fields,
        "items": items,
    }

    write_text_atomic(summary_path, json.dumps(current, ensure_ascii=False, indent=2))

    return {"previous": previous, "current": current, "output_path": str(summary_path)}
