from __future__ import annotations

from curaflow.html_utils import slugify


def test_slugify_basic_ascii() -> None:
    assert slugify("Hello World") == "hello-world"
    assert slugify("  multiple   spaces  ") == "multiple-spaces"


def test_slugify_diacritics_lowercase() -> None:
    # Accented vowels
    assert slugify("áéíóú") == "aeiou"
    assert slugify("àèìòù") == "aeiou"
    assert slugify("äëïöü") == "aeiou"
    # Spanish-specific characters
    assert slugify("ñ") == "n"
    assert slugify("ç") == "c"


def test_slugify_diacritics_uppercase_and_mixed() -> None:
    assert slugify("ÁÉÍÓÚ") == "aeiou"
    assert slugify("ÀÈÌÒÙ") == "aeiou"
    assert slugify("ÄËÏÖÜ") == "aeiou"
    assert slugify("Ñandú") == "nandu"
    assert slugify("ÇAÇÃ") == "caca"


def test_slugify_fallback_item() -> None:
    # When nothing survives, slugify should return a stable fallback
    assert slugify("") == "item"
    assert slugify("!!!") == "item"
