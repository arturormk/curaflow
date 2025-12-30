from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

from ...cli import APP_DIRS
from ...plugin_registry import target_plugin
from ...utils import ensure_dir, write_text_atomic


def _walk_path(obj: Any, path: str) -> Any:
    """Resolve a dotted path like "extractions.banners_items".

    If the path cannot be fully resolved, an empty list is returned so callers
    can treat it as "no items".
    """

    cur: Any = obj
    if not path:
        return cur
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return []
    return cur


def _load_yaml_source(dep: str) -> Any:
    p = APP_DIRS["sources"] / f"{dep}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"Source YAML for dependency '{dep}' not found at {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _normalise_base_dir(raw_base_dir: Any) -> Path:
    if isinstance(raw_base_dir, Path):
        base_dir = raw_base_dir
    else:
        base_dir = APP_DIRS["targets"] / str(raw_base_dir or "")
    ensure_dir(base_dir)
    return base_dir


def _run_command(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"media_convert: command failed: {' '.join(cmd)}") from exc


@target_plugin("media_convert")
def build_media_convert(name: str, deps: list[str], params: dict[str, object]) -> dict[str, Any]:
    if not deps:
        raise ValueError("media_convert target requires at least one dependency (the source list)")

    source_dep = deps[0]
    source_data = _load_yaml_source(source_dep)

    list_key = str(params.get("list_key") or "")
    items_raw = _walk_path(source_data, list_key)
    if not isinstance(items_raw, list):
        items: list[dict[str, Any]] = []
    else:
        items = [i for i in items_raw if isinstance(i, dict)]

    id_field = str(params.get("id_field") or "ID")
    image_source_tpl = str(params.get("image_source") or "")
    if not image_source_tpl:
        raise ValueError("media_convert requires 'image_source' parameter")

    name_template = str(params.get("name_template") or "{id}")

    width_param = params.get("width", 0)
    height_param = params.get("height", 0)

    width = int(width_param) if isinstance(width_param, int | str) else 0
    height = int(height_param) if isinstance(height_param, int | str) else 0
    if width <= 0 or height <= 0:
        raise ValueError("media_convert requires positive integer 'width' and 'height'")

    base_dir = _normalise_base_dir(params.get("base_dir", ""))

    converted_items: list[dict[str, Any]] = []

    for item in items:
        if id_field not in item:
            continue

        raw_id = item[id_field]
        id_str = str(raw_id)

        # Allow templates like "es_banner_image:{ID}" or "es_banner_image:{id}"
        fmt_mapping: dict[str, Any] = {k: v for k, v in item.items() if isinstance(k, str)}
        fmt_mapping.setdefault("id", raw_id)

        try:
            image_source_name = image_source_tpl.format(**fmt_mapping)
        except Exception as exc:
            raise ValueError(
                f"media_convert: failed to format image_source '{image_source_tpl}' "
                f"for item id={id_str}: {exc}"
            ) from exc

        try:
            base_name = name_template.format(**fmt_mapping)
        except Exception as exc:
            raise ValueError(
                f"media_convert: failed to format name_template '{name_template}' "
                f"for item id={id_str}: {exc}"
            ) from exc

        meta = _load_yaml_source(image_source_name)
        if not isinstance(meta, dict):
            continue

        content_type = str(meta.get("content_type") or "")
        raw_path_val = meta.get("raw_path")
        if not raw_path_val:
            continue

        if not content_type.startswith(("image/", "video/")):
            # Skip non-media entries silently; they are not relevant here.
            continue

        src_path = Path(str(raw_path_val))

        kind: str
        target_ext: str
        cmd: list[str]

        if content_type == "image/svg+xml":
            kind = "static"
            target_ext = ".png"
            target_path = base_dir / f"{base_name}{target_ext}"
            cmd = [
                "rsvg-convert",
                "-w",
                str(width),
                "-h",
                str(height),
                str(src_path),
                "-o",
                str(target_path),
            ]
        elif content_type.startswith("image/") and content_type != "image/gif":
            # Treat all non-GIF raster images as static images.
            kind = "static"
            target_ext = ".png"
            target_path = base_dir / f"{base_name}{target_ext}"
            geometry = f"{width}x{height}"
            cmd = [
                "convert",
                str(src_path),
                "-colorspace",
                "sRGB",
                "-resize",
                geometry,
                "-size",
                geometry,
                "xc:transparent",
                "+swap",
                "-gravity",
                "center",
                "-composite",
                "-colorspace",
                "sRGB",
                str(target_path),
            ]
        else:
            # Animated images (e.g. GIF) and all videos become MP4 clips.
            kind = "animated" if content_type.startswith("image/") else "video"
            target_ext = ".mp4"
            target_path = base_dir / f"{base_name}{target_ext}"
            cmd = [
                "ffmpeg",
                "-i",
                str(src_path),
                "-movflags",
                "faststart",
                "-pix_fmt",
                "yuv420p",
                "-vf",
                "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                str(target_path),
            ]

        # Per-item incremental behaviour: skip reconversion when the
        # converted file already exists and is newer than the raw input.
        if target_path.exists() and target_path.stat().st_mtime >= src_path.stat().st_mtime:
            # Keep the existing converted file; just record metadata.
            pass
        else:
            _run_command(cmd)

        converted_items.append(
            {
                "id": id_str,
                "name": base_name,
                "source": image_source_name,
                "content_type": content_type,
                "raw_path": str(src_path),
                "kind": kind,
                "output_path": str(target_path.relative_to(APP_DIRS["targets"])),
            }
        )

    summary_path = APP_DIRS["targets"] / f"{name}.json"
    previous = (
        json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
    )

    current = {
        "base_dir": str(base_dir.relative_to(APP_DIRS["targets"])),
        "width": width,
        "height": height,
        "count": len(converted_items),
        "items": converted_items,
    }

    write_text_atomic(summary_path, json.dumps(current, ensure_ascii=False, indent=2))

    return {"previous": previous, "current": current, "output_path": str(summary_path)}
