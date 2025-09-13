# Contributing to Curaflow

Thank you for considering a contribution!

## Workflow
1. Open an issue (feature, bug, or ADR proposal).
2. For architectural/process changes: draft or update an ADR in `docs/adr/`.
3. Create a branch; write (or update) tests first for behavioral changes.
4. Run pre-commit: `pre-commit run --all-files`.
5. Ensure CI passes (lint, type, test, build, ADR lint).

## Standards
- Reference ADR IDs in commit messages when relevant (e.g., `refs ADR-0002`).
- Keep runtime dependencies minimal (see ADR-0001).
- Include provenance: large AI-assisted changes may add `Curated-By:` footer.

## Tests
Fast subset: `bash scripts/fast_tests.sh`
Full: `pytest -q`

## Attribution & AI Usage
See ADR-0010 and README Attribution section. AI suggestions are drafts; human reviewers ensure intent alignment.

## Code Style
- Ruff enforces lint + formatting
- Type annotations required for new public functions
- Avoid large binary fixtures in repo

## Releasing
Follow semantic versioning. Tag `vX.Y.Z` after green CI.
