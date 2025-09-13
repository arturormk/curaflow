# Issue 0001: Document Ruff Lint & Format Workflow

Context: While introducing the plugin registry (ADR-0012) several pre-commit runs failed repeatedly due to Ruff complaints (import ordering I001, E402 import placement, and syntax errors caused by mis-indented `try` blocks after manual edits). Capturing the resolution steps here so future contributors (human or AI-assisted) converge faster.

## Symptoms Encountered
- I001: "Import block is un-sorted or un-formatted" across multiple plugin files after adding/removing imports.
- E402: "Module level import not at top of file" when code or docstrings appeared before imports in certain reorderings.
- Syntax errors in `plugin_registry.py` after editing the `try:` body (dedented lines left outside the block).
- Ruff format failing post-fix due to file not reformatted after changes.

## Root Causes
1. Manual import reordering omitted required blank lines between stdlib / third-party / local groups.
2. Mixing code (assignments) or misplaced docstring relative to `from __future__ import` caused E402.
3. Quick patch edits to `execute_source` lost indentation integrity inside `try` block.
4. Not re-running `pre-commit` after auto-fixes left staged content outdated.

## Canonical Resolution Workflow
```
ruff check . --fix      # auto-fix import order, simple lint issues
ruff format .           # apply code formatting
mypy .                  # type validation
pytest -q               # tests
pre-commit run --all-files  # final gate (includes ADR index & lint)
```
If a hook rewrites files:
```
git add .
pre-commit run --all-files
```

## Import Ordering Policy
Groups separated by one blank line in this order:
1. `from __future__ import annotations` (if used)
2. Module docstring (either before or after the future import—be consistent in a file)
3. Standard library imports
4. Third-party imports
5. Local/relative imports (`from .foo import Bar`, `from ..pkg import baz`)

Let Ruff handle ordering: `ruff check file.py --fix`.

## Try/Except Edit Tip
When adjusting code inside a `try` block, *never* dedent new lines inadvertently; run `python -m py_compile file.py` if unsure before committing.

## Pre-commit Hooks Snapshot (relevant)
- ruff (lint)
- ruff-format
- mypy
- adr-index / adr-lint

## Quick One-Liners
Format & lint full tree:
```
ruff check . --fix && ruff format .
```
Full gate:
```
ruff check . --fix && ruff format . && mypy . && pytest -q && pre-commit run --all-files
```

## Relation to ADR-0013
This issue captures the *operational troubleshooting narrative* that led to formalizing policy in ADR-0013 (Ruff unified lint & format governance). For normative rules, see ADR-0013; for practical, example-driven fixes and workflow quick references, use this document.

## References
- ADR-0001 (dependency policy)
- ADR-0010 (AI curation policy)
- ADR-0012 (plugin registry) — context where these issues surfaced.
