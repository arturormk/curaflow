from __future__ import annotations

import concurrent.futures
from collections import defaultdict, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .utils import newest_mtime

PluginName = Literal[
    "concat_json",
    "debug_print",
    "http_json",
    "http_html",
    "http_bytes",
    "http_xml",
]


@dataclass
class TargetSpec:
    name: str
    plugin: PluginName
    deps: list[str]
    params: dict[str, object] = field(default_factory=dict)


@dataclass
class SourceSpec:
    name: str
    plugin: PluginName
    params: dict[str, object]


def topo_sort(targets: dict[str, TargetSpec]) -> list[str]:
    indeg: dict[str, int] = defaultdict(int)
    adj: dict[str, list[str]] = defaultdict(list)
    nodes: set[str] = set(targets.keys())
    for t in targets.values():
        for d in t.deps:
            if d in nodes:
                adj[d].append(t.name)
                indeg[t.name] += 1
    q = deque([n for n in nodes if indeg[n] == 0])
    order: list[str] = []
    while q:
        n = q.popleft()
        order.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                q.append(m)
    if len(order) != len(nodes):
        raise RuntimeError("Cycle detected in target dependencies")
    return order


def needs_rebuild(outputs: Iterable[Path], dep_paths: Iterable[Path]) -> bool:
    newest_dep = newest_mtime(dep_paths)
    oldest_out = min((p.stat().st_mtime for p in outputs if p.exists()), default=0.0)
    if any(not p.exists() for p in outputs):
        return True
    return newest_dep > oldest_out


def run_parallel(func: Callable[[str], None], items: list[str], max_workers: int = 4) -> None:
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(func, it) for it in items]
        for f in futs:
            f.result()
