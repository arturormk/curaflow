from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx
import yaml

from ...fetcher import SRC_DIR, FetchMeta, conditional_get
from ...html_utils import make_soup, slugify
from ...utils import ensure_dir, sha256_obj, write_text_atomic


async def fetch(
    name: str, params: dict[str, Any]
) -> tuple[bool, dict[str, Any], list[dict[str, Any]]]:
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

    ensure_dir(SRC_DIR)
    meta = FetchMeta.load(name)
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
        return (False, prev, [])

    resp.raise_for_status()
    html = resp.text
    soup = make_soup(html)

    normalized: dict[str, Any] = {"url": url, "extractions": {}}
    for es in extract_specs:
        ename = es["name"]
        css = es["css"]
        attr = es.get("attr", "text")
        base = es.get("base") or url
        items: list[dict[str, Any]] = []
        for el in soup.select(css):
            rec: dict[str, Any] = {}
            if attr == "text":
                value = el.get_text(strip=True)
                rec["text"] = value
            else:
                value = el.get(attr) or ""
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
            items.append(rec)
        normalized["extractions"][ename] = items

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
        return (False, prev, [])

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

    # Build children
    children: list[dict[str, Any]] = []
    ex = normalized["extractions"]
    for fs in fanout_specs:
        src = fs["from"]
        child_plugin = fs["plugin"]
        name_t = fs.get("name_template", f"{name}:{src}:{{slug}}")
        url_field = fs.get("url_field", "absolute_url")
        base_params = fs.get("params", {})
        for idx, item in enumerate(ex.get(src, [])):
            if url_field not in item:
                continue
            child_name = name_t.format(
                slug=item.get("slug", f"{idx}"),
                index=idx,
                absolute_url=item.get("absolute_url", ""),
            )
            child_params = dict(base_params)
            for k, v in list(child_params.items()):
                if isinstance(v, str):
                    try:
                        child_params[k] = v.format(**item)
                    except KeyError:
                        pass
            if "url" not in child_params:
                child_params["url"] = item[url_field]
            children.append({"name": child_name, "plugin": child_plugin, "params": child_params})

    return (True, normalized, children)
