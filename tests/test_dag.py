import time
from pathlib import Path

from curaflow.dag import TargetSpec, needs_rebuild, topo_sort


def test_topo_sort_order() -> None:
    targets = {
        "A": TargetSpec(name="A", plugin="concat_json", deps=[], params={}),
        "B": TargetSpec(name="B", plugin="concat_json", deps=["A"], params={}),
        "C": TargetSpec(name="C", plugin="concat_json", deps=["B"], params={}),
    }
    order = topo_sort(targets)
    assert order == ["A", "B", "C"]


def test_needs_rebuild(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    dep = tmp_path / "dep.json"
    dep.write_text("{}")
    # No output yet -> needs rebuild
    assert needs_rebuild([out], [dep])
    out.write_text("{}")
    time.sleep(0.01)
    dep.write_text('{"x":1}')
    assert needs_rebuild([out], [dep])
