# 0001-packaging-and-dependency-policy
Status: Accepted
Date: 2025-09-13

## Context
Curaflow needs a reliable distribution mechanism and a clear policy for runtime vs development dependencies. Simplicity and minimal transitive risk are priorities.

## Decision
Use `pyproject.toml` with setuptools backend and static version field initially. Keep runtime dependencies minimal (httpx, PyYAML, typer, rich, beautifulsoup4, lxml, pyexcel-ods3). Avoid adding new runtime dependencies unless justified by a future ADR.

The original decision placed dev-only tools in `requirements-dev.txt`; ADR-0014 supersedes that portion by moving them to `[dependency-groups].dev` in `pyproject.toml`.

## Consequences
Positive:
- Predictable packaging flow.
- Clean separation of concerns.
- Low attack surface / maintenance overhead.

Negative / Trade-offs:
- Some functionality might need custom lightweight utilities over pulling heavier libs.

Follow-ups:
- Add version constant in package and consider single-sourcing later.
- Add dev requirements file.
- Add CI build step to verify artifacts.
