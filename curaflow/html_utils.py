from __future__ import annotations

import re

from bs4 import BeautifulSoup


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = _slug_re.sub("-", s).strip("-")
    return s or "item"
