from __future__ import annotations

import asyncio
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Annotated, Any, Final, TypedDict, cast

import typer
import yaml
from rich import print as rprint
from rich.table import Table

from .dag import PluginName, SourceSpec, TargetSpec, needs_rebuild, topo_sort
from .diffing import deep_diff
from .plugin_registry import (
    execute_source,
    execute_target,
    get_source,
    get_target,
    load_plugins_from_dir,
)
from .utils import substitute_placeholders, write_text_atomic


class ManifestSource(TypedDict, total=False):
    name: str
    plugin: PluginName
    params: dict[str, object]


class ManifestTarget(TypedDict, total=False):
    name: str
    # Manifest targets may include pseudo-plugins (e.g. "lang_targets")
    # that are expanded before DAG/PluginName types are enforced.
    plugin: str
    deps: list[str]
    params: dict[str, object]


def _expand_lang_targets(raw_targets: list[ManifestTarget]) -> list[ManifestTarget]:
    """Expand any ``lang_targets`` pseudo-plugin entries into concrete targets.

    A ``lang_targets`` entry has the following expected shape in the manifest::

        - name: lang-qml
          plugin: lang_targets
          params:
            languages: ["es", "en"]
            targets:
              - name: "$lang$_banners_qml"
                plugin: qml_banners
                deps: ["$lang$:banners"]
                params:
                  base_dir: "$lang$/banners"
                  # ... other plugin-specific params ...

    For each language code, placeholders of the form ``"$lang$"`` are
    substituted across the nested target templates using
    :func:`substitute_placeholders`, and the resulting plain targets are
    returned. The original ``lang_targets`` entry itself does not become a
    target.
    """

    expanded: list[ManifestTarget] = []

    for t in raw_targets:
        if t.get("plugin") != "lang_targets":
            expanded.append(t)
            continue

        params = t.get("params") or {}
        languages = params.get("languages") or []
        templates = params.get("targets") or []

        if not isinstance(languages, list) or not all(isinstance(x, str) for x in languages):
            raise TypeError("lang_targets expects 'languages' to be a list of strings")
        if not isinstance(templates, list):
            raise TypeError("lang_targets expects 'targets' to be a list of target templates")

        for lang in languages:
            mapping = {"$lang$": lang}
            for tmpl in templates:
                if not isinstance(tmpl, dict):
                    continue
                concrete = substitute_placeholders(deepcopy(tmpl), mapping)
                # Name is required; fall back to a deterministic synthetic name
                name = str(concrete.get("name") or f"{lang}:{t.get('name', 'lang')}")
                concrete["name"] = name
                expanded.append(concrete)

    return expanded


APP_DIRS: Final = {
    "meta": Path(".curaflow/meta"),
    "diffs": Path(".curaflow/diffs"),
    "sources": Path("data/sources"),
    "targets": Path("data/targets"),
}

# Import plugins to register them (requires APP_DIRS to be defined first for some plugins)
from . import plugins  # noqa: E402, F401

app = typer.Typer(
    help="Curaflow: incremental fetch→normalize→build pipeline (with hierarchical fanout)."
)


@app.callback()
def main(
    plugins_path: Annotated[
        Path | None,
        typer.Option(
            "--plugins",
            help=(
                "Additional plugin directory with 'sources' and 'targets' subdirectories. "
                "Modules found there are imported after built-in curaflow plugins."
            ),
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
        ),
    ] = None,
) -> None:
    """CLI entrypoint callback.

    If ``--plugins`` is provided, dynamically import any source/target
    plugins found under that directory *after* the built-in plugins are
    registered. External modules are expected to use the standard
    ``@source_plugin`` / ``@target_plugin`` decorators.
    """

    if plugins_path is not None:
        load_plugins_from_dir(plugins_path)


ManifestPath = Annotated[Path, typer.Option("-m", help="Path to manifest.yaml")]


def load_manifest(manifest: Path) -> tuple[dict[str, SourceSpec], dict[str, TargetSpec]]:
    m = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    sources: dict[str, SourceSpec] = {}
    targets: dict[str, TargetSpec] = {}
    for s in m.get("sources", []):
        sources[s["name"]] = SourceSpec(
            name=s["name"], plugin=s["plugin"], params=s.get("params", {})
        )
    raw_targets: list[ManifestTarget] = list(m.get("targets", []))
    expanded_targets = _expand_lang_targets(raw_targets)
    for t in expanded_targets:
        targets[t["name"]] = TargetSpec(
            name=t["name"],
            plugin=cast(PluginName, t["plugin"]),
            deps=t.get("deps", []),
            params=t.get("params", {}),
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
    debug: bool = typer.Option(
        False,
        help="Print source plugin outputs and extractions for debugging manifests",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Force re-fetch of all sources, ignoring HTTP cache metadata",
    ),
) -> None:
    """Fetch/normalize all sources (skips if unchanged), including dynamically fanned-out children."""
    ensure_base_dirs()
    sources, _ = load_manifest(manifest)

    # Run the async fetch function
    changed_any = asyncio.run(_fetch_parallel(sources, max_concurrent, debug=debug, force=force))

    if changed_any:
        rprint("[bold green]Some sources changed[/bold green]")
    else:
        rprint("[bold dim]No source changed[/bold dim]")


async def _fetch_parallel(
    sources: dict[str, SourceSpec],
    max_concurrent: int,
    debug: bool = False,
    force: bool = False,
) -> bool:
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

    # Initialize queue with manifest sources and dynamic sources. Tests may pass plain
    # dicts masquerading as SourceSpec, so accept both dataclass and mapping inputs.
    queue: dict[str, dict[str, Any]] = {}
    for src in sources.values():
        if isinstance(src, dict):  # tolerate tests using raw dicts cast to SourceSpec
            name = src["name"]
            plugin = src["plugin"]
            params = src.get("params", {})
        else:
            name = src.name
            plugin = src.plugin
            params = src.params
        queue[name] = {"name": name, "plugin": plugin, "params": params}
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
                # registry-based plugin
                try:
                    get_source(plugin)
                except Exception:
                    rprint(f"[yellow]SKIP[/yellow] {name}: plugin {plugin} not registered")
                    return name, False, []

                res = await execute_source(plugin, {**params, "name": name, "force": force})
                if debug:
                    data = res.get("data")
                    children = res.get("children") or []
                    rprint(f"[bold cyan]DEBUG source[/bold cyan] {name} ({plugin})")
                    if data is not None:
                        try:
                            y = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
                            rprint(y)
                        except Exception:
                            rprint(data)

                        if isinstance(data, dict) and "extractions" in data:
                            try:
                                y_ex = yaml.safe_dump(
                                    data.get("extractions"),
                                    sort_keys=False,
                                    allow_unicode=True,
                                )
                                rprint("[cyan]extractions:[/cyan]")
                                rprint(y_ex)
                            except Exception:
                                rprint("[cyan]extractions:[/cyan]")
                                rprint(data.get("extractions"))
                    else:
                        rprint("[dim]no data returned by plugin[/dim]")

                    if children:
                        rprint(
                            f"[cyan]children:[/cyan] {json.dumps(children, ensure_ascii=False, indent=2)}"
                        )
                if "error" in res:
                    rprint(f"[red]error[/red] {name} ({plugin}) -> {res['error'].splitlines()[-1]}")
                    return name, False, []
                else:
                    changed = res.get("changed", False)
                    children = res.get("children", []) or []
                    if changed:
                        child_count = len(children)
                        suffix = f"  (+{child_count} children)" if child_count else ""
                        rprint(f"[green]updated[/green] {name} -> data/sources/{name}.yaml{suffix}")
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


def _walk_path(obj: Any, path: str) -> Any:
    """Resolve a dotted path like ``extractions.tenant_links``.

    Returns an empty list if any component is missing, so callers can
    assume a list-like result without extra key checks.
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
        # Execute the target plugin with the *target name* as the first
        # argument so that per-target outputs (e.g. JSON summaries) can be
        # named consistently with the manifest.
        result = execute_target(spec.plugin, spec.name, spec.deps, spec.params)
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
def table(
    source: Annotated[
        str,
        typer.Argument(
            ...,
            help="Source name; reads data/sources/<source>.yaml from the current APP_DIRS",
        ),
    ],
    list_key: Annotated[
        str,
        typer.Option(
            "--list-key",
            "-k",
            help=(
                "Dotted path to the list of records inside the YAML. "
                "If omitted and the YAML document is itself a list, that list is used."
            ),
        ),
    ] = "",
    columns: Annotated[
        list[str] | None,
        typer.Option(
            "--columns",
            "-c",
            help=(
                "Columns to show. Can be passed multiple times or as comma-separated values, "
                "for example: --columns codigo,slug,marca"
            ),
        ),
    ] = None,
    sort: Annotated[
        list[str] | None,
        typer.Option(
            "--sort",
            "-s",
            help=(
                "Sort criteria. Each entry is +field or -field. "
                "Can be passed multiple times or as comma-separated values."
            ),
        ),
    ] = None,
) -> None:
    """Print a YAML source as a table.

    This is a small utility for inspecting source data. It reads the
    YAML file for the given ``source`` from ``APP_DIRS['sources']`` and
    renders a Rich table on stdout.
    """

    p = APP_DIRS["sources"] / f"{source}.yaml"
    if not p.exists():
        rprint(f"[red]No such source YAML:[/red] {p}")
        raise typer.Exit(code=1)

    data = _load_yaml(p)

    # Resolve the list of rows
    raw_rows: Any
    if list_key:
        raw_rows = _walk_path(data, list_key)
    else:
        raw_rows = data

    if isinstance(raw_rows, dict):
        rows_seq: list[Any] = list(raw_rows.values())
    elif isinstance(raw_rows, list):
        rows_seq = list(raw_rows)
    else:
        rprint(
            "[red]Expected a list of records at the given path; "
            f"got {type(raw_rows).__name__} instead[/red]"
        )
        raise typer.Exit(code=1)

    # Normalise into list of dicts for tabular display
    rows: list[dict[str, Any]] = []
    for item in rows_seq:
        if isinstance(item, dict):
            rows.append(item)
        else:
            rows.append({"value": item})

    if not rows:
        rprint("[dim]No rows to display[/dim]")
        return

    # Parse columns (support both repeated and comma-separated usage)
    col_tokens = columns or []
    parsed_cols: list[str] = []
    for token in col_tokens:
        for part in token.split(","):
            part = part.strip()
            if part:
                parsed_cols.append(part)

    if not parsed_cols:
        # Derive from union of keys, stable sorted for determinism
        key_set: set[str] = set()
        for row in rows:
            key_set.update(str(k) for k in row.keys())
        parsed_cols = sorted(key_set)

    # Parse sort criteria; later entries are lower precedence
    sort_tokens = sort or []
    sort_specs: list[tuple[str, bool]] = []  # (field, reverse)
    for token in sort_tokens:
        for part in token.split(","):
            part = part.strip()
            if not part:
                continue
            direction = part[0]
            if direction in "+-":
                field = part[1:]
                reverse = direction == "-"
            else:
                field = part
                reverse = False
            if field:
                sort_specs.append((field, reverse))

    def _natural_key(value: Any) -> tuple[object, ...]:
        """Return a key for *natural* ordering.

        Splits strings into digit and non-digit segments so that
        "10" > "2" numerically when sorting. Non-string values are
        converted to strings.
        """

        if value is None:
            return ()

        text = str(value)
        parts = re.split(r"(\d+)", text)
        key_parts: list[object] = []
        for part in parts:
            if not part:
                continue
            if part.isdigit():
                try:
                    key_parts.append(int(part))
                except ValueError:
                    key_parts.append(part)
            else:
                key_parts.append(part)
        return tuple(key_parts)

    def _sort_key(field: str, row: dict[str, Any]) -> tuple[bool, tuple[object, ...]]:
        v = row.get(field)
        if v is None:
            return True, ()
        return False, _natural_key(v)

    # Apply multi-key sort, lowest precedence first
    for field, reverse in reversed(sort_specs):
        rows.sort(key=lambda r: _sort_key(field, r), reverse=reverse)

    tbl = Table(title=f"Source {source}")
    for col in parsed_cols:
        tbl.add_column(col)

    for row in rows:
        tbl.add_row(*[str(row.get(col, "")) for col in parsed_cols])

    rprint(tbl)


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
