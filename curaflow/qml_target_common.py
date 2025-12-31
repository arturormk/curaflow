from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .cli import APP_DIRS
from .plugin_registry import target_plugin
from .utils import write_text_atomic

RenderFn = Callable[
    [str, Iterable[Mapping[str, Any]], Mapping[str, Any]], tuple[str, list[dict[str, Any]]]
]


@dataclass(frozen=True)
class ElementField:
    """Specification for extracting a single field into an element dict.

    ``name`` is the key stored in the final ``elements`` list (e.g. ``"idx"`` or
    ``"title"``). ``cfg_key`` names the configuration entry that holds the
    source field name (typically something like ``"title_field"``). If that
    entry is missing, ``default_source_key`` is used. ``value_type`` controls
    basic coercion (``"int"`` for index-like fields, ``"str"`` for strings,
    ``"raw"`` to pass the original value through unchanged).
    """

    name: str
    cfg_key: str
    default_source_key: str
    value_type: str = "str"  # "int", "str", or "raw"
    default_value: Any = ""


def _load_yaml_source(dep: str) -> Any:
    """Load a YAML source produced by a source plugin.

    This mirrors the ad-hoc helpers used in the QML target plugins but is
    centralized here so that multiple targets can share it.
    """

    p = APP_DIRS["sources"] / f"{dep}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"Source YAML for dependency '{dep}' not found at {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _walk_path(obj: Any, path: str) -> Any:
    """Resolve a dotted path like ``"extractions.news_items"``.

    If the path cannot be fully resolved, an empty list is returned so callers
    can treat it as "no items".
    """

    cur: Any = obj
    if not path:
        return cur
    for part in path.split("."):
        if isinstance(cur, Mapping) and part in cur:
            cur = cur[part]
        else:
            return []
    return cur


def qml_escape(value: Any) -> str:
    """Escape a value for safe inclusion in QML string literals.

    Lists of strings are converted to a ``<p>``-wrapped HTML block, which
    matches the behaviour in the existing playground targets.
    """

    if isinstance(value, list):
        value = "<p>" + "</p><p>".join(str(v) for v in value) + "</p>"
    text = str(value)
    return text.replace("\\", "\\\\").replace('"', '\\"')


def ddmmyyyy_to_iso(ddmmyyyy: str) -> str:
    """Convert a ``dd-mm-yyyy`` date string to ISO ``yyyy-mm-dd``.

    Returns an empty string when given a false-y value. This mirrors the
    behaviour in the existing news/promo targets.
    """

    if not ddmmyyyy:
        return ""
    try:
        dd, mm, yyyy = ddmmyyyy.split("-")
    except ValueError:
        return ""
    return "-".join([yyyy, mm, dd])


def build_elements_from_fields(
    items: Iterable[Mapping[str, Any]],
    cfg: Mapping[str, Any],
    fields: Iterable[ElementField],
) -> list[dict[str, Any]]:
    """Extract a list of element dicts based on ``ElementField`` specs.

    This helper is intentionally conservative: it only normalises scalar types
    and leaves any list/structured values untouched so that QML construction
    logic in individual plugins remains explicit.
    """

    # Resolve source keys from configuration once.
    resolved: list[tuple[ElementField, str]] = []
    for f in fields:
        source_key = str(cfg.get(f.cfg_key, f.default_source_key))
        resolved.append((f, source_key))

    elements: list[dict[str, Any]] = []
    for item in items:
        elem: dict[str, Any] = {}
        for f, source_key in resolved:
            raw = item.get(source_key, f.default_value)
            if f.value_type == "int":
                try:
                    elem[f.name] = int(raw) if raw is not None else int(f.default_value or 0)
                except (TypeError, ValueError):
                    elem[f.name] = int(f.default_value or 0)
            elif f.value_type == "raw":
                elem[f.name] = raw
            else:  # "str" (default)
                if raw is None:
                    elem[f.name] = str(f.default_value)
                else:
                    elem[f.name] = str(raw)
        elements.append(elem)

    return elements


def _normalise_params(
    defaults: Mapping[str, Any],
    params: Mapping[str, Any],
    field_specs: Iterable[ElementField] | None = None,
) -> dict[str, Any]:
    """Merge ``params`` over ``defaults`` and normalise common keys.

    - ``base_dir`` becomes a concrete Path under APP_DIRS["targets"].
    - ``qml_version``, ``qml_filename`` and ``list_key`` are coerced to ``str``.
    """

    cfg: dict[str, Any] = dict(defaults)

    # For any ElementField specs, ensure the corresponding "*_field" config
    # entries have sensible defaults derived from ``default_source_key``. This
    # lets callers avoid repeating the same information in ``default_params``.
    if field_specs is not None:
        for f in field_specs:
            cfg.setdefault(f.cfg_key, f.default_source_key)

    cfg.update(params)

    base_dir_raw = cfg.get("base_dir", "")
    if isinstance(base_dir_raw, Path):
        base_dir = base_dir_raw
    else:
        base_dir = APP_DIRS["targets"] / str(base_dir_raw or "")
    cfg["base_dir"] = base_dir

    cfg.setdefault("qml_version", "2.2")
    cfg["qml_version"] = str(cfg["qml_version"])

    cfg.setdefault("qml_filename", "ListModel.qml")
    cfg["qml_filename"] = str(cfg["qml_filename"])

    cfg.setdefault("list_key", "")
    cfg["list_key"] = str(cfg["list_key"])

    return cfg


def _run_qml_target(
    *,
    plugin_name: str,
    target_name: str,
    deps: list[str],
    params: Mapping[str, Any],
    default_params: Mapping[str, Any],
    field_specs: Iterable[ElementField] | None,
    render_qml: RenderFn,
) -> dict[str, Any]:
    """Shared implementation for simple QML list-model targets.

    The caller provides ``default_params`` (including the various
    ``"xxx_field"`` entries it cares about) and a ``render_qml`` callback
    that is responsible for turning ``(version, items, cfg)`` into both the
    QML text and an ``elements`` list suitable for JSON summarisation.
    """

    if not deps:
        raise ValueError(f"{plugin_name} target requires at least one dependency (the source YAML)")

    source_dep = deps[0]
    source_data = _load_yaml_source(source_dep)

    cfg = _normalise_params(default_params, params, field_specs)

    items_raw = _walk_path(source_data, cfg["list_key"])
    if not isinstance(items_raw, list):
        items: list[Mapping[str, Any]] = []
    else:
        # Only keep mapping-like entries; this matches the previous behaviour
        # inside the individual ``_iter_elements`` helpers.
        items = [i for i in items_raw if isinstance(i, Mapping)]

    qml_text, elements = render_qml(cfg["qml_version"], items, cfg)

    base_dir: Path = cfg["base_dir"]
    base_dir.mkdir(parents=True, exist_ok=True)
    qml_path = base_dir / cfg["qml_filename"]
    write_text_atomic(qml_path, qml_text)

    summary_path = APP_DIRS["targets"] / f"{target_name}.json"
    previous = None
    if summary_path.exists():
        try:
            previous = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            previous = None

    current = {
        "qml_file": str(qml_path.relative_to(APP_DIRS["targets"])),
        "qml_version": cfg["qml_version"],
        "count": len(elements),
        "items": elements,
    }

    write_text_atomic(summary_path, json.dumps(current, ensure_ascii=False, indent=2))

    return {"previous": previous, "current": current, "output_path": str(summary_path)}


def make_qml_target_plugin(
    plugin_name: str,
    *,
    default_params: Mapping[str, Any],
    render_qml: RenderFn,
    field_specs: Iterable[ElementField] | None = None,
) -> None:
    """Register a target plugin backed by ``_run_qml_target``.

    Example::

        from curaflow.qml_target_common import make_qml_target_plugin, qml_escape

        def _render_qml(version, items, cfg):
            ... build QML text and elements list ...
            return qml_text, elements

        make_qml_target_plugin(
            "qml_example",
            default_params={
                "base_dir": "es/example",
                "qml_filename": "ListModelExample.qml",
                "list_key": "extractions.example_items",
                "index_field": "_index",
                "key_field": "slug",
            },
            render_qml=_render_qml,
        )
    """

    @target_plugin(plugin_name)
    def _impl(name: str, deps: list[str], params: dict[str, Any]) -> dict[str, Any]:
        return _run_qml_target(
            plugin_name=plugin_name,
            target_name=name,
            deps=deps,
            params=params,
            default_params=default_params,
            field_specs=field_specs,
            render_qml=render_qml,
        )


__all__ = [
    "ElementField",
    "RenderFn",
    "build_elements_from_fields",
    "ddmmyyyy_to_iso",
    "make_qml_target_plugin",
    "qml_escape",
]
