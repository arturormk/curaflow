from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import yaml
from bs4 import BeautifulSoup

from .fetcher import SRC_DIR, FetchMeta, conditional_get
from .plugin_registry import source_plugin
from .utils import add_extraction_indices, ensure_dir, sha256_obj, write_text_atomic

Extractor = Callable[[BeautifulSoup, str, dict[str, Any]], dict[str, Any]]


async def _run_html_source(
    name: str,
    params: dict[str, Any],
    extractor: Extractor,
) -> tuple[bool, dict[str, Any] | None, list[dict[str, Any]]]:
    """Shared helper for HTML-based source plugins.

    Handles HTTP fetch with conditional GET, digest comparison, YAML
    normalization, and index annotation. The ``extractor`` callback is
    responsible for mapping ``(soup, url, params)`` to a normalized
    ``dict`` that includes an ``extractions`` mapping.

    In addition, this helper supports optional *manifest-style fanout*
    similar to ``http_html`` when the caller provides a ``fanout`` list
    in ``params``. Fanout is evaluated against the extractor's
    ``normalized['extractions']`` mapping.
    """

    url = params["url"]
    headers = params.get("headers") or {}
    force = bool(params.get("force", False))

    ensure_dir(SRC_DIR)
    meta = None if force else FetchMeta.load(name)

    async with httpx.AsyncClient(headers=headers) as client:
        resp = await conditional_get(
            client, url, meta.etag if meta else None, meta.last_modified if meta else None
        )

    if resp.status_code == 304 and meta:
        prev = (
            yaml.safe_load((SRC_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
            if (SRC_DIR / f"{name}.yaml").exists()
            else None
        )
        return False, prev, []

    resp.raise_for_status()
    html = resp.text

    # Lazy import to avoid tying helper to a specific HTML parser
    from .html_utils import make_soup

    soup = make_soup(html)

    # Expose the concrete source instance name to custom extractors via
    # params so they can, for example, derive extraction group names
    # from it (without changing the extractor call signature).
    params = dict(params)
    params.setdefault("_source_name", name)

    normalized: dict[str, Any] = extractor(soup, url, params)
    # Ensure minimal structure
    normalized.setdefault("url", url)
    normalized.setdefault("extractions", {})

    add_extraction_indices(normalized)

    digest = sha256_obj(normalized)
    if meta and meta.digest == digest:
        new_meta = FetchMeta(
            name=name,
            url=url,
            etag=resp.headers.get("ETag"),
            last_modified=resp.headers.get("Last-Modified"),
            digest=digest,
        )
        new_meta.save()
        prev = (
            yaml.safe_load((SRC_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
            if (SRC_DIR / f"{name}.yaml").exists()
            else None
        )
        return False, prev, []

    write_text_atomic(
        SRC_DIR / f"{name}.yaml",
        yaml.safe_dump(normalized, sort_keys=True, allow_unicode=True),
    )
    new_meta = FetchMeta(
        name=name,
        url=url,
        etag=resp.headers.get("ETag"),
        last_modified=resp.headers.get("Last-Modified"),
        digest=digest,
    )
    new_meta.save()

    # Optional generic fanout, mirroring ``http_html`` semantics.
    children: list[dict[str, Any]] = []
    fanout_specs = params.get("fanout", [])
    extractions = normalized.get("extractions") or {}
    if isinstance(fanout_specs, list) and isinstance(extractions, dict):
        for fs in fanout_specs:
            if not isinstance(fs, dict):
                continue
            src = fs.get("from")
            child_plugin = fs.get("plugin")
            if not src or not child_plugin:
                continue
            name_t = fs.get("name_template", f"{name}:{src}:{{slug}}")
            url_field = fs.get("url_field", "absolute_url")
            base_params = fs.get("params", {})
            items = extractions.get(src) or []
            if not isinstance(items, list):
                continue

            for idx, item in enumerate(items):
                if not isinstance(item, dict) or url_field not in item:
                    continue

                fmt_ctx: dict[str, Any] = dict(item)
                fmt_ctx.setdefault("slug", item.get("slug", f"{idx}"))
                fmt_ctx.setdefault("index", idx)
                fmt_ctx.setdefault("absolute_url", item.get(url_field, ""))

                class _SafeDict(dict[str, Any]):
                    def __missing__(self, key: str) -> str:
                        return "{" + key + "}"

                child_name = name_t.format_map(_SafeDict(fmt_ctx))
                child_params = dict(base_params)
                for k, v in list(child_params.items()):
                    if isinstance(v, str):
                        try:
                            child_params[k] = v.format(**item)
                        except KeyError:
                            # Leave value as-is if formatting fails due to
                            # missing keys; this mirrors ``http_html``.
                            pass
                if "url" not in child_params:
                    child_params["url"] = item[url_field]
                children.append(
                    {"name": child_name, "plugin": child_plugin, "params": child_params}
                )

    return True, normalized, children


def make_html_plugin(plugin_name: str, extractor: Extractor) -> None:
    """Register a source plugin backed by ``_run_html_source``.

    Example::

        from curaflow.html_source_common import make_html_plugin
        from curaflow.html_utils import slugify

        def my_extractor(soup, url, params):
            ... build extractions ...
            return {"url": url, "extractions": {"items": items}}

        make_html_plugin("my_html_plugin", my_extractor)
    """

    @source_plugin(plugin_name)
    async def _impl(
        name: str, params: dict[str, Any]
    ) -> tuple[bool, dict[str, Any] | None, list[dict[str, Any]]]:
        return await _run_html_source(name, params, extractor)


__all__ = ["Extractor", "_run_html_source", "make_html_plugin"]
