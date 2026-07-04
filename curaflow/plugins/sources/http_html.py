from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx
import yaml

from ...fetcher import SRC_DIR, FetchMeta, conditional_get
from ...html_source_common import _build_fanout_children
from ...html_utils import make_soup, slugify
from ...plugin_registry import source_plugin
from ...utils import add_extraction_indices, ensure_dir, sha256_obj, write_text_atomic


@source_plugin("http_html")
async def fetch(
    name: str, params: dict[str, Any]
) -> tuple[bool, dict[str, Any] | None, list[dict[str, Any]]]:
    """Fetch HTML, extract items via CSS, normalize to YAML, and optionally fan out child sources.
    Params:
      url: str
      headers: dict (optional)
      extract:  # list of extraction specs
        - name: "tenant_links"
          css: ".tenant-card a"
          attr: href        # one of: href, src, text
          base: null        # optional override for URL resolution
      fanout:   # list of fanout specs
        - from: "tenant_links"
          plugin: "http_html"          # child plugin (http_html/http_bytes/http_json)
          name_template: "tenant:{slug}"
          url_field: "absolute_url"    # which field from extracted record to use as URL
          params:
            url: "{absolute_url}"      # template format with record fields
            extract: []                # params for the child plugin
    """
    url = params["url"]
    headers = params.get("headers") or {}
    extract_specs = params.get("extract", [])
    fanout_specs = params.get("fanout", [])
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
        return (False, prev, _build_fanout_children(name, prev, fanout_specs))

    resp.raise_for_status()
    html = resp.text
    soup = make_soup(html)

    def _format_nested(value: Any, record: dict[str, Any]) -> Any:
        """Recursively format strings in nested params dicts/lists with record fields.

        This mirrors the shallow string ``.format`` used for fanout params, but
        extends it to nested structures so templates can appear inside, e.g.,
        extraction specs.
        """

        if isinstance(value, str):
            try:
                return value.format(**record)
            except KeyError:
                return value
        if isinstance(value, dict):
            return {k: _format_nested(v, record) for k, v in value.items()}
        if isinstance(value, list):
            return [_format_nested(v, record) for v in value]
        return value

    normalized: dict[str, Any] = {"url": url, "extractions": {}}
    for es in extract_specs:
        ename = es["name"]
        css = es["css"]
        attr = es.get("attr", "text")
        base = es.get("base") or url
        inject_spec = es.get("inject") or {}
        items: list[dict[str, Any]] = []
        for el in soup.select(css):
            rec: dict[str, Any] = {}
            if attr == "text":
                value = el.get_text(strip=True)
                rec["text"] = value
            else:
                raw_val = el.get(attr)
                if isinstance(raw_val, list):  # BeautifulSoup attr may be list
                    value = " ".join(str(v) for v in raw_val)
                else:
                    value = str(raw_val) if raw_val is not None else ""
                rec[attr] = value
            if attr in ("href", "src") and value:
                rec["absolute_url"] = urljoin(base, value)
            # slug heuristic
            if rec.get("text"):
                rec["slug"] = slugify(rec["text"])
            elif "absolute_url" in rec:
                rec["slug"] = slugify(rec["absolute_url"].rstrip("/").split("/")[-1])
            else:
                rec["slug"] = slugify(value or "item")

            # Optional field injection: copy or derive extra fields per record.
            # ``inject`` is a mapping of field name -> value/template. Templates
            # are formatted with the record itself (e.g. "{slug}"). Values that
            # were already formatted upstream (e.g. via parent fanout params)
            # are passed through unchanged.
            if inject_spec:
                for k, v in inject_spec.items():
                    if isinstance(v, str):
                        try:
                            rec[k] = v.format(**rec)
                        except KeyError:
                            rec[k] = v
                    else:
                        rec[k] = v

            items.append(rec)
        normalized["extractions"][ename] = items

    # Attach 1-based positional indices within each extraction group so that
    # callers can recover original source order even when re-indexing by slug
    # or other keys.
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
        return (False, prev, _build_fanout_children(name, prev, fanout_specs))

    write_text_atomic(
        SRC_DIR / f"{name}.yaml", yaml.safe_dump(normalized, sort_keys=True, allow_unicode=True)
    )
    new_meta = FetchMeta(
        name=name,
        url=url,
        etag=resp.headers.get("ETag"),
        last_modified=resp.headers.get("Last-Modified"),
        digest=digest,
    )
    new_meta.save()

    return (True, normalized, _build_fanout_children(name, normalized, fanout_specs))
