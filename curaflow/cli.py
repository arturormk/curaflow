from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any, Final, TypedDict

import typer
import yaml
from rich import print as rprint
from rich.table import Table

# Import plugins to register them
from . import plugins  # noqa: F401
from .dag import PluginName, SourceSpec, TargetSpec, needs_rebuild, topo_sort
from .diffing import deep_diff
from .fetcher import fetch_http_bytes, fetch_http_json
from .plugin_registry import execute_source, execute_target, get_source, get_target
from .utils import write_text_atomic


class ManifestSource(TypedDict, total=False):
    name: str
    plugin: PluginName
    params: dict[str, object]


class ManifestTarget(TypedDict, total=False):
    name: str
    plugin: PluginName
    deps: list[str]
    params: dict[str, object]


APP_DIRS: Final = {
    "meta": Path(".curaflow/meta"),
    "diffs": Path(".curaflow/diffs"),
    "sources": Path("data/sources"),
    "targets": Path("data/targets"),
}

app = typer.Typer(
    help="Curaflow: incremental fetch→normalize→build pipeline (with hierarchical fanout)."
)

ManifestPath = Annotated[Path, typer.Option("-m", help="Path to manifest.yaml")]


def load_manifest(manifest: Path) -> tuple[dict[str, SourceSpec], dict[str, TargetSpec]]:
    m = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    sources: dict[str, SourceSpec] = {}
    targets: dict[str, TargetSpec] = {}
    for s in m.get("sources", []):
        sources[s["name"]] = SourceSpec(
            name=s["name"], plugin=s["plugin"], params=s.get("params", {})
        )
    for t in m.get("targets", []):
        targets[t["name"]] = TargetSpec(
            name=t["name"], plugin=t["plugin"], deps=t.get("deps", []), params=t.get("params", {})
        )
    return sources, targets


def ensure_base_dirs() -> None:
    for p in APP_DIRS.values():
        p.mkdir(parents=True, exist_ok=True)


@app.command()
def plan(manifest: ManifestPath) -> None:
    sources, targets = load_manifest(manifest)
    rprint("[bold]Sources[/bold]")
    for s in sources.values():
        rprint(f"  - {s.name} [{s.plugin}]")
    rprint("[bold]\nTargets[/bold]")
    for t in targets.values():
        rprint(f"  - {t.name} [{t.plugin}] deps={t.deps}")


@app.command()
def fetch(
    manifest: ManifestPath,
    max_concurrent: int = typer.Option(10, help="Maximum concurrent fetches"),
) -> None:
    """Fetch/normalize all sources (skips if unchanged), including dynamically fanned-out children."""
    ensure_base_dirs()
    sources, _ = load_manifest(manifest)

    # Run the async fetch function
    changed_any = asyncio.run(_fetch_parallel(sources, max_concurrent))

    if changed_any:
        rprint("[bold green]Some sources changed[/bold green]")
    else:
        rprint("[bold dim]No source changed[/bold dim]")


async def _fetch_parallel(sources: dict[str, SourceSpec], max_concurrent: int) -> bool:
    """Parallel fetch implementation with concurrency control."""
    # Load previously discovered dynamic sources
    dyn_path = APP_DIRS["meta"] / "sources_dynamic.json"
    dynamic_sources: dict[str, dict[str, Any]] = {}
    if dyn_path.exists():
        try:
            dynamic_sources = {
                s["name"]: s for s in json.loads(dyn_path.read_text(encoding="utf-8"))
            }
        except Exception:
            dynamic_sources = {}

    # Initialize queue with manifest sources and dynamic sources
    queue: dict[str, dict[str, Any]] = {}
    for src in sources.values():
        queue[src.name] = {"name": src.name, "plugin": src.plugin, "params": src.params}
    for dyn in dynamic_sources.values():
        queue.setdefault(dyn["name"], dyn)

    processed: set[str] = set()
    changed_any = False
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _fetch_single(spec: dict[str, Any]) -> tuple[str, bool, list[dict[str, Any]]]:
        """Fetch a single source with concurrency control."""
        async with semaphore:
            name = spec["name"]
            plugin = spec["plugin"]
            params = spec.get("params", {})

            try:
                # Built-in legacy plugins not yet migrated to registry (http_json, http_bytes)
                if plugin == "http_json":
                    url = params["url"]
                    headers = params.get("headers")
                    changed, _obj = await fetch_http_json(name, url, headers)
                    if changed:
                        rprint(f"[green]updated[/green] {name} -> data/sources/{name}.yaml")
                    else:
                        rprint(f"[dim]unchanged[/dim] {name}")
                    return name, changed, []

                elif plugin == "http_bytes":
                    url = params["url"]
                    headers = params.get("headers")
                    changed, _meta = await fetch_http_bytes(name, url, headers)
                    if changed:
                        rprint(
                            f"[green]updated[/green] {name} -> data/sources/{name}.yaml (binary)"
                        )
                    else:
                        rprint(f"[dim]unchanged[/dim] {name}")
                    return name, changed, []

                else:
                    # registry-based plugin
                    try:
                        get_source(plugin)
                    except Exception:
                        rprint(f"[yellow]SKIP[/yellow] {name}: plugin {plugin} not registered")
                        return name, False, []

                    res = await execute_source(plugin, {**params, "name": name})
                    if "error" in res:
                        rprint(
                            f"[red]error[/red] {name} ({plugin}) -> {res['error'].splitlines()[-1]}"
                        )
                        return name, False, []
                    else:
                        changed = res.get("changed", False)
                        children = res.get("children", []) or []
                        if changed:
                            child_count = len(children)
                            suffix = f"  (+{child_count} children)" if child_count else ""
                            rprint(
                                f"[green]updated[/green] {name} -> data/sources/{name}.yaml{suffix}"
                            )
                        else:
                            rprint(f"[dim]unchanged[/dim] {name}")
                        return name, changed, children

            except Exception as e:
                rprint(f"[red]error[/red] {name} ({plugin}) -> {e!s}")
                return name, False, []

    # Process sources in waves to handle hierarchical fanout
    while queue:
        # Get all sources that are ready to process (not processed yet)
        ready_sources = [spec for name, spec in queue.items() if name not in processed]

        if not ready_sources:
            break

        # Process batch of sources concurrently
        tasks = [_fetch_single(spec) for spec in ready_sources]
        results = await asyncio.gather(*tasks)

        # Process results and collect new children
        for name, changed, children in results:
            processed.add(name)
            if changed:
                changed_any = True

            # Add children to dynamic sources and queue
            for child in children:
                child_name = child["name"]
                if child_name not in queue and child_name not in processed:
                    queue[child_name] = child
                    dynamic_sources[child_name] = child

    # Persist dynamic registry
    if dynamic_sources:
        APP_DIRS["meta"].mkdir(parents=True, exist_ok=True)
        write_text_atomic(dyn_path, json.dumps(list(dynamic_sources.values()), indent=2))

    return changed_any


def _load_yaml(p: Path) -> Any:
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else None


def _write_json(p: Path, obj: Any) -> None:
    write_text_atomic(p, json.dumps(obj, ensure_ascii=False, indent=2))


@app.command()
def build(manifest: ManifestPath) -> None:
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
        dep_paths: list[Path] = []
        for d in spec.deps:
            if d in source_paths:
                dep_paths.append(source_paths[d])
            else:
                dep_paths.append(APP_DIRS["targets"] / f"{d}.json")
        outputs = [APP_DIRS["targets"] / f"{tname}.json"]

        if not needs_rebuild(outputs, dep_paths):
            rprint(f"[dim]up-to-date[/dim] {tname}")
            continue

        # target plugin path
        try:
            get_target(spec.plugin)
        except Exception:
            if spec.plugin == "concat_json":  # legacy fallback should not happen now
                rprint(f"[yellow]legacy path used for {tname}[/yellow]")
            else:
                rprint(f"[yellow]SKIP[/yellow] {tname}: plugin {spec.plugin} not registered")
                continue
        result = execute_target(spec.plugin, spec.deps, spec.params)
        outp = outputs[0]
        prev = result.get("previous")
        merged = result.get("current")
        built_any = True
        changes = deep_diff(prev, merged) if prev is not None else [f"/: created {tname}"]
        if changes:
            (APP_DIRS["diffs"] / f"{tname}.diff.txt").write_text(
                "\n".join(changes), encoding="utf-8"
            )
            rprint(
                f"[green]built[/green] {tname} -> {outp}  ([bold]{len(changes)}[/bold] change lines)"
            )
        else:
            rprint(f"[green]built[/green] {tname} -> {outp}  (no structural changes)")

    if built_any:
        rprint("[bold green]Some targets rebuilt[/bold green]")
    else:
        rprint("[bold dim]No target rebuilt[/bold dim]")


@app.command()
def status(manifest: ManifestPath) -> None:
    sources, targets = load_manifest(manifest)

    tbl = Table(title="Sources", show_lines=False)
    tbl.add_column("name")
    tbl.add_column("path")
    tbl.add_column("exists")
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
    tbl2.add_column("name")
    tbl2.add_column("path")
    tbl2.add_column("needs rebuild?")
    for t in targets.values():
        outp = APP_DIRS["targets"] / f"{t.name}.json"
        dep_paths = []
        for d in t.deps:
            dep_paths.append(source_paths.get(d, APP_DIRS["targets"] / f"{d}.json"))
        tbl2.add_row(t.name, str(outp), "yes" if needs_rebuild([outp], dep_paths) else "no")
    rprint(tbl2)


@app.command()
def diff(
    artifact: str = typer.Argument(..., help="Prefix 'sources:' or 'targets:' + name"),
) -> None:
    kind, name = artifact.split(":", 1)
    if kind == "targets":
        p = APP_DIRS["diffs"] / f"{name}.diff.txt"
        if not p.exists():
            rprint(f"[dim]No diff recorded for target {name}[/dim]")
            raise typer.Exit(code=0)
        print(p.read_text(encoding="utf-8"))
    elif kind == "sources":
        p = APP_DIRS["sources"] / f"{name}.yaml"
        if not p.exists():
            rprint(f"[red]No such source {name}[/red]")
            raise typer.Exit(code=1)
        print(p.read_text(encoding="utf-8"))
    else:
        rprint("Use 'sources:NAME' or 'targets:NAME'.")


if __name__ == "__main__":
    app()
