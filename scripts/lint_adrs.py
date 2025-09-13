#!/usr/bin/env python3
"""Lightweight ADR linter: checks required sections and status keyword.
Exit codes:
 0 OK
 1 Structural problems
"""

from __future__ import annotations

import pathlib
import re
import sys
from typing import Final

ADR_DIR: Final = pathlib.Path("docs/adr")
REQUIRED_SECTIONS: Final = ["## Context", "## Decision", "## Consequences"]
VALID_STATUS: Final = {"Proposed", "Accepted", "Superseded"}
FILENAME_RE = re.compile(r"^[0-9]{4}-[a-z0-9-]+\.md$")


def lint_file(p: pathlib.Path) -> list[str]:
    if p.name in {"TEMPLATE.md", "README.md"}:
        return []
    text = p.read_text(encoding="utf-8")
    errors: list[str] = []
    if not FILENAME_RE.match(p.name):
        errors.append("Filename must be NNNN-kebab-title.md")
    # Status
    m = re.search(r"^Status:\s*(.+)$", text, re.MULTILINE)
    if not m:
        errors.append("Missing Status line")
    else:
        st = m.group(1).strip()
        if st not in VALID_STATUS:
            errors.append(f"Invalid Status: {st}")
    for s in REQUIRED_SECTIONS:
        if s not in text:
            errors.append(f"Missing section: {s}")
    return errors


def main() -> None:
    any_err = False
    for p in sorted(ADR_DIR.glob("*.md")):
        errs = lint_file(p)
        if errs:
            any_err = True
            for e in errs:
                print(f"{p.name}: {e}")
    if any_err:
        sys.exit(1)
    print("ADRs lint clean")


if __name__ == "__main__":
    main()
