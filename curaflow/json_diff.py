#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Failed to parse JSON from {path}: {exc}") from exc


def find_latest_snapshot(history_dir: Path, source_path: Path) -> Path | None:
    """Return the most recent history snapshot matching *-<source_name>.json.

    Snapshots are expected to be named like ``yyyymmdd-hhmm-<source-name>.json``.
    We simply sort lexicographically and pick the last one.
    """

    pattern = f"*-{source_path.name}"
    candidates = sorted(history_dir.glob(pattern))
    if not candidates:
        return None
    return candidates[-1]


def normalise_items(obj: Any) -> list[dict[str, Any]]:
    items = obj.get("items") if isinstance(obj, dict) else None
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


def canonicalise(item: dict[str, Any]) -> str:
    """Stable string representation for set operations on dict items."""

    return json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def pretty(item: dict[str, Any]) -> str:
    return json.dumps(item, sort_keys=True, ensure_ascii=False, indent=2)


def diff_items(
    prev_items: Iterable[dict[str, Any]], cur_items: Iterable[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    prev_map = {canonicalise(it): it for it in prev_items}
    cur_map = {canonicalise(it): it for it in cur_items}

    prev_keys = set(prev_map.keys())
    cur_keys = set(cur_map.keys())

    only_prev_keys = sorted(prev_keys - cur_keys)
    only_cur_keys = sorted(cur_keys - prev_keys)
    common_keys = prev_keys & cur_keys

    return (
        [prev_map[k] for k in only_prev_keys],
        [cur_map[k] for k in only_cur_keys],
        len(common_keys),
    )


def write_report(
    out_path: Path,
    source_path: Path,
    prev_path: Path,
    only_prev: list[dict[str, Any]],
    only_cur: list[dict[str, Any]],
    common_count: int,
) -> None:
    with out_path.open("w", encoding="utf-8") as f:
        lines: list[str] = []
        lines.append(f"Previous snapshot: {prev_path}")
        lines.append(f"Latest snapshot:   {source_path}")
        lines.append("")

        lines.append("Summary:")
        lines.append(f"  unchanged items:      {common_count}")
        lines.append(f"  only in previous:     {len(only_prev)}")
        lines.append(f"  only in latest:       {len(only_cur)}")
        lines.append("")

        if only_prev:
            lines.append("Only in previous (removed or changed):")
            for idx, item in enumerate(only_prev, 1):
                lines.append(f"- #{idx}")
                lines.append(pretty(item))
            lines.append("")

        if only_cur:
            lines.append("Only in latest (added or changed):")
            for idx, item in enumerate(only_cur, 1):
                lines.append(f"- #{idx}")
                lines.append(pretty(item))
            lines.append("")

        f.write("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diff JSON items against latest history snapshot")
    parser.add_argument(
        "source_json", help="Current JSON file (e.g. data/targets/watch_stores.json)"
    )
    parser.add_argument(
        "--history", required=True, help="Directory containing historical JSON snapshots"
    )
    parser.add_argument("--output", required=True, help="Path to write human-readable diff report")

    args = parser.parse_args(argv)

    source_path = Path(args.source_json)
    history_dir = Path(args.history)
    out_path = Path(args.output)

    if not source_path.is_file():
        sys.stderr.write(f"json-diff: source JSON not found: {source_path}\n")
        return 1

    if history_dir.exists() and not history_dir.is_dir():
        sys.stderr.write(
            "json-diff: history path exists and is not a directory: " f"{history_dir}\n"
        )
        return 1

    # Ensure history directory exists so we can create snapshots.
    history_dir.mkdir(parents=True, exist_ok=True)

    prev_path = find_latest_snapshot(history_dir, source_path)
    if prev_path is None:
        # No previous snapshot: create an initial snapshot and do not emit a
        # diff report. This establishes a baseline without triggering a
        # "changes" notification on first run.
        ts = datetime.now().strftime("%Y%m%d-%H%M")
        snap_path = history_dir / f"{ts}-{source_path.stem}.json"
        shutil.copy2(source_path, snap_path)
        return 0

    try:
        prev_obj = load_json(prev_path)
        cur_obj = load_json(source_path)
    except Exception as exc:
        sys.stderr.write(f"json-diff: {exc}\n")
        return 1

    prev_items = normalise_items(prev_obj)
    cur_items = normalise_items(cur_obj)

    only_prev, only_cur, common_count = diff_items(prev_items, cur_items)

    if not only_prev and not only_cur:
        # No differences; do not create the output file or a new snapshot.
        return 0

    # Ensure parent dir exists for the report
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_report(out_path, source_path, prev_path, only_prev, only_cur, common_count)

    # On real changes, append a new snapshot to the history so future runs
    # diff against the latest state.
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    snap_path = history_dir / f"{ts}-{source_path.stem}.json"
    shutil.copy2(source_path, snap_path)
    return 0


if __name__ == "__main__":  # pragma: no cover - script entrypoint
    raise SystemExit(main())
