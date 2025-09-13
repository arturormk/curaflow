from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
import yaml, typer
from rich import print as rprint
from rich.table import Table

from .fetcher import fetch_http_json, fetch_http_bytes, SRC_DIR
from .diffing import deep_diff
from .dag import topo_sort, needs_rebuild, TargetSpec, SourceSpec
from .utils import ensure_dir, write_text_atomic

APP_DIRS = {
    "meta": Path(".curaflow/meta"),
    "diffs": Path(".curaflow/diffs"),
    "sources": Path("data/sources"),
    "targets": Path("data/targets"),
}

app = typer.Typer(help="Curaflow: incremental fetch→normalize→build pipeline (with hierarchical fanout).")

def load_manifest(manifest: Path) -> Tuple[Dict[str, SourceSpec], Dict[str, TargetSpec]]:
    m = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    sources: Dict[str, SourceSpec] = {}
    targets: Dict[str, TargetSpec] = {}
    for s in m.get("sources", []):
        sources[s["name"]] = SourceSpec(name=s["name"], plugin=s["plugin"], params=s.get("params", {}))
    for t in m.get("targets", []):
        targets[t["name"]] = TargetSpec(name=t["name"], plugin=t["plugin"], deps=t.get("deps", []), params=t.get("params", {}))
    return sources, targets

def ensure_base_dirs():
    for p in APP_DIRS.values():
        p.mkdir(parents=True, exist_ok=True)

@app.command()
def plan(manifest: Path = typer.Option(..., "-m", help="Path to manifest.yaml")):
    sources, targets = load_manifest(manifest)
    rprint("[bold]Sources[/bold]")
    for s in sources.values():
        rprint(f"  - {s.name} [{s.plugin}]")
    rprint("[bold]\nTargets[/bold]")
    for t in targets.values():
        rprint(f"  - {t.name} [{t.plugin}] deps={t.deps}")

@app.command()
def fetch(manifest: Path = typer.Option(..., "-m", help="Path to manifest.yaml")):
    """Fetch/normalize all sources (skips if unchanged), including dynamically fanned-out children."""
    ensure_base_dirs()
    sources, _ = load_manifest(manifest)

    # Load previously discovered dynamic sources
    dyn_path = APP_DIRS["meta"] / "sources_dynamic.json"
    dynamic_sources = {}
    if dyn_path.exists():
        try:
            dynamic_sources = {s["name"]: s for s in json.loads(dyn_path.read_text(encoding="utf-8"))}
        except Exception:
            dynamic_sources = {}

    # Work queue
    queue: Dict[str, Dict[str, Any]] = {}
    for s in sources.values():
        queue[s.name] = {"name": s.name, "plugin": s.plugin, "params": s.params}
    for s in dynamic_sources.values():
        queue.setdefault(s["name"], s)

    processed: set[str] = set()
    changed_any = False

    def enqueue_children(children: List[dict]):
        for ch in children:
            nm = ch["name"]
            if nm not in queue and nm not in processed:
                queue[nm] = ch
                dynamic_sources[nm] = ch

    while True:
        next_item = None
        for nm, spec in queue.items():
            if nm not in processed:
                next_item = spec; break
        if not next_item:
            break

        name = next_item["name"]; plugin = next_item["plugin"]; params = next_item.get("params", {})
        children: List[dict] = []
        if plugin == "http_json":
            url = params["url"]; headers = params.get("headers")
            changed, _obj = typer.run_async(fetch_http_json(name, url, headers))
            if changed:
                rprint(f"[green]updated[/green] {name} -> data/sources/{name}.yaml")
                changed_any = True
            else:
                rprint(f"[dim]unchanged[/dim] {name}")
        elif plugin == "http_html":
            from .plugins.sources.http_html import fetch as html_fetch
            changed, _obj, children = typer.run_async(html_fetch(name, params))
            if changed:
                rprint(f"[green]updated[/green] {name} -> data/sources/{name}.yaml  (+{len(children)} children)")
                changed_any = True
            else:
                rprint(f"[dim]unchanged[/dim] {name}")
        elif plugin == "http_bytes":
            url = params["url"]; headers = params.get("headers")
            changed, _meta = typer.run_async(fetch_http_bytes(name, url, headers))
            if changed:
                rprint(f"[green]updated[/green] {name} -> data/sources/{name}.yaml (binary)")
                changed_any = True
            else:
                rprint(f"[dim]unchanged[/dim] {name}")
        else:
            rprint(f"[yellow]SKIP[/yellow] {name}: plugin {plugin} not implemented")

        if children:
            enqueue_children(children)
        processed.add(name)

    # Persist dynamic registry
    if dynamic_sources:
        APP_DIRS["meta"].mkdir(parents=True, exist_ok=True)
        write_text_atomic(dyn_path, json.dumps(list(dynamic_sources.values()), indent=2))

    if changed_any:
        rprint("[bold green]Some sources changed[/bold green]")
    else:
        rprint("[bold dim]No source changed[/bold dim]")

def _load_yaml(p: Path):
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else None

def _write_json(p: Path, obj: Any) -> None:
    write_text_atomic(p, json.dumps(obj, ensure_ascii=False, indent=2))

@app.command()
def build(manifest: Path = typer.Option(..., "-m", help="Path to manifest.yaml")):
    ensure_base_dirs()
    sources, targets = load_manifest(manifest)

    source_paths = {name: APP_DIRS["sources"] / f"{name}.yaml" for name in sources.keys()}

    # Include dynamic sources in dep resolution (they are sources too)
    dyn_path = APP_DIRS["meta"] / "sources_dynamic.json"
    if dyn_path.exists():
        for s in json.loads(dyn_path.read_text(encoding="utf-8")):
            source_paths[s["name"]] = APP_DIRS["sources"] / f"{s['name']}.yaml"

    order = topo_sort(targets)
    built_any = False

    for tname in order:
        spec = targets[tname]
        dep_paths: List[Path] = []
        for d in spec.deps:
            if d in source_paths:
                dep_paths.append(source_paths[d])
            else:
                dep_paths.append(APP_DIRS["targets"] / f"{d}.json")
        outputs = [APP_DIRS["targets"] / f"{tname}.json"]

        if not needs_rebuild(outputs, dep_paths):
            rprint(f"[dim]up-to-date[/dim] {tname}")
            continue

        if spec.plugin == "concat_json":
            merged: Dict[str, Any] = {}
            for d in spec.deps:
                p = source_paths.get(d, APP_DIRS["targets"] / f"{d}.json")
                obj = _load_yaml(p) if p.suffix == ".yaml" else json.loads(p.read_text(encoding="utf-8"))
                merged[d] = obj
            outp = outputs[0]
            prev = json.loads(outp.read_text(encoding="utf-8")) if outp.exists() else None
            _write_json(outp, merged); built_any = True
            changes = deep_diff(prev, merged) if prev is not None else [f"/: created {tname}"]
            if changes:
                (APP_DIRS["diffs"] / f"{tname}.diff.txt").write_text("\n".join(changes), encoding="utf-8")
                rprint(f"[green]built[/green] {tname} -> {outp}  ([bold]{len(changes)}[/bold] change lines)")
            else:
                rprint(f"[green]built[/green] {tname} -> {outp}  (no structural changes)")
        else:
            rprint(f"[yellow]SKIP[/yellow] {tname}: plugin {spec.plugin} not implemented")

    if built_any: rprint("[bold green]Some targets rebuilt[/bold green]")
    else: rprint("[bold dim]No target rebuilt[/bold dim]")

@app.command()
def status(manifest: Path = typer.Option(..., "-m", help="Path to manifest.yaml")):
    sources, targets = load_manifest(manifest)

    tbl = Table(title="Sources", show_lines=False)
    tbl.add_column("name"); tbl.add_column("path"); tbl.add_column("exists")
    source_paths = {n: APP_DIRS["sources"] / f"{n}.yaml" for n in sources.keys()}

    # dynamic sources too
    dyn_path = APP_DIRS["meta"] / "sources_dynamic.json"
    if dyn_path.exists():
        for s in json.loads(dyn_path.read_text(encoding="utf-8")):
            source_paths[s["name"]] = APP_DIRS["sources"] / f"{s['name']}.yaml"

    for name, p in sorted(source_paths.items()):
        tbl.add_row(name, str(p), "yes" if p.exists() else "no")
    rprint(tbl)

    tbl2 = Table(title="Targets", show_lines=False)
    tbl2.add_column("name"); tbl2.add_column("path"); tbl2.add_column("needs rebuild?")
    for t in targets.values():
        outp = APP_DIRS["targets"] / f"{t.name}.json"
        dep_paths = []
        for d in t.deps:
            dep_paths.append(source_paths.get(d, APP_DIRS["targets"] / f"{d}.json"))
        tbl2.add_row(t.name, str(outp), "yes" if needs_rebuild([outp], dep_paths) else "no")
    rprint(tbl2)

@app.command()
def diff(artifact: str = typer.Argument(..., help="Prefix 'sources:' or 'targets:' + name")):
    kind, name = artifact.split(":", 1)
    if kind == "targets":
        p = APP_DIRS["diffs"] / f"{name}.diff.txt"
        if not p.exists():
            rprint(f"[dim]No diff recorded for target {name}[/dim]"); raise typer.Exit(code=0)
        print(p.read_text(encoding="utf-8"))
    elif kind == "sources":
        p = APP_DIRS["sources"] / f"{name}.yaml"
        if not p.exists():
            rprint(f"[red]No such source {name}[/red]"); raise typer.Exit(code=1)
        print(p.read_text(encoding="utf-8"))
    else:
        rprint("Use 'sources:NAME' or 'targets:NAME'.")

if __name__ == "__main__":
    app()
