# Curaflow

*Incremental, parallel fetch → normalize → build for web-curated datasets.*

**New:** hierarchical fanout: scrape an index page → fan out to tenant pages → fan out to images (binary).

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .

curaflow plan -m example/manifest.yaml
curaflow fetch -m example/manifest.yaml  # use --max-concurrent to tune parallelism
curaflow build -m example/manifest.yaml
curaflow status -m example/manifest.yaml
curaflow diff targets:tenants_bundle
curaflow table "es:tiendas" --columns codigo,slug,marca --sort +codigo
```

## Highlights

- **Sources (YAML):** `http_json`, `http_html` (CSS selectors), `http_xml` (XML via ElementTree paths), `http_bytes` (binary, metadata YAML + file in `data/raw/`).
- **Hierarchical fanout:** HTML extractions can spawn child sources (pages → images).
- **Conditional GET:** ETag / Last-Modified + content digests to avoid redundant work.
- **Targets:** Declare artifacts with deps; rebuild only when deps are newer.
- **Diffs:** Structural diffs for targets stored in `.curaflow/diffs/`.
- **Dynamic registry:** Discovered sources are persisted in `.curaflow/meta/sources_dynamic.json`.
 - **Inspection tooling:** `curaflow table` prints YAML sources as pretty tables, with natural ("1, 2, 10") sorting on selected columns.

See `example/manifest.yaml` and comments in `curaflow/plugins/sources/http_html.py`.


## Inspecting sources with `table`

For day-to-day maintenance and debugging of manifests, Curaflow exposes a small
utility command that renders a YAML source as a terminal table:

```bash
curaflow table SOURCE \
	--list-key extractions.items \
	--columns codigo,slug,marca \
	--sort +codigo
```

- `SOURCE` is the source name; it reads `data/sources/SOURCE.yaml` under the
	current `APP_DIRS["sources"]`.
- `--list-key` is an optional dotted path to the list or mapping of records
	inside the YAML (e.g. `extractions.tenant_links`). If omitted and the YAML is
	itself a list, that list is used.
- `--columns` accepts either repeated flags or comma-separated values and
	selects which keys to show as columns. If omitted, all keys found in the
	records are shown.
- `--sort` accepts `+field` / `-field` expressions (multiple or
	comma-separated). Sorting is *natural*: digit segments are compared
	numerically, so values like `1`, `2`, `10` appear in the expected order.


## How names map to files

Curaflow relies heavily on `name` fields in the manifest. Roughly:

	- If the source is binary (e.g. `http_bytes`), the downloaded file itself is stored under `data/raw/<name>.<ext>` and the YAML in `data/sources/<name>.yaml` contains metadata (URL, content type, digest, path to the raw file).
	- Dynamically discovered sources (via fanout or meta-plugins such as `multiplex`) behave exactly the same: once created, they are just sources with a `name`.
- **Source `name`** → normalized YAML at `data/sources/<name>.yaml`.
	- If the source is binary (e.g. `http_bytes`), the downloaded file itself is stored under `data/raw/<name>.<ext>` and the YAML in `data/sources/<name>.yaml` contains metadata (URL, content type, digest, path to the raw file). For fanout children, this `<name>` is whatever was generated from the fanout `name_template`.
	- Dynamically discovered sources (via fanout or meta-plugins such as `multiplex`) behave exactly the same: once created, they are just sources with a `name`.
- **Target `name`** → built artifact at `data/targets/<name>.json` and its change history under `.curaflow/diffs/`.

Within a single source's YAML, **extraction names** and **fanout `from` keys** are always *local*:

- In the manifest: `extract: - name: items`.
- In the YAML: `extractions.items`.
- In fanout: `fanout: - from: items` (points at that extraction group, not at another source).

Meta-plugins like `multiplex` can rewrite the *source* `name` (for example, turning `banners` into `es:banners` for an `es` instance) but do not touch these local extraction keys; this keeps manifests readable while still giving each concrete source a unique global name.
## Writing a Plugin

Plugins are lightweight callables registered via decorators:

```python
from curaflow.plugin_registry import source_plugin, target_plugin

@source_plugin("my_source")
async def fetch_my_source(name: str, params: dict[str, object]):
		"""Return (changed, data, children)."""
		data = {"hello": "world"}
		return True, data, []

@target_plugin("my_target")
def build_my_target(name: str, deps: list[str], params: dict[str, object]):
		return {"previous": None, "current": {"deps": deps}, "output_path": "-"}
```

Add them to your manifest:

```yaml
sources:
	- name: demo
		plugin: my_source
		params: {}
targets:
	- name: all
		plugin: my_target
		deps: [demo]
```

Ship a module that imports the decorators (import side-effect registers). No auto-discovery yet—ensure your plugin module is imported before use (e.g. `import my_package.curaflow_plugins`). For project-local plugins that live outside this repo, you can also point Curaflow at a directory containing `sources/` and `targets/` subfolders:

```bash
curaflow --plugins path/to/plugins fetch -m manifest.yaml
```

Every `*.py` file under `sources/`/`targets/` is imported and can register plugins via the usual decorators.

Source plugin return tuple:
1. `changed` (bool) – whether output YAML updated.
2. `data` – structured object (serialized to YAML by your function if you write the file yourself; current built-ins write directly).
3. `children` – list of dynamically spawned source specs `{name, plugin, params}`.

Target plugin return dict should include at minimum:
* `previous` – prior object (if exists)
* `current` – new artifact object
* `output_path` – written file path

### HTML helper for custom scrapers

For HTML pages that need bespoke BeautifulSoup logic, Curaflow exposes a small helper in `curaflow.html_source_common` that takes care of HTTP fetching, YAML persistence, index annotation, and optional manifest-style fanout. You only provide an extractor that maps `(soup, url, params)` to a normalized structure:

```python
from typing import Any
from bs4 import BeautifulSoup

from curaflow.html_source_common import make_html_plugin
from curaflow.html_utils import slugify


def my_extractor(soup: BeautifulSoup, url: str, params: dict[str, Any]) -> dict[str, Any]:
	items: list[dict[str, Any]] = []
	for el in soup.select(".item"):
		title = el.get_text(strip=True)
		items.append({"title": title, "slug": slugify(title)})
	return {"url": url, "extractions": {"items": items}}


make_html_plugin("my_html_plugin", my_extractor)
```

You can then use `params.fanout` in the manifest to spawn child sources from `extractions.items`, following the same schema as `http_html`.

See ADR-0012 for rationale.

### QML helper for list-model targets

For simple QML `ListModel` targets backed by YAML sources, Curaflow exposes a
small helper in `curaflow.qml_target_common` that centralises YAML loading,
QML/JSON writing, and some common utilities. You only provide:

- a mapping of default parameters (including any `xxx_field` keys you care
  about), and
- a `_render_qml(version, items, cfg)` function that returns the QML text and
  the list of elements to store in the JSON summary.

Example::

	from collections.abc import Iterable, Mapping
	from typing import Any

	from curaflow.qml_target_common import (
		make_qml_target_plugin,
		qml_escape,
	)


	def _render_qml(
		version: str,
		items: Iterable[Mapping[str, Any]],
		cfg: Mapping[str, Any],
	) -> tuple[str, list[dict[str, Any]]]:
		index_field = str(cfg.get("index_field", "_index"))
		key_field = str(cfg.get("key_field", "slug"))

		elements: list[dict[str, Any]] = []
		for item in items:
			idx = int(item.get(index_field, 0) or 0)
			key = str(item.get(key_field, ""))
			elements.append({"idx": idx, "key": key})

		elements.sort(key=lambda e: e["idx"])

		lines: list[str] = []
		lines.append(f"import QtQuick {version}")
		lines.append("")
		lines.append("ListModel {")
		for el in elements:
			idx = el["idx"]
			key = qml_escape(el["key"])
			lines.append("    ListElement {")
			lines.append(f"        idx: {idx}")
			lines.append(f"        key: \"{key}\"")
			lines.append("    }")
		lines.append("}")
		lines.append("")

		return "\n".join(lines), elements


	make_qml_target_plugin(
		"qml_example",
		default_params={
			"base_dir": "es/example",
			"qml_version": "2.2",
			"qml_filename": "ListModelExample.qml",
			"list_key": "extractions.example_items",
			"index_field": "_index",
			"key_field": "slug",
		},
		render_qml=_render_qml,
	)

The helper will:

- load the first dependency's YAML from `APP_DIRS["sources"]`,
- resolve `list_key` inside that YAML to obtain the list of items,
- call `_render_qml` with the resolved items and merged configuration, and
- write both the QML file and a JSON summary under `APP_DIRS["targets"]`.

Target authors remain in full control of how the QML is constructed while
avoiding repetitive boilerplate for YAML IO and summaries.

### Media conversion target plugin

Curaflow includes a generic `media_convert` target plugin for turning
`http_bytes` metadata into normalized image/video assets.

Typical manifest usage:

```yaml
targets:
	- name: banners_img
		plugin: media_convert
		deps: ["banners"]
		params:
			base_dir: "es/banners"           # under data/targets/
			list_key: "extractions.banners_items"
			id_field: "ID"                   # field in the list used as media id
			image_source: "banner_image:{id}"  # name of corresponding http_bytes sources
			name_template: "{id}"            # optional; base filename without extension
			width: 800                         # target width in pixels
			height: 600                        # target height in pixels
```

At build time, `media_convert`:

- Reads the first dependency YAML and walks `list_key` to obtain a list of items.
- For each item, formats `image_source` to locate a corresponding `http_bytes` YAML.
- Filters to `image/*` or `video/*` content types and reads `raw_path` into `data/raw/`.
- Formats `name_template` (default `{id}`) to obtain the base filename, then chooses the extension based on media type:
	- `image/svg+xml` → PNG via `rsvg-convert`.
	- Other `image/*` except `image/gif` → PNG via ImageMagick `convert` with center‑crop/letterbox.
	- `image/gif` and all `video/*` → MP4 via `ffmpeg`.
- Writes the converted files under `data/targets/<base_dir>/<name>.<ext>`.
- Skips reconversion for an item when the existing output file is newer than its `raw_path`.
- Writes a JSON summary `data/targets/{target}.json` with `base_dir`, `width`, `height`, and an `items` list describing inputs and outputs.

### Language-target multiplexing

For multi-language QML list-models, manifests can stay DRY by using the
`lang_targets` pseudo-plugin. Instead of repeating one target block per
language, you declare language codes once and use a `$lang$` placeholder in
the target templates for the pieces that vary (name, dependency, base_dir,
and any language-specific YAML paths):

```yaml
targets:
	- name: qml-lang
		plugin: lang_targets
		params:
			languages: ["es", "en"]
			targets:
				- name: "$lang$_banners_qml"
					plugin: qml_banners
					deps: ["$lang$:banners"]
					params:
						base_dir: "$lang$/banners"
						list_key: "extractions.banners_items"
```

At manifest load time, this expands into concrete targets like
`es_banners_qml` and `en_banners_qml` with the expected `deps` and
`base_dir` values, so the rest of the DAG/build pipeline only sees
ordinary `TargetSpec` entries.

## Attribution & Curation
Curaflow is **AI-assisted** and **human-curated**. AI (GitHub Copilot / GPT models) generated initial scaffolding and subsequent instrumentation following the policy in ADR-0010. All architectural and process decisions are recorded as ADRs in `docs/adr/`. Human maintainers review intent, enforce tests, and ensure transparency.

## Contributing
See `CONTRIBUTING.md`. Propose changes via issues + ADRs. Reference ADR IDs in commits (e.g., `refs ADR-0002`).
