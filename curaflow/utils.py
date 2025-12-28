from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def sha256_obj(obj: Any) -> str:
    data = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return sha256_bytes(data)


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def newest_mtime(paths: Iterable[Path]) -> float:
    mtimes = [p.stat().st_mtime for p in paths if p.exists()]
    return max(mtimes) if mtimes else 0.0


def write_text_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_bytes_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def now_ts() -> float:
    return time.time()


def add_extraction_indices(obj: Any) -> None:
    """Annotate extraction records with a 1-based ``_index`` field.

    This walks a top-level ``extractions`` mapping, and for each value:
    - if it's a list, each dict item gets ``_index = position`` (1-based)
    - if it's a dict, each value dict also gets a positional ``_index``

    Existing ``_index`` values are preserved.
    """

    if not isinstance(obj, dict):
        return

    extractions = obj.get("extractions")
    if not isinstance(extractions, dict):
        return

    for group in extractions.values():
        # List of records
        if isinstance(group, list):
            for idx, rec in enumerate(group, start=1):
                if isinstance(rec, dict):
                    rec.setdefault("_index", idx)
        # Mapping of key -> record (e.g. already indexed by slug)
        elif isinstance(group, dict):
            for idx, rec in enumerate(group.values(), start=1):
                if isinstance(rec, dict):
                    rec.setdefault("_index", idx)
