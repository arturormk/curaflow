"""Unified plugin registration and lookup.

Light-weight in-process registry for *source* and *target* plugins. External
plugins register via decorators at import time.
"""

from __future__ import annotations

import importlib.util
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol, TypedDict

PluginName = str  # reuse conceptually; Literal set maintained elsewhere


class SourcePlugin(Protocol):
    async def __call__(
        self, name: str, params: dict[str, object]
    ) -> tuple[bool, dict[str, Any] | None, list[dict[str, Any]]]: ...


class TargetPlugin(Protocol):
    def __call__(self, name: str, deps: list[str], params: dict[str, object]) -> dict[str, Any]: ...


class PluginRegistrationError(RuntimeError):
    pass


class PluginNotFoundError(LookupError):
    pass


class PluginExecutionError(RuntimeError):
    def __init__(self, plugin: str, message: str, exc: BaseException | None = None):
        super().__init__(message)
        self.plugin = plugin
        self.original = exc


class FetchResult(TypedDict, total=False):
    name: str
    changed: bool
    data: dict[str, Any] | None
    children: list[dict[str, Any]]
    error: str


@dataclass
class _Registry:
    sources: dict[str, SourcePlugin]
    targets: dict[str, TargetPlugin]


_REGISTRY: Final = _Registry(sources={}, targets={})


def register_source(name: str, func: SourcePlugin) -> None:
    if name in _REGISTRY.sources:
        raise PluginRegistrationError(f"Source plugin '{name}' already registered")
    _REGISTRY.sources[name] = func


def register_target(name: str, func: TargetPlugin) -> None:
    if name in _REGISTRY.targets:
        raise PluginRegistrationError(f"Target plugin '{name}' already registered")
    _REGISTRY.targets[name] = func


def get_source(name: str) -> SourcePlugin:
    try:
        return _REGISTRY.sources[name]
    except KeyError as e:
        raise PluginNotFoundError(f"Unknown source plugin '{name}'") from e


def get_target(name: str) -> TargetPlugin:
    try:
        return _REGISTRY.targets[name]
    except KeyError as e:
        raise PluginNotFoundError(f"Unknown target plugin '{name}'") from e


def source_plugin(name: str) -> Callable[[SourcePlugin], SourcePlugin]:
    def deco(func: SourcePlugin) -> SourcePlugin:
        register_source(name, func)
        return func

    return deco


def target_plugin(name: str) -> Callable[[TargetPlugin], TargetPlugin]:
    def deco(func: TargetPlugin) -> TargetPlugin:
        register_target(name, func)
        return func

    return deco


async def execute_source(name: str, params: dict[str, object]) -> FetchResult:
    """Execute a source plugin safely, capturing exceptions into the result."""
    plugin = get_source(name)
    try:
        # Canonical call: first arg is the *source instance name* (manifest or dynamic)
        source_instance_name = params.get("name") if isinstance(params.get("name"), str) else name
        changed, data, children = await plugin(str(source_instance_name), params)
        return FetchResult(name=name, changed=changed, data=data, children=children)
    except Exception as exc:  # pragma: no cover - defensive
        tb = traceback.format_exception(exc)
        return FetchResult(name=name, changed=False, data=None, children=[], error="".join(tb))


def execute_target(
    plugin_name: str, target_name: str, deps: list[str], params: dict[str, object]
) -> dict[str, Any]:
    """Execute a target plugin.

    ``plugin_name`` is the registry key (e.g. ``"media_convert"``), while
    ``target_name`` is the *manifest target name* whose outputs are being
    built. Target plugins receive ``target_name`` as their first argument and
    should use it for any per-target filenames (such as JSON summaries).
    """

    plugin = get_target(plugin_name)
    return plugin(target_name, deps, params)


def list_sources() -> list[str]:  # convenience / testing
    return sorted(_REGISTRY.sources.keys())


def list_targets() -> list[str]:  # convenience / testing
    return sorted(_REGISTRY.targets.keys())


def load_plugins_from_dir(path: str | Path) -> None:
    """Dynamically import source/target plugins from a filesystem directory.

    The directory is expected to mirror the built-in layout:

        <root>/sources/*.py
        <root>/targets/*.py

    Any imported module can register plugins via the usual
    ``@source_plugin`` / ``@target_plugin`` decorators. This is intended
    primarily for the CLI ``--plugins`` option so that curators can keep
    project-specific plugins out of the core curaflow package.
    """

    root = Path(path)
    if not root.exists() or not root.is_dir():
        return

    def _import_tree(kind: str) -> None:
        base = root / kind
        if not base.is_dir():
            return
        for file in base.glob("*.py"):
            if file.name.startswith("__"):
                continue
            # Give each plugin module a unique, non-conflicting name
            # based on its absolute path so repeated invocations do not
            # clobber built-ins or each other.
            mod_name = f"_curaflow_ext_{kind}_" + "_".join(
                str(file.resolve()).split("/")[-4:]
            ).replace(".", "_")
            if mod_name in sys.modules:
                continue
            spec = importlib.util.spec_from_file_location(mod_name, file)
            if spec is None or spec.loader is None:  # pragma: no cover - defensive
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)

    _import_tree("sources")
    _import_tree("targets")


__all__ = [
    "FetchResult",
    "PluginExecutionError",
    "PluginNotFoundError",
    "PluginRegistrationError",
    "SourcePlugin",
    "TargetPlugin",
    "load_plugins_from_dir",
    "execute_source",
    "execute_target",
    "get_source",
    "get_target",
    "list_sources",
    "list_targets",
    "register_source",
    "register_target",
    "source_plugin",
    "target_plugin",
]
