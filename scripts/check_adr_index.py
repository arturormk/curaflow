#!/usr/bin/env python3
"""Validate ADR index section in docs/adr/README.md.
Ensures each ADR file is listed in numeric order between markers.
"""

from __future__ import annotations

import pathlib
import re
import sys
from typing import Final

ADR_DIR: Final = pathlib.Path("docs/adr")
README: Final = ADR_DIR / "README.md"
BEGIN: Final = "<!-- ADR-INDEX:BEGIN -->"
END: Final = "<!-- ADR-INDEX:END -->"


def collect_adrs() -> list[tuple[str, str, str]]:
    entries = []
    for p in sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")):
        if p.name == "TEMPLATE.md":
            continue
        text = p.read_text(encoding="utf-8")
        m = re.search(r"^Status:\s*(.+)$", text, re.MULTILINE)
        status = m.group(1).strip() if m else "Unknown"
        num = p.name.split("-", 1)[0]
        slug = p.name.split("-", 1)[1].rsplit(".md", 1)[0]
        entries.append((num, slug, status))
    return entries


def build_index(entries: list[tuple[str, str, str]]) -> str:
    return "\n".join(f"- {num} - {slug} ({status})" for num, slug, status in entries)


def main() -> None:
    entries = collect_adrs()
    expected_index = build_index(entries)
    content = README.read_text(encoding="utf-8")
    if BEGIN not in content or END not in content:
        print("ADR index markers missing", file=sys.stderr)
        sys.exit(1)
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
    new_block = BEGIN + "\n" + expected_index + "\n" + END
    updated = pattern.sub(new_block, content)
    if updated != content:
        README.write_text(updated, encoding="utf-8")
        print("ADR index updated; please add this change to commit.")
        sys.exit(2)
    # Validate ordering monotonic
    nums = [e[0] for e in entries]
    if nums != sorted(nums):
        print("ADR numbers out of order", file=sys.stderr)
        sys.exit(3)
    print("ADR index OK")


if __name__ == "__main__":
    main()
