from __future__ import annotations

import asyncio

import pytest

from curaflow.plugin_registry import (
    PluginNotFoundError,
    PluginRegistrationError,
    execute_source,
    get_source,
    get_target,
    list_sources,
    list_targets,
    register_source,
    register_target,
    source_plugin,
    target_plugin,
)


async def dummy_source(
    name: str, params: dict[str, object]
) -> tuple[bool, dict[str, object], list[dict[str, object]]]:
    return True, {"ok": True, "name": name}, []


def dummy_target(name: str, deps: list[str], params: dict[str, object]) -> dict[str, object]:
    return {"previous": None, "current": {"deps": deps, "params": params}, "output_path": "-"}


def test_registration_and_lookup() -> None:
    # unique names per test run
    register_source("_test_src", dummy_source)
    register_target("_test_tgt", dummy_target)
    assert "_test_src" in list_sources()
    assert "_test_tgt" in list_targets()
    assert get_source("_test_src") is not None
    assert get_target("_test_tgt") is not None


def test_duplicate_registration() -> None:
    register_source("_dupe", dummy_source)
    with pytest.raises(PluginRegistrationError):
        register_source("_dupe", dummy_source)


def test_not_found() -> None:
    with pytest.raises(PluginNotFoundError):
        get_source("__missing__")


def test_decorator_registration() -> None:
    @source_plugin("_decorated_src")
    async def decorated(
        name: str, params: dict[str, object]
    ) -> tuple[bool, None, list[dict[str, object]]]:
        return False, None, []

    @target_plugin("_decorated_tgt")
    def decorated_tgt(name: str, deps: list[str], params: dict[str, object]) -> dict[str, object]:
        return {"previous": None, "current": {"deps": deps}, "output_path": "-"}

    assert "_decorated_src" in list_sources()
    assert "_decorated_tgt" in list_targets()


def test_execute_source_success() -> None:
    register_source("_exec", dummy_source)
    res = asyncio.run(execute_source("_exec", {"name": "thing"}))
    assert res.get("changed") is True
    data = res.get("data") or {}
    assert data.get("name") == "thing"


def test_execute_source_error_is_captured() -> None:
    async def failing(
        name: str, params: dict[str, object]
    ) -> tuple[bool, None, list[dict[str, object]]]:
        raise RuntimeError("boom")

    register_source("_boom", failing)
    res = asyncio.run(execute_source("_boom", {"name": "x"}))
    assert res.get("error")
    assert res.get("changed") is False
