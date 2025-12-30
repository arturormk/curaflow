# AI Curator Recipe — Curaflow

This document specializes the project‑agnostic guidance in `AI_CURATOR_RECIPE.md` for the Curaflow codebase.

- For **overall methodology, quality gates, and AI curation policy**, see `AI_CURATOR_RECIPE.md`.
- This file focuses on **Curaflow‑specific contracts**: CLI behavior, manifest schema, plugin contracts, data layout, and automation.

---
## 1. Intent & Scope (Curaflow)

Curaflow provides an **incremental, parallel fetch → normalize → build** pipeline for web‑curated datasets.

Curaflow‑specific objectives:
- Support **hierarchical fanout** (index → entity pages → assets) with dynamic sources persisted under `.curaflow/meta/`.
- Store normalized **YAML sources** and **JSON targets**, with structural diffs captured per build.
- Expose a small, deterministic CLI surface (see Section 3) backed by tests.

Non‑goals (for this repo):
- Heavy frameworks, auto‑magic plugin discovery, or networked CI tests.


## 2. Architecture & Data Layout

Key components:
- `curaflow/cli.py` — CLI entrypoint (`plan`, `fetch`, `build`, `status`, `diff`).
- `curaflow/dag.py` — dependency graph and `needs_rebuild` logic.
- `curaflow/plugins/` — built‑in source and target plugins, registered via decorators.
- `curaflow/diffing.py` — structural, path‑aware diffs between previous and current artifacts.

Directory layout (runtime‑relevant):
- `.curaflow/meta/`
  - `src_{name}.json` — fetch metadata (ETag, Last‑Modified, SHA‑256 digest).
  - `sources_dynamic.json` — registry of dynamically discovered child sources (from fanout).
- `.curaflow/diffs/`
  - `{target}.diff.txt` — structural diffs between previous and current target output.
- `data/raw/` — binary assets fetched via `http_bytes` (e.g., images).
- `data/sources/` — normalized YAML for each source: `data/sources/{name}.yaml`.
- `data/targets/` — built JSON artifacts: `data/targets/{target}.json`.

Children discovered during `fetch` are persisted in `.curaflow/meta/sources_dynamic.json` and treated as first‑class sources on subsequent runs.


## 3. CLI Contract (Curaflow)

All behavior below is part of the Curaflow contract and must stay in sync with tests.

### 3.1 Commands & Exit Codes

- `plan -m <manifest>`
  - Prints headings `Sources` and `Targets` with names and plugins.
  - Exit code: `0` on success; non‑zero only on unexpected exceptions.

- `fetch -m <manifest> [--max-concurrent N] [--debug] [--force]`
  - Parallel fetch against manifest sources **and** any dynamic children in `.curaflow/meta/sources_dynamic.json`.
  - Uses conditional GET (If‑None‑Match / If‑Modified‑Since) based on stored metadata.
  - Writes or updates `data/sources/{name}.yaml` when content changes; returns `changed` flag.
  - Persists newly discovered dynamic sources into `.curaflow/meta/sources_dynamic.json`.
  - Tolerates unknown plugins by skipping with a warning.
  - Exit code: `0` even if some plugins are skipped; non‑zero only on unexpected exceptions.

- `build -m <manifest>`
  - Builds targets in **topological order**.
  - Rebuilds a target only when its dependencies are newer than its outputs (`needs_rebuild`).
  - Writes `data/targets/{name}.json` on change.
  - Computes structural diffs via `deep_diff(previous, current)` and writes them to `.curaflow/diffs/{name}.diff.txt`.
  - Skips targets with unregistered plugins (warns, does not fail the whole run).
  - Exit code: `0` on success; non‑zero only on unexpected exceptions.

- `status -m <manifest>`
  - Prints two tables:
    - Sources: existence of `data/sources/{name}.yaml`, including dynamic sources.
    - Targets: output path and whether a rebuild is needed.
  - Exit code: `0` on success; non‑zero only on unexpected exceptions.

- `diff targets:NAME`
  - Prints recorded structural diff for the target from `.curaflow/diffs/NAME.diff.txt`.
  - If no diff is recorded, prints a friendly message rather than erroring.
  - Exit code: `0` whether diff exists or not; non‑zero only on unexpected exceptions.

- `diff sources:NAME`
  - Prints normalized YAML for `data/sources/NAME.yaml`.
  - Exit code: `0` if the YAML exists; `1` if it does not.

- `diff` with invalid kind (not `sources`/`targets`)
  - Prints usage guidance.
  - Exit code: `0` (contract is to treat this as user guidance, not a failure).

### 3.2 Determinism Rules

- Given identical disk state and network responses, repeated `build` runs must produce identical targets and diffs.
- `deep_diff` sorts mapping keys; diff line ordering is stable.
- `needs_rebuild` compares **newest dependency mtime** vs **oldest outputs**.
- `topo_sort` is deterministic for graphs with strict ordering; order among independent targets is currently **unspecified** and tests must not rely on it.


## 4. Manifest Schema (Curaflow)

Curaflow’s manifest (see `example/manifest.yaml`) defines **sources** and **targets**.

### 4.1 Sources

Minimal schema:

```yaml
top-level:
  sources:
    - name: "source_name"
      plugin: some_source_plugin
      params: { ... }
```

Core built‑in source plugins:
- `http_html` — fetch HTML, extract via CSS selectors, normalize to YAML, optionally fan out.
- `http_json` — fetch JSON, extract subtrees (see plugin docs), optionally fan out.
- `http_xml` — fetch XML, extract via `ElementTree.findall` paths, normalize to YAML, optionally fan out.
- `http_bytes` — fetch binary content (images, PDFs, etc.) and store in `data/raw/`.

#### 4.1.1 `http_html.params`

```yaml
params:
  url: "https://example.com/page"
  headers: { ... }          # optional
  extract:
    - name: "tenant_links"
      css: ".tenant-card a"
      attr: href            # one of: href, src, text; default: text
      base: null            # optional override for URL resolution
      inject:               # optional; Curaflow-specific extension
        field_name: "{slug}"
  fanout:
    - from: "tenant_links"
      plugin: "http_html"  # or http_json/http_bytes/etc.
      name_template: "tenant:{slug}"
      url_field: "absolute_url"   # defaults to "absolute_url"
      params:
        url: "{absolute_url}"
        # arbitrary nested params for the child plugin
```

Extraction behavior:
- Each `extract` entry defines a **named extraction group** (e.g., `tenant_links` → `extractions.tenant_links`).
- For each matched element:
  - If `attr: text` (default), grabs the element’s text into `text`.
  - If `attr: href`/`src`, records that attribute and, when present, computes `absolute_url` via `urljoin(base, value)`.
  - Synthesizes a `slug`:
    - Prefer `text`, else last path segment of `absolute_url`, else a fallback from the attribute value.
- `inject` (optional):
  - Map of `field_name -> template_or_value`.
  - String values are formatted with the current record (e.g., `"{slug}"`, `"{absolute_url}"`) and written into each record.
  - Non‑string values are copied as‑is.

Fanout behavior:
- `fanout[*].from` refers to a local extraction key (e.g., `tenant_links`).
- For each record in that extraction group:
  - Builds a child source spec `{name, plugin, params}`.
  - `name_template` is formatted with a **safe** mapping over the record (e.g., `{slug}`, `{index}`, `{absolute_url}`); missing keys are left as `{key}` rather than raising.
  - `params` is processed **recursively**: any string anywhere in the structure is formatted with the parent record.
  - If `params.url` is not set, it defaults to `item[url_field]`.
- Children are first‑class sources, written to `data/sources/{child_name}.yaml` and persisted via `.curaflow/meta/sources_dynamic.json`.

This allows patterns like:

```yaml
- name: news
  plugin: http_xml
  params:
    url: $url_news$
    extract:
      - name: news_items
        path: ".//item"
    fanout:
      - from: news_items
        plugin: http_html
        name_template: "$prefix$_news_detail:{slug}"
        params:
          url: "{absolute_url}"
          extract:
            - name: news_image
              css: ".single-evento-imagen img"
              attr: "src"
              inject:
                item_slug: "{slug}"
          fanout:
            - from: news_image
              plugin: http_bytes
              name_template: "$prefix$_news_image:{item_slug}"
              params:
                url: "{absolute_url}"
```

Here, the **XML item slug** is injected into each `news_image` record so binary assets can be named by the logical news slug rather than an opaque image filename.

#### 4.1.2 `http_xml.params`

Key points (full details in the plugin docstring):
- `extract[*].path` is passed to `root.findall(path)`.
- Each matched element becomes a record; child elements are flattened into fields.
- Attributes are exposed as `@attr` fields.
- URL normalization: if a field named `URL`/`url`/`link`/`href` exists, `absolute_url` is added using `base` or `url` as the base.
- `slug` is synthesized from `ID`/`id`/`post_title`/`title`/`absolute_url`, falling back to `name-index`.
- `fanout` uses the same nested‑template formatting as `http_html`.

#### 4.1.3 `http_bytes.params`

- `url`: required; URL for the binary.
- `headers`: optional.
- `force`: optional; forces re‑fetch ignoring HTTP cache metadata.
- Writes metadata under `.curaflow/meta/` and binary content under `data/raw/{name}.*` with an extension inferred from content type (falling back to `application/octet-stream`).

### 4.2 Targets

Minimal schema:

```yaml
targets:
  - name: "target_name"
    plugin: some_target_plugin
    deps: ["source_a", "source_b", ...]
    params: { ... }
```

Core built‑in target plugin:
- `concat_json` — bundles one or more dependency YAMLs into a single JSON artifact.

Targets are built in topological order based on the `deps` graph, using `needs_rebuild` to decide whether to rebuild.


## 5. Plugin Authoring Contract

Curaflow’s plugin system is defined in `curaflow/plugin_registry.py` and documented in ADR‑0012.

### 5.1 Source Plugins

Signature:

```python
@source_plugin("plugin_name")
async def fetch(name: str, params: dict[str, object]) -> tuple[bool, dict[str, Any] | None, list[dict[str, Any]]]:
    ...
```

Contract:
- `name` is the **source name** (also used for filenames).
- `params` originates from manifest `params` plus internal flags (e.g., `force`).
- Return tuple:
  - `changed: bool` — whether normalized data changed.
  - `data: dict | None` — normalized representation (usually written to `data/sources/{name}.yaml`).
  - `children: list[dict[str, Any]]` — dynamic child source specs of the shape `{"name", "plugin", "params"}`.
- Plugins are expected to:
  - Respect `force` when present (bypass HTTP cache metadata).
  - Write their own normalized data to `data/sources/{name}.yaml` when `changed`.

### 5.2 Target Plugins

Signature:

```python
@target_plugin("plugin_name")
def build(name: str, deps: list[str], params: dict[str, object]) -> dict[str, Any]:
    ...
```

Contract:
- `name` is the target name and output filename stem.
- `deps` are names of source/target artifacts this target depends on.
- `params` is free‑form plugin configuration.
- Return dict must include at least:
  - `previous`: previous normalized structure (or `None` if not present).
  - `current`: new normalized structure.
  - `output_path`: location under `data/targets/`.

`curaflow/cli.py` handles diffing (`deep_diff(previous, current)`) and persists diffs to `.curaflow/diffs/`.


## 6. Guardrails & Testing (Curaflow)

In addition to the generic gates in `AI_CURATOR_RECIPE.md`, Curaflow emphasizes:

- **No network in tests** — HTTP logic must be isolated or mocked.
- **Contract tests** for CLI and plugins:
  - `tests/test_cli_plan.py` — `plan` headings and manifest handling.
  - `tests/test_dag.py` — `topo_sort` and `needs_rebuild`.
  - `tests/test_diffing.py` — deterministic structural diffs.
  - `tests/test_plugin_registry.py` — registration, duplicate detection, error capture.
  - `tests/test_fetch_parallel.py` — concurrency limits and dynamic source persistence.
  - Additional tests around plugins (`http_html`, `http_xml`, etc.) as they evolve.
- **Dynamic sources** — tests must ensure `.curaflow/meta/sources_dynamic.json` is honored by `fetch` and `status`.
- Unknown plugins in the manifest are **warnings, not hard failures**.


## 7. Automation: Pre‑commit & CI (Curaflow)

These settings complement the generic recipe and are considered part of the Curaflow contract.

### 7.1 Local (recommended)

- Lint & format: `ruff check . --fix` and `ruff format .`.
- Types: `mypy curaflow tests scripts` (strict; defer only with explicit rationale).
- ADR checks:
  - `python scripts/check_adr_index.py` — maintains `docs/adr/README.md` index; should fail if it rewrites the index.
  - `python scripts/lint_adrs.py` — validates ADR structure and status.
- Print guard: `bash scripts/check_prints.sh` — bans bare `print()` inside the package (CLI uses `rich.print`).
- Fast tests: `bash scripts/fast_tests.sh`.

### 7.2 CI (recommended baseline)

- Python versions: at least 3.10 and 3.11.
- Steps:
  1. Install dev deps: `pip install -r requirements-dev.txt` and `pip install -e .`.
  2. Lint: `ruff check .` and `ruff format --check .`.
  3. Types: `mypy curaflow tests scripts`.
  4. Tests: `pytest -q` (no network).
  5. ADR checks: `python scripts/lint_adrs.py` and `python scripts/check_adr_index.py`.
  6. Build: `python -m build`.
  7. CLI smoke: `python -m curaflow.cli plan -m example/manifest.yaml`.


## 8. Edge Cases & Known Behaviors

Curaflow explicitly cares about the following edge cases:

- **Missing source YAML for `diff sources:NAME`**
  - Behavior: print clear message; exit `1`.

- **Missing target diff file for `diff targets:NAME`**
  - Behavior: print friendly note; exit `0`.

- **Unregistered plugins in manifest**
  - Behavior: `fetch`/`build` skip those entries with a warning; process continues with exit `0`.

- **HTML parsing quirks**
  - BeautifulSoup attributes that are lists are normalized to strings.
  - `slugify` must have stable fallbacks when text/URL is missing (see `tests/test_html_utils.py`).

- **Binary content types**
  - Extension is inferred from `Content-Type` when possible, falling back to `application/octet-stream` and possibly an empty extension — this is acceptable and documented.

- **Dynamic source persistence**
  - Dynamic children discovered during fetch are always written to `.curaflow/meta/sources_dynamic.json` and re‑used on future runs.


## 9. Relationship to ADRs & Incidents

- Architectural and behavioral decisions for Curaflow are recorded under `docs/adr/`.
  - ADR‑0002 — hierarchical fanout design.
  - ADR‑0012 — plugin registry and built‑in plugins.
  - ADR‑0010 — AI curation policy.
- Non‑trivial regressions or subtle contract risks should be captured in `docs/incidents/` along with the guardrails that prevent recurrence (tests, hooks, docs).

---

This Curaflow‑specific recipe should stay compact and focused on **actual contracts the code and tests enforce**. For broader methodology, AI assistant behavior, and general project hygiene, defer to `AI_CURATOR_RECIPE.md`.
