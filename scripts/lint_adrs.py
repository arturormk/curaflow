#!/usr/bin/env python3
"""Lightweight ADR linter: checks required sections and status keyword.
Exit codes:
 0 OK
 1 Structural problems
"""
from __future__ import annotations
import sys, pathlib, re

ADR_DIR = pathlib.Path('docs/adr')
REQUIRED_SECTIONS = ['## Context', '## Decision', '## Consequences']
VALID_STATUS = {'Proposed', 'Accepted', 'Superseded'}


def lint_file(p: pathlib.Path):
    text = p.read_text(encoding='utf-8')
    errors = []
    if p.name == 'TEMPLATE.md':
        return []
    if not p.name[0:4].isdigit():
        errors.append('Filename must start with 4 digits')
    # Status
    m = re.search(r'^Status:\s*(.+)$', text, re.MULTILINE)
    if not m:
        errors.append('Missing Status line')
    else:
        st = m.group(1).strip()
        if st not in VALID_STATUS:
            errors.append(f'Invalid Status: {st}')
    # Sections
    for s in REQUIRED_SECTIONS:
        if s not in text:
            errors.append(f'Missing section: {s}')
    return errors


def main():
    any_err = False
    for p in sorted(ADR_DIR.glob('*.md')):
        errs = lint_file(p)
        if errs:
            any_err = True
            for e in errs:
                print(f'{p.name}: {e}')
    if any_err:
        sys.exit(1)
    print('ADRs lint clean')

if __name__ == '__main__':
    main()
