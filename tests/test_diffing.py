from curaflow.diffing import deep_diff

def test_deep_diff_basic_changes():
    a = {"a": 1, "b": {"c": 2}}
    b = {"a": 1, "b": {"c": 3, "d": 4}}
    diff = deep_diff(a, b)
    assert any('/b/c' in line and '2 -> 3' in line for line in diff)
    assert any('/b/d' in line and 'added' in line for line in diff)
