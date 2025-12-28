from __future__ import annotations

from typing import Any, cast

from ...fetcher import fetch_http_json
from ...plugin_registry import source_plugin


@source_plugin("http_json")
async def fetch(
    name: str, params: dict[str, object]
) -> tuple[bool, dict[str, Any] | None, list[dict[str, Any]]]:
    """Source plugin wrapper around fetch_http_json.

    Params:
      url: str
      headers: dict[str, str] (optional)
      force: bool (optional; overrides HTTP cache metadata)
    """

    url = cast(str, params["url"])
    headers = cast("dict[str, str] | None", params.get("headers"))
    force = bool(params.get("force", False))

    changed, data = await fetch_http_json(name, url, headers=headers, force=force)
    return changed, data, []
