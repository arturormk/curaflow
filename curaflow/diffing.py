from __future__ import annotations
from typing import Any, List

def deep_diff(a: Any, b: Any, path: str = "") -> List[str]:
    changes: List[str] = []
    if type(a) is not type(b):
        changes.append(f"{path or '/'}: type {type(a).__name__} -> {type(b).__name__}")
        return changes
    if isinstance(a, dict):
        keys = set(a.keys()) | set(b.keys())
        for k in sorted(keys):
            p = f"{path}/{k}" if path else f"/{k}"
            if k not in a:
                changes.append(f"{p}: +added: {repr(b[k])[:80]}")
            elif k not in b:
                changes.append(f"{p}: -removed: {repr(a[k])[:80]}")
            else:
                changes.extend(deep_diff(a[k], b[k], p))
    elif isinstance(a, list):
        if a != b:
            changes.append(f"{path or '/'}: list changed len {len(a)} -> {len(b)}")
    else:
        if a != b:
            changes.append(f"{path or '/'}: {repr(a)[:80]} -> {repr(b)[:80]}")
    return changes
