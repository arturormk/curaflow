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

- **Sources (YAML):** `http_json`, `http_html` (with CSS selectors), `http_bytes` (binary, metadata YAML + file in `data/raw/`).
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

Ship a module that imports the decorators (import side-effect registers). No auto-discovery yet—ensure your plugin module is imported before use (e.g. `import my_package.curaflow_plugins`).

Source plugin return tuple:
1. `changed` (bool) – whether output YAML updated.
2. `data` – structured object (serialized to YAML by your function if you write the file yourself; current built-ins write directly).
3. `children` – list of dynamically spawned source specs `{name, plugin, params}`.

Target plugin return dict should include at minimum:
* `previous` – prior object (if exists)
* `current` – new artifact object
* `output_path` – written file path

See ADR-0012 for rationale.

## Attribution & Curation
Curaflow is **AI-assisted** and **human-curated**. AI (GitHub Copilot / GPT models) generated initial scaffolding and subsequent instrumentation following the policy in ADR-0010. All architectural and process decisions are recorded as ADRs in `docs/adr/`. Human maintainers review intent, enforce tests, and ensure transparency.

## Contributing
See `CONTRIBUTING.md`. Propose changes via issues + ADRs. Reference ADR IDs in commits (e.g., `refs ADR-0002`).
