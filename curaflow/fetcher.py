from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any, Final, Protocol

import httpx
import yaml

from .utils import (
    add_extraction_indices,
    ensure_dir,
    sha256_bytes,
    sha256_obj,
    write_bytes_atomic,
    write_text_atomic,
)

META_DIR: Final = Path(".curaflow/meta")
SRC_DIR: Final = Path("data/sources")
RAW_DIR: Final = Path("data/raw")


class JsonFetcher(Protocol):
    async def __call__(
        self,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
        force: bool = False,
    ) -> tuple[bool, dict[str, Any] | None]: ...


class BytesFetcher(Protocol):
    async def __call__(
        self,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
        force: bool = False,
    ) -> tuple[bool, dict[str, Any] | None]: ...


class FetchMeta:
    def __init__(
        self, name: str, url: str, etag: str | None, last_modified: str | None, digest: str | None
    ):
        self.name = name
        self.url = url
        self.etag = etag
        self.last_modified = last_modified
        self.digest = digest

    @property
    def path(self) -> Path:
        return META_DIR / f"src_{self.name}.json"

    @classmethod
    def load(cls, name: str) -> FetchMeta | None:
        p = META_DIR / f"src_{name}.json"
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return cls(
            name=name,
            url=data["url"],
            etag=data.get("etag"),
            last_modified=data.get("last_modified"),
            digest=data.get("digest"),
        )

    def save(self) -> None:
        ensure_dir(META_DIR)
        write_text_atomic(
            self.path,
            json.dumps(
                {
                    "name": self.name,
                    "url": self.url,
                    "etag": self.etag,
                    "last_modified": self.last_modified,
                    "digest": self.digest,
                },
                indent=2,
            ),
        )


async def conditional_get(
    client: httpx.AsyncClient, url: str, etag: str | None, last_modified: str | None
) -> httpx.Response:
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return await client.get(url, headers=headers, follow_redirects=True, timeout=30.0)


JsonObj = dict[str, Any]


async def fetch_http_json(
    name: str,
    url: str,
    headers: dict[str, str] | None = None,
    force: bool = False,
) -> tuple[bool, JsonObj | None]:
    ensure_dir(SRC_DIR)
    meta = None if force else FetchMeta.load(name)
    async with httpx.AsyncClient(headers=headers or {}) as client:
        resp = await conditional_get(
            client, url, meta.etag if meta else None, meta.last_modified if meta else None
        )
    if resp.status_code == 304 and meta:
        prev = (
            yaml.safe_load((SRC_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
            if (SRC_DIR / f"{name}.yaml").exists()
            else None
        )
        return (False, prev)
    resp.raise_for_status()
    data = resp.json()

    # If the JSON payload already follows the normalized ``extractions``
    # convention, annotate its records with positional indices.
    add_extraction_indices(data)

    digest = sha256_obj(data)
    if meta and meta.digest == digest:
        FetchMeta(
            name=name,
            url=url,
            etag=resp.headers.get("ETag"),
            last_modified=resp.headers.get("Last-Modified"),
            digest=digest,
        ).save()
        prev = (
            yaml.safe_load((SRC_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
            if (SRC_DIR / f"{name}.yaml").exists()
            else None
        )
        return (False, prev)
    write_text_atomic(
        SRC_DIR / f"{name}.yaml", yaml.safe_dump(data, sort_keys=True, allow_unicode=True)
    )
    FetchMeta(
        name=name,
        url=url,
        etag=resp.headers.get("ETag"),
        last_modified=resp.headers.get("Last-Modified"),
        digest=digest,
    ).save()
    return (True, data)


async def fetch_http_bytes(
    name: str,
    url: str,
    headers: dict[str, str] | None = None,
    force: bool = False,
) -> tuple[bool, dict[str, Any] | None]:
    ensure_dir(SRC_DIR)
    ensure_dir(RAW_DIR)
    meta = None if force else FetchMeta.load(name)
    async with httpx.AsyncClient(headers=headers or {}) as client:
        resp = await conditional_get(
            client, url, meta.etag if meta else None, meta.last_modified if meta else None
        )
    if resp.status_code == 304 and meta:
        prev = (
            yaml.safe_load((SRC_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
            if (SRC_DIR / f"{name}.yaml").exists()
            else None
        )
        return (False, prev)
    resp.raise_for_status()
    content = resp.content
    digest = sha256_bytes(content)
    ctype = resp.headers.get(
        "Content-Type", mimetypes.guess_type(url)[0] or "application/octet-stream"
    )
    if meta and meta.digest == digest:
        FetchMeta(
            name=name,
            url=url,
            etag=resp.headers.get("ETag"),
            last_modified=resp.headers.get("Last-Modified"),
            digest=digest,
        ).save()
        prev = (
            yaml.safe_load((SRC_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
            if (SRC_DIR / f"{name}.yaml").exists()
            else None
        )
        return (False, prev)
    ext = mimetypes.guess_extension(ctype) or ""
    raw_path = RAW_DIR / f"{name}{ext}"
    write_bytes_atomic(raw_path, content)
    meta_yaml = {
        "url": url,
        "content_type": ctype,
        "bytes": len(content),
        "sha256": digest,
        "raw_path": str(raw_path),
        "headers": {
            k: v for k, v in resp.headers.items() if k.lower() in ("etag", "last-modified")
        },
    }
    write_text_atomic(
        SRC_DIR / f"{name}.yaml", yaml.safe_dump(meta_yaml, sort_keys=True, allow_unicode=True)
    )
    FetchMeta(
        name=name,
        url=url,
        etag=resp.headers.get("ETag"),
        last_modified=resp.headers.get("Last-Modified"),
        digest=digest,
    ).save()
    return (True, meta_yaml)
