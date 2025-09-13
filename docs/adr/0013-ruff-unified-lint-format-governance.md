# 0013: Adopt unified Ruff lint & format governance workflow

Status: Accepted

## Context

During implementation of the plugin registry (ADR-0012) several development cycles were slowed by repetitive Ruff failures (import ordering, misplaced imports, indentation / formatting mismatches). The friction exposed a gap: while Ruff had already replaced a traditional stack (isort + Flake8 + Black) implicitly, we had not explicitly codified:

- The canonical local developer workflow sequence (fix → format → type → test → full pre-commit).
- The import grouping policy we expect Ruff to enforce.
- The expectation that Ruff remains the single source of truth for both lint and formatting to reduce tool overlap and cognitive load.
- How operational guidance (Issue 0001) relates to architectural policy.

Without a recorded decision, future contributors (human or AI) could re-introduce parallel tools (e.g., add Black or isort) or diverge on ordering, generating noisy diffs and slower reviews.

## Decision

Adopt a unified lint + format governance policy centered on Ruff as the single style & lint tool.

Key elements:

1. Use Ruff for:
   - Style/lint rules (including import sorting and common error codes).
   - Source formatting (invoked via `ruff format`).
2. Canonical local workflow (documented in CONTRIBUTING and Issue 0001):
   1. `ruff check . --fix`
   2. `ruff format .`
   3. `mypy .`
   4. `pytest -q`
   5. `pre-commit run --all-files`
3. Import grouping policy (enforced by Ruff; contributors avoid manual reordering beyond obvious deletions):
   - Future imports
   - (Optional) module docstring (consistent placement relative to future import within file)
   - Standard library
   - Third-party packages
   - Local / relative modules
4. The issue document `docs/issues/0001-ruff-lint-guidelines.md` remains the operational, example-driven companion; this ADR is the normative policy.
5. Pre-commit hook order retains Ruff (lint) then Ruff format, followed by mypy, ADR index/lint, and tests (if configured) to surface fast, auto-fixable issues earliest.
6. Additional standalone formatters (Black), import sorters (isort), or overlapping Flake8-style tools will not be introduced unless this ADR is superseded.

## Consequences

Positive:
- Single tool reduces configuration fragmentation and speeds iteration.
- Fewer style-only diffs; consistency leads to lower review overhead.
- Clear contributor on-ramp: one mental model for style + lint operations.
- Automated fixes earlier in workflow reduce pre-commit churn.

Trade-offs / Neutral:
- Ruff's formatting opinions may occasionally diverge from Black; we accept this to avoid dual tool overhead.
- Some niche lint rules available in specialized plugins (e.g., flake8-* extensions) may require enabling equivalent Ruff rules or deferring until parity exists.

Risks / Mitigations:
- Risk: Ruff changes defaults in a future major version → Mitigation: pin versions via `pyproject.toml` and update ADR if policy shifts.
- Risk: Need for a rule Ruff does not yet support → Mitigation: open issue; only add a second tool after formal superseding ADR.

## Alternatives Considered

1. Black + isort + Flake8 stack (traditional Python trio) — rejected (multiple tools, slower feedback, config sprawl, redundant functionality that Ruff consolidates).
2. Keep policy implicit (no ADR) — rejected (increases drift risk; institutional knowledge non-durable).
3. Add a Makefile or task runner wrapper for the workflow — deferred (overhead not justified at current project size; pre-commit + docs sufficient).
4. Enforce formatting only in CI (allow local variation) — rejected (creates surprise diffs and slows merge loop).

## Future Work
- Periodic review of Ruff rule set to incrementally tighten (e.g., enabling additional performance or security rules once codebase grows).
- Consider an aggregated `./scripts/dev-check.sh` convenience wrapper if contributor friction rises.
- Evaluate adding structured lint metrics (counts of fixed vs. remaining issues) to CI badges if useful.
- Supersede this ADR if adopting a multi-language formatting solution that necessitates splitting Python tooling concerns.

## References
- Issue 0001 (operational guidance & troubleshooting narrative)
- ADR-0001 (dependency policy) — ensures Ruff dependency pinning consistency.
- ADR-0010 (AI curation policy) — this ADR supports reproducible, explainable automation.
- ADR-0012 (plugin registry) — context where friction emerged prompting formalization.
