# AI Curator Recipe — Baseline (v0.1)

This repository follows the Software Curatorship methodology. The goal is a **self-documenting, self-verifying, curator-friendly** codebase where AI assists and the human curator owns decisions.

> Note: This file is adapted for Curaflow (experimental v0.2). Headings and section order remain identical to the baseline for diffability.

## 1) Intent & Scope
- Keep runtime minimal; favor clarity and determinism.
- All user-visible behavior is test-backed and explained via ADRs.
- Provenance is transparent (README “Attribution & Curation”, ADR-0010, AUTHORS).

Curaflow-specific objectives:
- Provide an incremental, parallel fetch → normalize → build pipeline for web-curated datasets.
- Support hierarchical fanout (index → entity pages → assets) with dynamic sources persisted under `.curaflow/meta/`.
- Store normalized YAML sources and JSON targets; record structural diffs on build.

## 2) Product Contract (plain language)

This contract covers the Curaflow CLI defined in `curaflow/cli.py`.

- Inputs
  - Manifest file (YAML): path via `-m/--manifest` (e.g., `example/manifest.yaml`).
  - Network endpoints (at operator’s discretion) when running `fetch`.
  - Existing on-disk artifacts under: `.curaflow/meta`, `.curaflow/diffs`, `data/raw`, `data/sources`, `data/targets`.

- Outputs/streams
  - Filesystem:
    - `data/sources/{name}.yaml` (normalized source outputs)
    - `data/targets/{target}.json` (built artifacts)
    - `.curaflow/meta/sources_dynamic.json` (persisted dynamic sources)
    - `.curaflow/meta/src_{name}.json` (fetch metadata: etag, last-modified, digest)
    - `.curaflow/diffs/{target}.diff.txt` (line-oriented structural diffs)
  - Stdout: All CLI table/listing output, progress messages, warnings, and diffs (uses `rich.print` where applicable). There is currently no separation of diagnostics to stderr.

- Commands and exit codes
  - `plan -m <manifest>`
    - Behavior: Prints "Sources" and "Targets" with names and plugins.
    - Exit codes: 0 on success; non-zero only on unexpected exceptions.
  - `fetch -m <manifest> [--max-concurrent N]`
    - Behavior: Parallel fetch; writes/updates source YAMLs and dynamic children; prints per-source status ("updated"/"unchanged").
    - Exit codes: 0 on success (even if some plugins are skipped for not being registered); non-zero only on unexpected exceptions.
  - `build -m <manifest>`
    - Behavior: Topologically builds targets; rebuilds only when deps are newer; writes diffs when structure changes; skips targets whose plugin is not registered (warns).
    - Exit codes: 0 on success; non-zero only on unexpected exceptions.
  - `status -m <manifest>`
    - Behavior: Prints two tables: Sources (file existence) and Targets (output path and rebuild status). Includes dynamic sources from `.curaflow/meta/sources_dynamic.json`.
    - Exit codes: 0 on success; non-zero only on unexpected exceptions.
  - `diff targets:NAME`
    - Behavior: Prints the recorded structural diff for the target, if any; prints a friendly note if no diff exists.
    - Exit codes: 0 if diff exists or if none is recorded; non-zero only on unexpected exceptions.
  - `diff sources:NAME`
    - Behavior: Prints the normalized YAML for the source.
    - Exit codes: 1 if the source YAML does not exist; 0 otherwise.
  - `diff` with invalid kind (not `sources`/`targets`): prints usage guidance; exits 0.

- Determinism
  - Given the same inputs on disk and network responses, repeated `build` runs produce identical artifacts and diffs.
  - `deep_diff` sorts mapping keys; diff line order is stable.
  - `needs_rebuild` considers newest dependency mtime vs oldest outputs; behavior is deterministic on a stable filesystem clock.
  - `topo_sort` produces a deterministic order for strictly ordered graphs; when multiple targets are independent (no edges among them), relative order between those independent nodes is not guaranteed (tie-breaking is unspecified today). Tests and documentation must not rely on ordering among independent targets.

## 3) Curation Principles
- AI drafts; human curator approves and is accountable.
- Non-trivial changes: add/update tests and ADRs; document behavior changes in README.
- Prefer stdlib/zero-deps unless an ADR justifies otherwise.

## 4) Repository Map
- `curaflow/…` (package and CLI; no `src/` layout in this repo)
- `tests/…` (functional/contracts + edges; network-free)
- `docs/adr/` (NNNN-kebab.md + `README.md` index with markers)
- `docs/incidents/` (optional but encouraged)
- `scripts/` (ADR linters, print guard, fast test subset)
- `.curaflow/` (runtime metadata and diffs; generated)
- `data/` (raw, sources, targets; generated)
- (Recommended) `.github/workflows/ci.yml` and `.pre-commit-config.yaml`

## 5) ADR Policy
- Required sections: **Context · Decision · Consequences**
- Status: Proposed → Accepted → Superseded
- Index in `docs/adr/README.md` is auto-maintained by `scripts/check_adr_index.py`; CI should fail if stale. Structural checks via `scripts/lint_adrs.py`.

## 6) Testing Strategy
- Focus on **contracts** (CLI behavior, exit codes, structural diffs, rebuild policy).
- Add at least one **edge case** per changed behavior.
- No network; deterministic and fast. Keep a `scripts/fast_tests.sh` subset.

## 7) Automation — Self-Verifying
**Local (pre-commit, recommended):**
- Ruff lint + format (fast)
- mypy (cached)
- ADR index + ADR lint (`scripts/check_adr_index.py`, `scripts/lint_adrs.py`)
- Print-guard (`scripts/check_prints.sh`)
- Pre-push: `scripts/fast_tests.sh`

**CI (recommended minimal):**
- Setup matrix (Python 3.10, 3.11)
- Lint → Types → Tests → Build
- ADR checks (index + lint); fail if index gets modified
- CLI smoke: `curaflow plan -m example/manifest.yaml` (no-network)

## 8) Definition of Done
- Lint/types/tests/build all green
- Tests cover new/changed behavior
- README/ADRs updated if user-visible changes
- Provenance intact (README + ADR-0010 + AUTHORS)
- Versioning/package sanity verified

## 9) AI Assistant Operating Procedure
1. Read the tree & target files (no guessing paths).
2. Expand the curator’s ask into a checklist.
3. Propose minimal diffs; avoid unrelated reformatting.
4. Run local checks (lint/types/tests/build); iterate to green or state deferrals.
5. Summarize deltas mapping each checklist item → Done/Deferred.
6. Keep attribution; never remove license/provenance.

## 10) Releases & Versioning
- Semantic Versioning; single source of truth in `pyproject.toml` (`version = "0.1.0"`).
- Tag `vX.Y.Z`; ensure CI green on tag; publish release notes.
- Build verification: `python -m build` must succeed; console script `curaflow` entry point must be resolvable (`[project.scripts]`).
- Packaging layout: package `curaflow` (no `src/` layout). If migrating to a different layout or dynamic versioning, draft an ADR first.

## 11) Maintenance Rhythm
- Periodically: `pre-commit run --all-files`, README accuracy review, ADR housekeeping.
- Recurrent issues → log an Incident and add a guardrail before closing.

---

### Appendix A — Project-Specific Contracts (Curaflow)

- CLI/API contracts
  - `plan -m PATH`
    - Prints headings "Sources" and "Targets" with items and plugins; exit 0.
  - `fetch -m PATH [--max-concurrent N]`
    - Performs conditional GET (If-None-Match/If-Modified-Since) and content-digest checks.
    - Writes `data/sources/{name}.yaml` for changed sources; persists `.curaflow/meta/sources_dynamic.json` for children.
    - Logs per-source status (updated/unchanged/skipped) to stdout; exit 0 even if some plugins aren’t registered.
  - `build -m PATH`
    - Builds `data/targets/{name}.json` in topological order; only when deps are newer.
    - Computes structural diffs with `deep_diff(prev,current)` and writes `.curaflow/diffs/{name}.diff.txt` when changes exist.
    - Unknown target plugins are reported and skipped; exit 0.
  - `status -m PATH`
    - Two tables with existence and rebuild decisions; includes dynamic sources.
    - Exit 0.
  - `diff targets:NAME`
    - Prints diff content if present; otherwise prints a friendly note; exit 0.
  - `diff sources:NAME`
    - Prints source YAML; exit 1 if missing.

- Determinism rules
  - `deep_diff`: deterministic ordering by sorted mapping keys; list diffs summarized (no per-item alignment).
  - `build`: deterministic outputs given identical inputs and mtimes; no non-deterministic data is introduced by Curaflow.
  - `topo_sort`: unspecified tie-breaks among independent targets; avoid tests that rely on those relative orders.

- Domain rules
  - Plugins register via decorators (`@source_plugin`, `@target_plugin`) and require an import side-effect; there is no auto-discovery.
  - Source plugin return contract: `(changed, data, children)`; target plugin returns `{previous, current, output_path}`.
  - Normalized artifacts live under `data/sources/` (YAML) and `data/targets/` (JSON). Binary assets persist under `data/raw/` with content-type-derived extension.
  - Dynamic children are first-class sources, persisted in `.curaflow/meta/sources_dynamic.json` and considered in subsequent fetch/build/status operations.

- Edge cases we explicitly care about
  - Missing source YAML for `diff sources:NAME` → exit 1 with clear message.
  - Missing target diff file → do not error; report none recorded.
  - Unregistered plugins in manifest → skip item with warning; CLI continues with exit 0.
  - HTML attributes with list values (BeautifulSoup) are normalized to string; `slugify` has fallbacks when text/URL is missing.
  - Binary content-type inference falls back to `application/octet-stream` and may produce an empty extension. This is acceptable and documented.

---

### Automation adjustments (minimal, enforcement-oriented)

- Pre-commit (recommended `.pre-commit-config.yaml`)
  - ruff check --fix; ruff format
  - mypy (cached)
  - `python scripts/check_adr_index.py` (fail if it modifies the ADR index and changes aren’t staged)
  - `python scripts/lint_adrs.py`
  - `bash scripts/check_prints.sh`
  - Pre-push: `bash scripts/fast_tests.sh`

- CI (recommended `.github/workflows/ci.yml`)
  - Matrix: Python 3.10, 3.11
  - Steps:
    1) Install: `pip install -r requirements-dev.txt` and `pip install -e .`
    2) Lint: `ruff check .` and `ruff format --check .`
    3) Types: `mypy curaflow tests scripts`
    4) Tests: `pytest -q` (no network assumptions)
    5) ADRs: `python scripts/lint_adrs.py` and `python scripts/check_adr_index.py` (fail if index is modified)
    6) Build: `python -m build`
    7) CLI smoke: `python -m curaflow.cli plan -m example/manifest.yaml`

- Optional future (defer until ADR):
  - Manifest schema validation step (JSON Schema) for `example/manifest.yaml`.
  - Auto-generated plugin inventory docs from `list_sources()` / `list_targets()`.

---

### Deferred with rationale
- Topological order tie-break determinism: today, ordering among independent targets is unspecified; enforcing lexical tie-breaks would require a small code change (stdlib-only) and should be decided via ADR to avoid silent behavior changes for users relying on current order (even if not guaranteed).
- Separate stderr for diagnostics: current CLI sends diagnostics to stdout via `rich.print`; changing streams is a user-visible contract shift and should be ADR’d if pursued.
- Manifest schema validation and docs generation: valuable, but adds maintenance; propose via ADR after initial convergence on the manifest shape.

---

### Tests checklist to validate the contract
- CLI contracts
  - `plan` prints "Sources" and "Targets"; exit 0 (exists).
  - `diff sources:__missing__` exits 1 and prints an error (add).
  - `diff targets:__missing__` exits 0 with a friendly message (add).
  - `diff` with invalid kind exits 0 and prints usage guidance (add).
- Build/rebuild rules
  - Target not rebuilt when deps older; rebuilt when any dep mtime increases (exists for core logic; consider adding CLI-level smoke using temp dirs).
- Diffing
  - `deep_diff` deterministic ordering of dict keys; list diff summarized (exists partially; add test for deterministic order with multiple keys).
- Plugin registry
  - Registration, duplicate protection, error capture (exists).
- Dynamic sources
  - `status` includes dynamic sources persisted in `.curaflow/meta/sources_dynamic.json` (add using a pre-baked file in a tmp workspace).
- Unknown plugins
  - `fetch` and `build` skip unregistered plugins with a warning; process exits 0 (add using a synthetic manifest).
- Print guard
  - `scripts/check_prints.sh` flags bare print() in package files (ensure a test or CI check runs it; currently enforced via script—CI hook will cover).
