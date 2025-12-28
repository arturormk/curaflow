from __future__ import annotations

from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import httpx
import yaml

from ...fetcher import SRC_DIR, FetchMeta, conditional_get
from ...html_utils import slugify
from ...plugin_registry import source_plugin
from ...utils import add_extraction_indices, ensure_dir, sha256_obj, write_text_atomic


def _add_value(rec: dict[str, Any], key: str, value: Any) -> None:
    """Helper to accumulate values; turn duplicates into lists.

    XML feeds often repeat tags (e.g. multiple <imagen> entries). When the same
    key is seen more than once, this turns the field into a list and appends the
    additional values.
    """

    if key in rec:
        existing = rec[key]
        if isinstance(existing, list):
            existing.append(value)
        else:
            rec[key] = [existing, value]
    else:
        rec[key] = value


def _first_str(value: Any) -> str | None:
    """Return a representative string for a possibly-list value."""

    if isinstance(value, list):
        return str(value[0]) if value else None
    if value is None:
        return None
    return str(value)


@source_plugin("http_xml")
async def fetch(
    name: str, params: dict[str, Any]
) -> tuple[bool, dict[str, Any] | None, list[dict[str, Any]]]:
    """Fetch XML, extract items via ElementTree ``findall`` paths, normalize to YAML, and optionally fan out child sources.

    Params example::

      url: str
      headers: dict (optional)
      extract:  # list of extraction specs
        - name: "posts"
          path: ".//item"   # ElementTree.findall path from the document root
          base: null          # optional override for URL resolution
      fanout:   # list of fanout specs (same contract as http_html)
        - from: "posts"
          plugin: "http_html"          # or http_bytes/http_json/etc.
          name_template: "post:{slug}"
          url_field: "absolute_url"    # which field from extracted record to use as URL
          params:
            url: "{absolute_url}"      # template format with record fields

    Extraction behaviour
    --------------------
    - For each ``extract`` entry, ``path`` is passed to ``root.findall(path)``.
    - Each matched element becomes one record (dict).
    - Direct child elements of the record element are flattened into fields
      using their tag names; repeated tags turn into lists of strings.
    - Element attributes are exposed as fields named "@attr".
    - If a field named "URL"/"url"/"link"/"href" is present, an
      ``absolute_url`` field is added by resolving it against ``base`` (or
      ``url`` if ``base`` is not provided).
    - A ``slug`` field is synthesized, preferring ``post_title``/``title``/``ID``/``id``
      or the absolute URL, and falling back to an index-based slug.
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
        return (False, prev, [])

    resp.raise_for_status()
    content = resp.content

    # Parse XML document
    root = ET.fromstring(content)

    normalized: dict[str, Any] = {"url": url, "root_tag": root.tag, "extractions": {}}
    for es in extract_specs:
        ename = es["name"]
        path = es["path"]
        base = es.get("base") or url

        records: list[dict[str, Any]] = []
        for idx, el in enumerate(root.findall(path)):
            rec: dict[str, Any] = {}

            # Flatten child elements into simple fields
            for child in el:
                text = (child.text or "").strip()
                if text:
                    _add_value(rec, child.tag, text)

            # Include attributes as @attr keys
            for attr_name, attr_val in el.attrib.items():
                _add_value(rec, f"@{attr_name}", attr_val)

            # URL normalization: create absolute_url from a likely URL field
            url_key = None
            for candidate in ("URL", "url", "link", "href"):
                if candidate in rec:
                    url_key = candidate
                    break
            if url_key is not None:
                val = _first_str(rec[url_key]) or ""
                if val:
                    rec["absolute_url"] = urljoin(base, val)

            # Slug heuristics
            slug_source = None
            for candidate in ("ID", "id", "post_title", "title", "absolute_url"):
                if candidate in rec:
                    slug_source = _first_str(rec[candidate])
                    if slug_source:
                        break
            if not slug_source:
                slug_source = f"{ename}-{idx}"

            # If slug source is a URL, trim to the last path segment
            if slug_source and slug_source.startswith("http") and "/" in slug_source:
                slug_source = slug_source.rstrip("/").split("/")[-1]

            rec["slug"] = slugify(slug_source or f"{ename}-{idx}")
            records.append(rec)

        normalized["extractions"][ename] = records

    # Ensure all extraction records carry a 1-based ``_index`` field so
    # consumers can preserve source order even when re-indexing by slug.
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
        return (False, prev, [])

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

    # Build children (same contract as http_html)
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
            # Allow name_template to reference any extracted field (e.g. {ID})
            # while still providing slug/index/absolute_url defaults and avoiding
            # KeyError for missing keys.
            fmt_ctx: dict[str, Any] = dict(item)
            fmt_ctx.setdefault("slug", item.get("slug", f"{idx}"))
            fmt_ctx.setdefault("index", idx)
            fmt_ctx.setdefault("absolute_url", item.get("absolute_url", ""))

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
                        # Leave template as-is if field is missing
                        pass
            if "url" not in child_params:
                child_params["url"] = item[url_field]
            children.append({"name": child_name, "plugin": child_plugin, "params": child_params})

    return (True, normalized, children)


__all__ = ["fetch"]
