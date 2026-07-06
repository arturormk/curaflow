from __future__ import annotations

from curaflow.plugins.sources.ods_table import _build_records_from_columns


def test_build_records_keeps_rows_when_trailing_cells_are_missing() -> None:
    """Rows missing trailing empty cells should still produce partial records."""
    rows = [
        ["key", "es", "targets[]"],
        [],
        ["zona-de-descanso", "Zona de descanso"],
        ["silla-de-ruedas", "Silla de ruedas"],
    ]

    data = _build_records_from_columns(
        rows,
        group_key="services",
        columns={"key": "key", "es": "es", "targets": "targets[]"},
    )

    assert data == {
        "extractions": {
            "services": [
                {"key": "zona-de-descanso", "es": "Zona de descanso"},
                {"key": "silla-de-ruedas", "es": "Silla de ruedas"},
            ]
        }
    }
