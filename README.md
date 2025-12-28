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
```

## Highlights

- **Sources (YAML):** `http_json`, `http_html` (CSS selectors), `http_xml` (XML via ElementTree paths), `http_bytes` (binary, metadata YAML + file in `data/raw/`).
- **Hierarchical fanout:** HTML extractions can spawn child sources (pages → images).
- **Conditional GET:** ETag / Last-Modified + content digests to avoid redundant work.
- **Targets:** Declare artifacts with deps; rebuild only when deps are newer.
- **Diffs:** Structural diffs for targets stored in `.curaflow/diffs/`.
- **Dynamic registry:** Discovered sources are persisted in `.curaflow/meta/sources_dynamic.json`.

See `example/manifest.yaml` and comments in `curaflow/plugins/sources/http_html.py`.

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

## Attribution & Curation
Curaflow is **AI-assisted** and **human-curated**. AI (GitHub Copilot / GPT models) generated initial scaffolding and subsequent instrumentation following the policy in ADR-0010. All architectural and process decisions are recorded as ADRs in `docs/adr/`. Human maintainers review intent, enforce tests, and ensure transparency.

## Contributing
See `CONTRIBUTING.md`. Propose changes via issues + ADRs. Reference ADR IDs in commits (e.g., `refs ADR-0002`).
