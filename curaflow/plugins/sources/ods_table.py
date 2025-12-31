from __future__ import annotations

from typing import Any

import yaml
from pyexcel_ods3 import get_data

from ...cli import APP_DIRS
from ...plugin_registry import source_plugin
from ...utils import sha256_obj


def _load_sheet(path: str, sheet_name: str | None) -> list[list[Any]]:
    """Load rows from an ODS sheet using pyexcel-ods3.

    Returns a list-of-lists where the first row is expected to contain
    headers. If ``sheet_name`` is ``None``, the first sheet in the
    workbook is used.
    """

    # get_data returns: {sheet_name: [[cell, ...], ...], ...}
    book_raw = get_data(path)
    # Normalise to a plain dict[str, list[list[Any]]] to satisfy typing.
    book: dict[str, list[list[Any]]] = {str(k): list(v) for k, v in book_raw.items()}

    if sheet_name is None:
        # Take the first sheet by insertion order
        sheet_name = next(iter(book.keys()))
    return book[str(sheet_name)]


def _build_records_from_columns(
    rows: list[list[Any]], group_key: str, columns: dict[str, str]
) -> dict[str, Any]:
    """Build an extractions mapping from a column specification.

    ``columns`` maps YAML field names to ODS header titles.
    """

    if not rows:
        return {"extractions": {group_key: []}}

    headers = [str(c).strip() for c in rows[0]]

    # Map each YAML field name to its column index in the sheet
    indices: dict[str, int] = {}
    for field, header in columns.items():
        try:
            indices[field] = headers.index(header)
        except ValueError as exc:
            raise ValueError(
                f"ods_table: expected column '{header}' for field '{field}' "
                f"in sheet with headers {headers!r}"
            ) from exc

    max_idx = max(indices.values()) if indices else -1

    records: list[dict[str, Any]] = []
    for row in rows[1:]:
        if len(row) <= max_idx:
            continue
        rec: dict[str, Any] = {}
        for field, idx in indices.items():
            value = row[idx]
            # Normalise to string and trim whitespace; callers can choose
            # column names/types to suit their needs.
            text = "" if value is None else str(value).strip()
            if text:
                rec[field] = text
        if rec:
            records.append(rec)

    return {"extractions": {group_key: records}}


@source_plugin("ods_table")
async def fetch(
    name: str, params: dict[str, object]
) -> tuple[bool, dict[str, Any] | None, list[dict[str, Any]]]:
    """Read an ODS sheet and expose it as an ``extractions`` table.

    Schema:

      path: str          # ODS file path
      sheet: str         # sheet name (optional; first sheet if omitted)
      group_key: str     # key under ``extractions`` for the records list
      columns:           # mapping YAML field name -> ODS header title
        slug: "slug"
        polygon: "poly[]"
        brand: "marca"

    Produces a document shaped like::

      extractions:
        <group_key>:
          - {...record...}
    """

    path = str(params["path"])
    sheet_name = str(params.get("sheet", "")) or None

    group_key_param = params.get("group_key")
    columns_param = params.get("columns")

    if not isinstance(group_key_param, str) or not isinstance(columns_param, dict):
        raise ValueError("ods_table requires 'group_key' (str) and 'columns' (mapping)")

    group_key = group_key_param
    # Normalise keys/values to strings
    columns = {str(k): str(v) for k, v in columns_param.items()}
    rows = _load_sheet(path, sheet_name)
    data = _build_records_from_columns(rows, group_key, columns)

    # Compare against any existing YAML to support incremental fetches for
    # local ODS files. If the structured data hasn't changed, report
    # ``changed = False`` so downstream targets can skip rebuilds.
    src_path = APP_DIRS["sources"] / f"{name}.yaml"
    previous: dict[str, Any] | None = None
    if src_path.exists():
        try:
            previous = yaml.safe_load(src_path.read_text(encoding="utf-8"))
        except Exception:
            previous = None

    if previous is not None and sha256_obj(previous) == sha256_obj(data):
        return False, previous, []

    return True, data, []
