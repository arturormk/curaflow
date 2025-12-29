from __future__ import annotations

from pathlib import Path
from typing import Any

import curaflow.cli as cli


def _override_app_dirs(tmp_path: Path) -> dict[str, Path]:
    """Point APP_DIRS to a temporary workspace, returning the previous mapping."""
    old = {k: v for k, v in cli.APP_DIRS.items()}
    cli.APP_DIRS.update(
        {
            "meta": tmp_path / ".curaflow/meta",
            "diffs": tmp_path / ".curaflow/diffs",
            "sources": tmp_path / "data/sources",
            "targets": tmp_path / "data/targets",
        }
    )
    return old


def _restore_app_dirs(old: dict[str, Path]) -> None:
    cli.APP_DIRS.update(old)


def test_cli_table_basic(tmp_path: Path, capsys: Any) -> None:
    """Basic smoke test for the `table` command.

    Creates a simple YAML source with two records and checks that the
    command runs successfully and emits expected column names.
    """

    old_app_dirs = _override_app_dirs(tmp_path)
    try:
        sources_dir = cli.APP_DIRS["sources"]
        sources_dir.mkdir(parents=True, exist_ok=True)

        yaml_path = sources_dir / "shops.yaml"
        yaml_path.write_text(
            """
- codigo: 2
  slug: b
  marca: B
- codigo: 1
  slug: a
  marca: A
""".lstrip(),
            encoding="utf-8",
        )

        # Call the command function directly so the overridden APP_DIRS
        # mapping is used within this process.
        cli.table(
            source="shops",
            list_key="",
            columns=["codigo,slug,marca"],
            sort=["+codigo"],
        )

        captured = capsys.readouterr()
        # Column headers should appear in the textual table output
        assert "codigo" in captured.out
        assert "slug" in captured.out
        assert "marca" in captured.out
    finally:
        _restore_app_dirs(old_app_dirs)


def test_cli_table_natural_sort(tmp_path: Path, capsys: Any) -> None:
    """Values with embedded numbers are sorted naturally (1, 2, 10)."""

    old_app_dirs = _override_app_dirs(tmp_path)
    try:
        sources_dir = cli.APP_DIRS["sources"]
        sources_dir.mkdir(parents=True, exist_ok=True)

        yaml_path = sources_dir / "nums.yaml"
        yaml_path.write_text(
            """
- codigo: "2"
- codigo: "10"
- codigo: "1"
""".lstrip(),
            encoding="utf-8",
        )

        cli.table(
            source="nums",
            list_key="",
            columns=["codigo"],
            sort=["+codigo"],
        )

        out = capsys.readouterr().out
        # Ensure natural ordering: 1, 2, 10
        pos_1 = out.find("1")
        pos_2 = out.find("2")
        pos_10 = out.find("10")
        assert -1 not in (pos_1, pos_2, pos_10)
        assert pos_1 < pos_2 < pos_10
    finally:
        _restore_app_dirs(old_app_dirs)
