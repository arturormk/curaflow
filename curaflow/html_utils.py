from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


_slug_re = re.compile(r"[^a-z0-9]+")


def _strip_diacritics(text: str) -> str:
    """Normalize accented characters to their base ASCII forms.

    Uses NFKD decomposition and drops combining marks so characters like
    "áéíóú àèìòù äëïöü ñ ç" (and their uppercase variants) map to
    "aeiou aeiou aeiou n c" before slug generation.
    """

    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def slugify(s: str) -> str:
    # Normalize whitespace and accents before slug generation
    s = _strip_diacritics(s.strip()).lower()
    s = _slug_re.sub("-", s).strip("-")
    return s or "item"
