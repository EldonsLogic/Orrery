"""Derived reorder step (BPL-045, ADR-0072, Q-627): a prepend, a rename in the middle and several removals compile to a
reorder step with empty sourceOps and `derivedFrom`, apply on the fake adapter and roll back to the base export.
Synthetic data only."""
import copy

import pytest

import cmp_helpers as H
from bpdiff import diff, invert
from compiler import artifact as art
from test_cmp_incremental import _compile, _entity, _fake, _field, _inputs, _rev2, _rollback_approvals

NEW = {"id": "aa_first", "type": "string", "labels": {"ar": "أول", "en": "First"}}


def _prepend(t):
    _entity(t, "supplier")["fields"].insert(0, copy.deepcopy(NEW))


def _rename_middle(t):
    _field(t, "supplier", "email").update(id="email_address")


def _two_removals(t):
    e = _entity(t, "supplier")
    e["fields"] = [f for f in e["fields"] if f["id"] not in ("email", "bank_iban")]


def _option_prepend(t):
    _field(t, "supplier", "supplier_type")["options"].insert(0, {"value": "agent", "labels": {"ar": "وكيل", "en": "Agent"}})


def _option_two_removals(t):
    f = _field(t, "supplier", "supplier_type")
    f["options"] = [o for o in f["options"] if o["value"] == "manufacturer"]


def _remove_first_and_third(t):
    # The inverse restores supplier_code at index 0 and vat_number at index 2 in one list; the adapter puts each back
    # at its index when it was removed, so applied in pointer order the restores land out of order.
    e = _entity(t, "supplier")
    e["fields"] = [f for f in e["fields"] if f["id"] not in ("supplier_code", "vat_number")]


EDITS = [_prepend, _rename_middle, _two_removals, _option_prepend, _option_two_removals, _remove_first_and_third]


def _derived(a):
    return [s for s in a["steps"] if "derivedFrom" in s]


@pytest.mark.parametrize("edit", EDITS)
def test_a_position_change_with_no_reorder_op_compiles_to_a_derived_reorder_in_both_directions(edit):
    base, reg, mp = _inputs()
    t = _rev2(base, edit)
    fwd = _compile(t, base, reg, mp)
    d = diff(base, t)
    for a, src in ((fwd, d), (fwd["inverse"], invert(d))):
        assert not list(H.ARTIFACT_VALIDATOR.iter_errors(a)) and art.check(a) == []
        assert a["artifactSchema"] == "0.2.0"
        (step,) = _derived(a)
        assert step["kind"] in ("field.reorder", "option.reorder") and step["sourceOps"] == [] and step["phase"] == 6
        ops = {op["pointer"]: op for op in src["ops"]}
        assert step["derivedFrom"] == sorted(step["derivedFrom"]) and set(step["derivedFrom"]) <= set(ops)
        assert all(ops[p]["op"] in ("add", "remove") and p.startswith(step["pointer"] + "/") for p in step["derivedFrom"])
        assert step["impact"] == max((ops[p]["impact"] for p in step["derivedFrom"]),
                                     key=list(reversed(__import__("bpdiff").classify._SEVERITY)).index)
        covered = sorted([p for s in a["steps"] for p in s["sourceOps"]] + [s["pointer"] for s in a["skippedOps"]])
        assert covered == sorted(ops)  # exactly once still holds for sourceOps; derivedFrom does not count
    assert [s["pointer"] for s in _derived(fwd)] == [s["pointer"] for s in _derived(fwd["inverse"])]


def test_several_restores_in_one_inverse_carry_a_derived_reorder():
    base, reg, mp = _inputs()
    t = _rev2(base, _remove_first_and_third)
    fwd = _compile(t, base, reg, mp)
    inv = fwd["inverse"]
    (step,) = _derived(inv)
    ops = {op["pointer"]: op for op in invert(diff(base, t))["ops"]}
    restores = [p for p in step["derivedFrom"] if ops[p]["op"] == "add"]
    assert len(restores) == 2 and step["derivedFrom"] == sorted(step["derivedFrom"])
    assert [p.rsplit("/", 1)[1] for p in restores] == ["supplier_code", "vat_number"]
    assert step["kind"] == "field.reorder" and not step["sourceOps"]
    # the reorder lists the base order exactly: the restored keys in their base places
    ids = [f["id"] for f in _entity(base, "supplier")["fields"]]
    assert step["params"]["order"] == ids


def test_an_artifact_without_a_derived_step_keeps_schema_0_1_0():
    base, reg, mp = _inputs()
    fwd = _compile(_rev2(base, lambda t: _entity(t, "supplier")["fields"].append(copy.deepcopy(NEW))), base, reg, mp)
    assert fwd["artifactSchema"] == fwd["inverse"]["artifactSchema"] == "0.1.0" and not _derived(fwd)


@pytest.mark.parametrize("edit", EDITS)
def test_a_derived_reorder_applies_and_rolls_back_on_the_fake_adapter(edit):
    h, tk, adapter_id = _fake()
    base, reg, mp = _inputs(adapter_id)
    t = _rev2(base, edit)
    initial, fwd = _compile(base, None, reg, mp), _compile(t, base, reg, mp)
    assert tk.provision(h, blueprint_id=base["meta"]["id"], target=initial["engineTarget"], site_class="sandbox")["ok"]
    assert tk.apply_artifact(h, initial)["result"]["status"] == "applied"
    base_hash = tk.export(h)["exportHash"]
    out = tk.apply_artifact(h, fwd)
    assert out["ok"] and out["result"]["status"] == "applied", out
    assert all(pc["passed"] for pc in out["result"]["postConditions"])
    sup = next(e for e in tk.export(h)["export"]["sections"]["entities"] if e["id"] == "supplier")
    assert [f["id"] for f in sup["fields"]] == [f["id"] for f in _entity(t, "supplier")["fields"]]
    back = tk.rollback(h, fwd, approvals=_rollback_approvals(tk))
    assert back["ok"] and back["result"]["status"] == "applied", back
    assert tk.export(h)["exportHash"] == base_hash


def test_the_fake_adapter_blocks_a_reorder_that_does_not_list_exactly_the_active_keys():
    h, tk, adapter_id = _fake()
    base, reg, mp = _inputs(adapter_id)
    initial, fwd = _compile(base, None, reg, mp), _compile(_rev2(base, _prepend), base, reg, mp)
    assert tk.provision(h, blueprint_id=base["meta"]["id"], target=initial["engineTarget"], site_class="sandbox")["ok"]
    assert tk.apply_artifact(h, initial)["result"]["status"] == "applied"
    bad = copy.deepcopy(fwd)
    (step,) = _derived(bad)
    step["params"]["order"] = step["params"]["order"][1:]  # drops the added key
    bad = art.seal(bad)
    plan = tk.plan(h, bad)
    assert plan["ok"] and plan["result"]["verdict"] == "rejected", plan
    entry = next(s for s in plan["result"]["steps"] if s["seq"] == step["seq"])
    assert entry["disposition"] == "blocked" and entry["reasonCode"] == "definition_conflict"


# ---------------------------------------------------------------- schema and x-validator-rules


def _sample():
    base, reg, mp = _inputs()
    return _compile(_rev2(base, _prepend), base, reg, mp)


def _errors(a):
    return list(H.ARTIFACT_VALIDATOR.iter_errors(a))


def test_empty_source_ops_are_valid_only_on_a_derived_reorder():
    a = _sample()
    add = next(s for s in a["steps"] if s["kind"] == "field.add")
    add["sourceOps"] = []
    assert _errors(a)  # an ordinary step still needs at least one source op
    a = _sample()
    (step,) = _derived(a)
    del step["derivedFrom"]
    assert _errors(a)  # empty sourceOps without derivedFrom
    a = _sample()
    add = next(s for s in a["steps"] if s["kind"] == "field.add")
    add["derivedFrom"] = list(add["sourceOps"])
    assert _errors(a)  # derivedFrom only on a reorder kind
    a = _sample()
    (step,) = _derived(a)
    step["sourceOps"] = list(step["derivedFrom"])
    assert _errors(a)  # a derived step carries no sourceOps of its own
    a = _sample()
    a["artifactSchema"] = "0.1.0"
    assert _errors(a)  # a derived step needs artifact schema 0.2.0


def test_derived_from_lists_each_op_once():
    a = _sample()
    assert not _errors(a)
    (step,) = _derived(a)
    step["derivedFrom"] = step["derivedFrom"] + step["derivedFrom"][:1]  # the same op named twice
    assert any(e.validator == "uniqueItems" for e in _errors(a))


def test_derived_from_must_name_add_or_remove_ops_another_step_implements():
    a = _sample()
    (step,) = _derived(a)
    step["derivedFrom"] = ["/entities/supplier/fields/not_in_the_diff"]
    a = art.seal(a)
    assert not _errors(a)  # the schema cannot see other steps
    assert [i.code for i in art.check(a)] == ["CMP-ART-004"]
    a = _sample()
    (step,) = _derived(a)
    step["derivedFrom"] = ["/entities/customer/fields/phone"]  # not under the step's own collection
    assert [i.code for i in art.check(art.seal(a))] == ["CMP-ART-004"]
