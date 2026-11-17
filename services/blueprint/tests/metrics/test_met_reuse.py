import copy

import pytest

from metrics import MetricsError, new_components_per_build, reuse_ratio


def test_reuse_examples():
    inp = {"t1": [("a", "1.0.0"), ("b", "1.0.0")], "t2": [("a", "1.1.0"), ("c", "1.0.0")], "t3": [("a", "1.0.0")]}
    r = reuse_ratio(inp)
    assert r.ratio == (1, 3) and r.percent == 33.33
    assert r.tenant_counts == {"a": 3, "b": 1, "c": 1} and r.reused_ids == ("a",)


def test_versions_are_one_component_and_one_tenant_counts_once():
    r = reuse_ratio({"t1": [("a", "1.0.0"), ("a", "2.0.0")], "t2": [("b", "1.0.0")]})
    assert r.ratio == (0, 2) and r.tenant_counts == {"a": 1, "b": 1}


def test_all_shared_and_empty_tenant_allowed():
    r = reuse_ratio({"t1": [("a", "1")], "t2": [("a", "1")], "t3": []})
    assert r.ratio == (1, 1) and r.percent == 100.0


def test_reuse_deterministic_no_mutation():
    inp = {"t2": [["b", "1"], ["a", "1"]], "t1": [["a", "1"]]}
    c = copy.deepcopy(inp)
    assert reuse_ratio(inp) == reuse_ratio(inp) and inp == c
    assert reuse_ratio(inp).to_dict()["tenant_counts"] == {"a": 2, "b": 1}


@pytest.mark.parametrize("bad,code", [
    ([], "MET-REUSE-001"), ({"t": "ab"}, "MET-REUSE-001"), ({"": [("a", "1")]}, "MET-REUSE-001"),
    ({"t": [("a",)]}, "MET-REUSE-001"), ({"t": [("a", 1)]}, "MET-REUSE-001"), ({"t": [("", "1")]}, "MET-REUSE-001"),
    ({"t": 5}, "MET-REUSE-001"), ({}, "MET-REUSE-002"), ({"t": []}, "MET-REUSE-002"),
])
def test_reuse_refusals(bad, code):
    with pytest.raises(MetricsError) as e:
        reuse_ratio(bad)
    assert e.value.code == code


def test_new_components():
    r = new_components_per_build(["a", "b"], ["a", "b", "c", "d"])
    assert r.count == 2 and r.added == ("c", "d") and r.removed == ()
    r = new_components_per_build({"a", "b"}, ["a", "c"])
    assert r.count == 1 and r.removed == ("b",)
    assert new_components_per_build([], []).count == 0
    assert new_components_per_build(["a"], ["a", "a"]).count == 0


@pytest.mark.parametrize("b,a", [("ab", ["a"]), (["a"], "ab"), ([1], ["a"]), (["a"], [""]), (None, []), ({"a": 1}, [])])
def test_new_components_refusals(b, a):
    with pytest.raises(MetricsError) as e:
        new_components_per_build(b, a)
    assert e.value.code == "MET-NEW-001"
