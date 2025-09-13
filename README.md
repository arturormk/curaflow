# Curaflow

*Incremental, parallel fetch → normalize → build for web-curated datasets.*

**New:** hierarchical fanout: scrape an index page → fan out to tenant pages → fan out to images (binary).

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .

curaflow plan -m example/manifest.yaml
curaflow fetch -m example/manifest.yaml
curaflow build -m example/manifest.yaml
curaflow status -m example/manifest.yaml
curaflow diff targets:tenants_bundle -m example/manifest.yaml
```

## Highlights

- **Sources (YAML):** `http_json`, `http_html` (with CSS selectors), `http_bytes` (binary, metadata YAML + file in `data/raw/`).
- **Hierarchical fanout:** HTML extractions can spawn child sources (pages → images).
- **Conditional GET:** ETag / Last-Modified + content digests to avoid redundant work.
- **Targets:** Declare artifacts with deps; rebuild only when deps are newer.
- **Diffs:** Structural diffs for targets stored in `.curaflow/diffs/`.
- **Dynamic registry:** Discovered sources are persisted in `.curaflow/meta/sources_dynamic.json`.

See `example/manifest.yaml` and comments in `curaflow/plugins/sources/http_html.py`.

## Attribution & Curation
Curaflow is **AI-assisted** and **human-curated**. AI (GitHub Copilot / GPT models) generated initial scaffolding and subsequent instrumentation following the policy in ADR-0010. All architectural and process decisions are recorded as ADRs in `docs/adr/`. Human maintainers review intent, enforce tests, and ensure transparency.

## Contributing
See `CONTRIBUTING.md`. Propose changes via issues + ADRs. Reference ADR IDs in commits (e.g., `refs ADR-0002`).
