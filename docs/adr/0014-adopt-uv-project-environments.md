# 0014: Adopt uv project environments

Status: Accepted

## Context

Curaflow already has a committed `uv.lock`, but local setup, release
instructions, and CI still use manual virtual environments and pip. Dev-only
tools also live in `requirements-dev.txt`, which leaves the lockfile covering
runtime dependencies but not the full contributor environment.

## Decision

Adopt uv as the project environment and lockfile manager.

Key elements:

1. Keep runtime dependencies in `[project.dependencies]` so package metadata
   remains standard and publishable.
2. Move development tools to the standardized `[dependency-groups].dev` table in
   `pyproject.toml`.
3. Commit `uv.lock` as the lockfile for local development and CI.
4. Use `uv sync` for environment setup, `uv run` for commands inside the
   environment, and `uv build` for source and wheel distributions.
5. Remove `requirements-dev.txt` after its contents are represented in
   `pyproject.toml`.

## Consequences

Positive:
- Local and CI environments use the same dependency source of truth.
- Contributors no longer need to manually create or activate `.venv`.
- Dev tools are resolved and locked alongside runtime dependencies.

Trade-offs / Neutral:
- Contributors need uv installed locally.
- Pip-only setup is no longer the documented development path.

Risks / Mitigations:
- Risk: uv CLI behavior changes over time → Mitigation: CI installs uv through
  the official setup action and lock consistency is checked with uv.
- Risk: Some tooling assumes activated environments → Mitigation: document
  `uv run` as the canonical invocation pattern.

## Alternatives Considered

1. Keep pip plus `requirements-dev.txt` — rejected because it leaves the
   committed lockfile incomplete for development.
2. Only update README setup commands — rejected because CI and dependency
   metadata would continue to drift from local development.
3. Use a tool-specific legacy uv dev-dependencies table — rejected in favor of
   standardized dependency groups.

## References

- ADR-0001 (packaging and dependency policy) — supersedes the
  `requirements-dev.txt` portion while preserving runtime dependency policy.
- ADR-0013 (Ruff workflow) — local command examples now run through uv.
