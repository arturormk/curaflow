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

### Lint & Formatting Guidelines
The project uses Ruff for *both* linting (`ruff check`) and code formatting (`ruff format`). To minimize iteration cycles:

Recommended local loop:
```
ruff check . --fix
ruff format .
mypy .
pytest -q
```

Key Ruff expectations that previously caused friction:
1. Import order (I001): groups separated by single blank lines in this order:
	- `__future__` imports (if any)
	- Module docstring (can appear before or after `from __future__ import`—be consistent)
	- Standard library
	- Third-party
	- Local/relative (`from .foo import Bar`)
2. E402 (module level import not at top): Only the module docstring and `from __future__ import` may precede imports. Avoid executable code (including variable assignments) before imports.
3. After editing a `try:` block, ensure the indented body stays within the block—dedenting a line by accident will surface as a syntax error during pre-commit (was a source of repeated failures while refining `plugin_registry.execute_source`).
4. Let Ruff fix imports instead of hand-tweaking: `ruff check file.py --fix`.
5. Always run `pre-commit run --all-files` once right before committing; hooks may rewrite files—stage again if they do.

Common one-liner (will auto-fix where possible):
```
pre-commit run --all-files || (git add . && pre-commit run --all-files)
```

If a hook fails due to formatting only, run format then re-run the hook:
```
ruff format . && pre-commit run ruff-format --all-files
```

Philosophy: We keep style automation strict so PR diffs focus on intent, not whitespace or ordering.

## Releasing
Follow semantic versioning. Tag `vX.Y.Z` after green CI.
