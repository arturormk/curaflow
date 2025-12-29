from __future__ import annotations

from copy import deepcopy
from typing import Any

from ...plugin_registry import source_plugin


def _substitute_placeholders(obj: Any, mapping: dict[str, str]) -> Any:
    """Recursively substitute placeholders in all strings of a structure.

    Placeholders are literal substrings; we do a simple replace for each
    mapping key. This keeps the logic generic and avoids coupling to a
    specific template syntax beyond "find this token and replace it".
    """

    if isinstance(obj, str):
        result = obj
        for placeholder, value in mapping.items():
            if placeholder:
                result = result.replace(placeholder, value)
        return result

    if isinstance(obj, list):
        return [_substitute_placeholders(item, mapping) for item in obj]

    if isinstance(obj, dict):
        return {k: _substitute_placeholders(v, mapping) for k, v in obj.items()}

    # Leave other types (int, bool, None, etc.) untouched
    return obj


@source_plugin("multiplex")
async def multiplex(
    name: str, params: dict[str, Any]
) -> tuple[bool, dict[str, Any] | None, list[dict[str, Any]]]:
    """Meta-source that expands parametrized source templates into children.

    Expected params schema (YAML):

        params:
          instances:
            es:
              "$prefix$": "es"
              "$url_banners$": "https://example.com/es.xml"
            en:
              "$prefix$": "en"
              "$url_banners$": "https://example.com/en.xml"
          sources:
            - name: "$prefix$_banners"
              plugin: http_xml
              params:
                url: "$url_banners$"
                # ...

    For each instance, every placeholder key in the mapping is replaced by
    its value across the entire ``sources`` subtree (names, params, etc.),
    yielding a concrete child source spec. The plugin itself produces no
    data; it only returns children.
    """

    instances = params.get("instances") or {}
    templates = params.get("sources") or []

    if not isinstance(instances, dict):
        raise TypeError(f"multiplex plugin '{name}' expected 'instances' to be a mapping")
    if not isinstance(templates, list):
        raise TypeError(f"multiplex plugin '{name}' expected 'sources' to be a list")

    children: list[dict[str, Any]] = []

    for instance_key, placeholder_map in instances.items():
        if not isinstance(placeholder_map, dict):
            raise TypeError(
                f"multiplex plugin '{name}' expected mapping for instance '{instance_key}', "
                f"got {type(placeholder_map).__name__}"
            )

        for tmpl in templates:
            if not isinstance(tmpl, dict):
                continue  # robust in face of bad input

            concrete = deepcopy(tmpl)
            concrete = _substitute_placeholders(concrete, placeholder_map)

            # Unconditionally prefix the instance key to the logical
            # template name so manifests can stay generic (e.g.
            # ``name: banners`` -> ``es:banners``). All other
            # identifiers (extraction names, fanout "from" keys, etc.)
            # remain *local* and are not rewritten.
            base_name = str(concrete.get("name", "")).strip() or name
            concrete["name"] = f"{instance_key}:{base_name}"

            # Attach plugin + params as normal source spec; if plugin is
            # missing in the template, we leave it as-is and let the core
            # machinery validate/complain.
            plugin = concrete.get("plugin")
            if not isinstance(plugin, str) or not plugin:
                raise TypeError(
                    f"multiplex plugin '{name}' produced child without valid 'plugin' field "
                    f"for instance '{instance_key}'"
                )

            children.append(
                {
                    "name": concrete["name"],
                    "plugin": plugin,
                    "params": concrete.get("params", {}),
                }
            )

    # We treat the multiplexor as a pure configuration expander. It
    # returns no data of its own, only children; we also don't persist any
    # YAML under data/sources/ for it. Reporting it as unchanged keeps it
    # from influencing "some sources changed" summaries while still
    # letting its children into the dynamic source registry.
    return False, None, children
