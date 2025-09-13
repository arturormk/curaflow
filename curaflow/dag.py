from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Callable, Iterable
from collections import defaultdict, deque
import concurrent.futures
from .utils import newest_mtime

@dataclass
class TargetSpec:
    name: str
    plugin: str
    deps: List[str]
    params: dict = field(default_factory=dict)

@dataclass
class SourceSpec:
    name: str
    plugin: str
    params: dict

def topo_sort(targets: Dict[str, TargetSpec]) -> List[str]:
    indeg: Dict[str, int] = defaultdict(int)
    adj: Dict[str, List[str]] = defaultdict(list)
    nodes: Set[str] = set(targets.keys())
    for t in targets.values():
        for d in t.deps:
            if d in nodes:
                adj[d].append(t.name)
                indeg[t.name] += 1
    q = deque([n for n in nodes if indeg[n] == 0])
    order: List[str] = []
    while q:
        n = q.popleft(); order.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0: q.append(m)
    if len(order) != len(nodes): raise RuntimeError("Cycle detected in target dependencies")
    return order

def needs_rebuild(outputs: Iterable[Path], dep_paths: Iterable[Path]) -> bool:
    newest_dep = newest_mtime(dep_paths)
    oldest_out = min((p.stat().st_mtime for p in outputs if p.exists()), default=0.0)
    if any(not p.exists() for p in outputs): return True
    return newest_dep > oldest_out

def run_parallel(func: Callable[[str], None], items: List[str], max_workers: int = 4) -> None:
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(func, it) for it in items]
        for f in futs: f.result()
