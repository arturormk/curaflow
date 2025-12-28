# Curaflow – AI Curator Recipe (Experimental)

This experimental recipe tailors the Software Curatorship methodology to Curaflow. It’s a concise, actionable operating guide for humans and AIs collaborating on this repo. It focuses on self-documenting, self-verifying workflows, minimal dependencies, and transparent provenance.

---
## 1) Objectives and Scope
- Purpose: Incremental, parallel fetch → normalize → build for web-curated datasets with hierarchical fanout and structural diffs.
- Deliverables:
  - Deterministic CLI: `plan`, `fetch`, `build`, `status`, `diff`.
  - Stable artifact tree: YAML sources, JSON targets, diffs under `.curaflow/diffs`.
  - Incrementality: Conditional GET (ETag/Last-Modified) + content digests.
- Non-goals:
  - Heavy frameworks, auto-magic plugin discovery, or networked CI tests.

## 2) Architecture (What matters for curation)
- CLI (`curaflow/cli.py`):
  - `plan`: enumerate manifest sources/targets.
  - `fetch`: parallel fetch, normalize to `data/sources/*.yaml`; supports dynamic fanout; persists `.curaflow/meta/sources_dynamic.json`.
  - `build`: topo builds `data/targets/*.json`; rebuilds only if deps newer; writes diffs to `.curaflow/diffs/*.diff.txt` using `deep_diff`.
  - `status`: shows existence and rebuild need.
  - `diff`: show target diff or raw source YAML.
- Data layout:
  - `.curaflow/meta`: fetch metadata, dynamic source registry.
  - `.curaflow/diffs`: structural diffs of targets.
  - `data/raw`: binaries; `data/sources`: normalized YAML; `data/targets`: JSON artifacts.
- Plugins (ADR-0012):
  - Register via decorators in `curaflow/plugin_registry.py`: `@source_plugin`, `@target_plugin`.
  - Built-ins:
    - Sources: `http_html` (extract + fanout), `http_json`, `http_bytes`.
    - Targets: `concat_json` (bundles deps into one JSON).
- DAG (`curaflow/dag.py`): `topo_sort`, `needs_rebuild` (newest dep vs oldest outputs).

## 3) Manifest Schema and Invariants
- Minimal schema (`example/manifest.yaml`):
  - `sources[]`: { `name`, `plugin`, `params` }
  - `targets[]`: { `name`, `plugin`, `deps`, `params` }
- `http_html.params`:
  - `extract`: list of { `name`, `css`, `attr`, `base?` } → yields normalized records with `text`/`href`/`src`, `absolute_url` and `slug`.
  - `fanout`: list of { `from`, `plugin`, `name_template?`, `url_field?`, `params` } → creates child sources.
- Naming rules:
  - `name` becomes filename; must be stable and slug-safe; fanout `name_template` should ensure uniqueness (e.g., `{slug}`, `{index}`).
- Compatibility:
  - Schema or behavior changes must be gated by an ADR and a version bump.

## 4) Plugin Authoring Contract
- Source plugin signature:
  - async `(name: str, params: dict) -> (changed: bool, data: dict|None, children: list[spec])`
  - Writes `data/sources/{name}.yaml` on change; returns `children` specs: `{name, plugin, params}`.
- Target plugin signature:
  - `(name: str, deps: list[str], params: dict) -> { previous, current, output_path }`
  - Writes `data/targets/{name}.json`; returns previous/current for diffing.
- Error handling:
  - Source errors should be captured by `execute_source` and reported; avoid aborting the whole run.
- Discovery:
  - No auto-discovery; plugin modules must be imported (import side-effects register them).

## 5) Quality Gates (Definition of Done)
- Lint: Ruff clean (`pyproject.toml` defines rules, line-length=100, double quotes).
- Types: mypy strict; if deferring, include rationale in PR and a tracked follow-up.
- Tests: deterministic, fast, offline; add tests for any new behavior.
- Docs: update `README.md` or add/modify ADRs when behavior/architecture changes.
- Build: `python -m build` succeeds; CLI smoke (`plan`) still works.
- Provenance: keep Attribution & Curation text and `AUTHORS` intact (ADR-0010).
- ADR integrity: new decisions recorded; index valid and up to date.

## 6) AI Curation Policy (see `docs/adr/0010-ai-curation-policy.md`)
- AI drafts, human curator owns intent and approves.
- For meaningful changes: add tests, update/add ADRs, pass all hooks.
- Large AI batches may use `Curated-By:` footer.
- Never remove attribution/licensing.

## 7) Developer Runbook (local)
- Bootstrap: `pip install -r requirements-dev.txt && pip install -e .`
- Fast smoke: `bash scripts/fast_tests.sh`
- ADR checks: `python scripts/lint_adrs.py` and `python scripts/check_adr_index.py`
- No bare `print()` in package (except CLI uses `rich.print`) → `bash scripts/check_prints.sh`.
- CLI usage demo: `python -m curaflow.cli plan -m example/manifest.yaml`

## 8) Testing Strategy (what to test here)
- DAG: order and rebuild policy (`tests/test_dag.py`).
- Diffing: structural path-aware diffs (`tests/test_diffing.py`).
- Plugin registry: registration, duplicates, decorator paths, error capture (`tests/test_plugin_registry.py`).
- CLI smoke: `plan` with example manifest (`tests/test_cli_plan.py`).
- Avoid network in tests; mock or keep logic isolated from HTTP.

## 9) Automations: Self-Documenting + Self-Verifying
- Already present (wire into hooks/CI):
  - `scripts/check_adr_index.py` → updates `docs/adr/README.md` index (non-zero exit when changes written).
  - `scripts/lint_adrs.py` → file naming, required sections, and Status validation.
  - `scripts/fast_tests.sh` → sentinel test subset.
  - `scripts/check_prints.sh` → ban stray `print()` in package.
  - Tooling: Ruff + mypy configured in `pyproject.toml`.
- Recommended pre-commit (fast):
  - ruff check --fix; ruff format
  - mypy (cached)
  - scripts/check_adr_index.py (fail if it modifies the index and changes aren’t committed)
  - scripts/lint_adrs.py
  - scripts/check_prints.sh
  - pre-push: scripts/fast_tests.sh
- Recommended CI (GitHub Actions) stages:
  1) Setup Python (3.10, 3.11), install `requirements-dev.txt` and `-e .`.
  2) Lint: `ruff check .` and `ruff format --check .`.
  3) Types: `mypy curaflow tests scripts`.
  4) Tests: `pytest -q` (no network calls).
  5) ADRs: run both ADR scripts; fail if index is out-of-date.
  6) Build: `python -m build` as packaging sanity.
  7) CLI contract smoke: run `curaflow plan -m example/manifest.yaml`.
- Optional self-documentation tasks:
  - Plugin inventory: generate `docs/plugins.md` by importing `curaflow.plugins` and printing `list_sources()`/`list_targets()`.
  - Manifest schema: add `docs/manifest.schema.json` + `docs/manifest.md` and validate `example/manifest.yaml` in CI.

## 10) Incident Log (curator knowledge)
- Location: `docs/incidents/`.
- Include: ID, Date, Status, Context, Symptom, Root Cause, Resolution, Prevention/Guardrail, References.
- Criteria: recurring value (e.g., packaging pitfalls, ADR drift, registration gotchas).
- Couple each incident to a guardrail (script, check, or test) before closing.

## 11) Governance (ADRs)
- Files under `docs/adr/` follow: `NNNN-kebab-title.md` with Context, Decision, Consequences; Status in {Proposed, Accepted, Superseded}.
- Index auto-maintained in `docs/adr/README.md` between markers; CI should fail when stale.
- Reference ADR IDs in commits/PRs (e.g., `refs ADR-0012`).

## 12) Releases and Versioning
- SemVer; version in `pyproject.toml`.
- Release checklist:
  1) CI green; `python -m build` OK.
  2) README/ADRs reflect new behavior.
  3) Tag `vX.Y.Z`; publish if desired; use GitHub Releases.
  4) If behavior changes materially, add a migration/advisory note.

## 13) Ethics and Operational Constraints (scraping)
- Respect robots.txt and site policies; document stance in README/ADRs.
- Concurrency: default `fetch --max-concurrent 10`; expose and document safe ranges.
- Idempotency: rely on conditional GET + SHA-256 digests to avoid duplicate writes.
- Reproducibility: persist normalized YAML + minimal fetch metadata.

## 14) Contracts and Edge Cases (for AI and humans)
- CLI contracts:
  - `plan`: exits 0; prints headings “Sources” and “Targets”.
  - `fetch`: tolerates unknown plugin names by skipping with a warning; records dynamic children; writes unchanged vs updated messages.
  - `build`: only rebuilds when deps newer; writes diffs; tolerates missing plugins by skipping targets (warn).
  - `status`: prints 2 tables; includes dynamic sources discovered in `.curaflow/meta/sources_dynamic.json`.
  - `diff`: `targets:NAME` prints the recorded diff; `sources:NAME` prints source YAML.
- Likely edge cases:
  - Fanout explosion: add future guardrails (depth/count caps; domain allowlist).
  - HTML parsing variability: ensure slug generation fallback; attribute lists (BeautifulSoup) are normalized.
  - Dynamic source persistence: always write after fanout; ensure idempotent merges.
  - Binary content types: infer extension via mimetypes; default to octet-stream.

## 15) Future Enhancements (record via ADRs)
- Fanout guardrails and observability (counts, depth, skipped children report).
- Security scanning (`pip-audit`), optional Bandit.
- Property-based testing for diffing/normalization cores.
- Cross-platform CI matrix.
- Coverage reporting once baseline stabilized.

## 16) AI Assistant Operating Procedure (condensed)
1) Read the tree; list and open key files before editing.
2) Expand the user ask into a checklist; don’t omit requirements.
3) Prefer minimal diffs; implement with proper file editing tooling.
4) After changes, run lint/tests/build locally; iterate to green or clearly defer.
5) Summarize deltas; map each requirement → Done/Deferred.
6) Attribute properly; never remove license or provenance text.

---
This document is experimental and exists alongside the canonical `AI_CURATOR_RECIPE.md`. Prefer to converge by ADR once the experiment stabilizes.
