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


def _drop_email(t):
    e = _entity(t, "supplier")
    e["fields"] = [f for f in e["fields"] if f["id"] != "email"]


@pytest.mark.parametrize("edit", [_drop_email, lambda t: _entity(t, "supplier")["labels"].update(en="Vendor")])
def test_an_artifact_without_a_derived_step_keeps_schema_0_1_0(edit):
    base, reg, mp = _inputs()
    fwd = _compile(_rev2(base, edit), base, reg, mp)
    assert fwd["artifactSchema"] == fwd["inverse"]["artifactSchema"] == "0.1.0" and not _derived(fwd)


def test_an_append_carries_a_derived_reorder_because_the_add_may_be_a_restore():
    base, reg, mp = _inputs()
    fwd = _compile(_rev2(base, lambda t: _entity(t, "supplier")["fields"].append(copy.deepcopy(NEW))), base, reg, mp)
    assert fwd["artifactSchema"] == fwd["inverse"]["artifactSchema"] == "0.2.0"
    assert [s["derivedFrom"] for s in _derived(fwd)] == [["/entities/supplier/fields/aa_first"]]
    assert [s["pointer"] for s in _derived(fwd["inverse"])] == ["/entities/supplier/fields"]


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
    assert _site_order(tk, h, "field") == _order(t, "field")
    assert _site_order(tk, h, "option") == _order(t, "option")  # options are keyed by value (review Low 6)
    back = tk.rollback(h, fwd, approvals=_rollback_approvals(tk))
    assert back["ok"] and back["result"]["status"] == "applied", back
    assert tk.export(h)["exportHash"] == base_hash
    assert _site_order(tk, h, "field") == _order(base, "field") and _site_order(tk, h, "option") == _order(base, "option")


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


def test_the_schema_refuses_an_inverse_whose_artifact_schema_differs_from_its_forward():
    # review Low 5: the inverse is the 0.2.0 one, the forward has no derived step and says 0.1.0
    a = _sample()
    a["steps"] = [s for s in a["steps"] if "derivedFrom" not in s]
    for i, s in enumerate(a["steps"], 1):
        s["seq"] = i
    a["artifactSchema"] = "0.1.0"
    assert a["inverse"]["artifactSchema"] == "0.2.0"
    assert any(list(e.absolute_path) == ["inverse", "artifactSchema"] for e in _errors(a)), _errors(a)
    a = _sample()
    a["inverse"]["steps"] = [s for s in a["inverse"]["steps"] if "derivedFrom" not in s]
    a["inverse"]["artifactSchema"] = "0.1.0"  # the other way round
    assert any(list(e.absolute_path) == ["inverse", "artifactSchema"] for e in _errors(a)), _errors(a)


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


# ---------------------------------------------------------------- partner review at 0fb152e4 (High 1, Low 6, Low 7)


def _opts_of(t):
    return _field(t, "supplier", "supplier_type")["options"]


def _order(t, kind):
    if kind == "field":
        return [f["id"] for f in _entity(t, "supplier")["fields"]]
    return [o["value"] for o in _opts_of(t)]


def _site_order(tk, h, kind):
    sup = next(e for e in tk.export(h)["export"]["sections"]["entities"] if e["id"] == "supplier")
    if kind == "field":
        return [f["id"] for f in sup["fields"]]
    return [o["value"] for o in next(f for f in sup["fields"] if f["id"] == "supplier_type")["options"]]


def _drop_middle(kind):
    def edit(t):
        if kind == "field":
            e = _entity(t, "supplier")
            e["fields"] = [f for f in e["fields"] if f["id"] != "email"]
        else:
            f = _field(t, "supplier", "supplier_type")
            f["options"] = [o for o in f["options"] if o["value"] != "importer"]
    return edit


def _readd_at_end(old, kind):
    """Bring back what _drop_middle removed, at the end of the list (not its old index)."""
    def edit(t):
        if kind == "field":
            _entity(t, "supplier")["fields"].append(copy.deepcopy(_field(old, "supplier", "email")))
        else:
            _opts_of(t).append(copy.deepcopy(next(o for o in _opts_of(old) if o["value"] == "importer")))
    return edit


def _started(adapter_id):
    h, tk = _fake()[:2]
    base, reg, mp = _inputs(adapter_id)
    initial = _compile(base, None, reg, mp)
    assert tk.provision(h, blueprint_id=base["meta"]["id"], target=initial["engineTarget"], site_class="sandbox")["ok"]
    assert tk.apply_artifact(h, initial)["result"]["status"] == "applied"
    return h, tk, base, reg, mp


@pytest.mark.parametrize("kind", ["field", "option"])
def test_a_re_add_after_a_quarantine_reaches_the_target_order(kind):
    # The site still holds the quarantined element, so the adapter restores it at its old index; the compiler cannot
    # see site history, so every add to an ordered list of a kept parent carries a derived reorder (ADR-0072 point 5).
    h, tk, base, reg, mp = _started(_fake()[2])
    r2 = _rev2(base, _drop_middle(kind))
    r3 = _rev2(r2, _readd_at_end(base, kind))
    assert tk.apply_artifact(h, _compile(r2, base, reg, mp))["result"]["status"] == "applied"
    before = tk.export(h)["exportHash"]
    fwd = _compile(r3, r2, reg, mp)
    assert _derived(fwd) and _derived(fwd["inverse"])
    out = tk.apply_artifact(h, fwd)
    assert out["ok"] and out["result"]["status"] == "applied", out
    assert _site_order(tk, h, kind) == _order(r3, kind)
    back = tk.rollback(h, fwd, approvals=_rollback_approvals(tk))
    assert back["ok"] and back["result"]["status"] == "applied", back
    assert tk.export(h)["exportHash"] == before


@pytest.mark.parametrize("kind", ["field", "option"])
def test_add_roll_back_then_re_add_elsewhere_reaches_the_target_order(kind):
    h, tk, base, reg, mp = _started(_fake()[2])
    x = copy.deepcopy(NEW) if kind == "field" else {"value": "agent", "labels": {"ar": "وكيل", "en": "Agent"}}
    y = {**copy.deepcopy(x), **({"id": "zz_other"} if kind == "field" else {"value": "zz_other"})}

    def append(*items):
        def edit(t):
            (_entity(t, "supplier")["fields"] if kind == "field" else _opts_of(t)).extend(copy.deepcopy(list(items)))
        return edit
    first = _compile(_rev2(base, append(x)), base, reg, mp)
    assert tk.apply_artifact(h, first)["result"]["status"] == "applied"
    assert tk.rollback(h, first, approvals=_rollback_approvals(tk))["result"]["status"] == "applied"
    r2 = _rev2(base, append(y))  # y now sits where x was quarantined from
    assert tk.apply_artifact(h, _compile(r2, base, reg, mp))["result"]["status"] == "applied"
    target = _rev2(r2, append(x))  # x comes back after y
    out = tk.apply_artifact(h, _compile(target, r2, reg, mp))
    assert out["ok"] and out["result"]["status"] == "applied", out
    assert _site_order(tk, h, kind) == _order(target, kind)


def test_an_option_change_carries_an_order_post_condition():
    base, reg, mp = _inputs()
    target = _rev2(base, _option_prepend)
    fwd = _compile(target, base, reg, mp)
    ptr = "/entities/supplier/fields/supplier_type/options"
    for a, t in ((fwd, target), (fwd["inverse"], base)):
        (pc,) = [p for p in a["postConditions"] if p["pointer"] == ptr and p["check"] == "order_equals"]
        assert pc["expected"] == _order(t, "option")


def test_an_order_change_with_no_reorder_or_membership_op_is_refused():
    # bpdiff always emits a reorder op for a pure position change; a diff without one (hand-built or from a faulty
    # differ) must be refused, not compiled to an artifact that leaves the order wrong (review Low 7).
    from compiler.incremental import steps_from_diff
    base = _inputs()[0]
    t = _rev2(base, lambda t: _entity(t, "supplier")["fields"].reverse())
    d = diff(base, t)
    d["ops"] = [op for op in d["ops"] if op["op"] != "reorder"]
    issues = steps_from_diff(d, base, t)[2]
    assert [(i.code, i.path) for i in issues] == [("CMP-ART-001", "/entities/supplier/fields")]
    assert "no reorder or membership op" in issues[0].message


# ---------------------------------------------------------------- RULES 42 review of #348 (Low 3)


def test_a_forward_derived_reorder_needs_an_inverse_derived_reorder_at_the_same_pointer():
    a = _sample()
    (step,) = _derived(a)
    assert art.check(a) == []
    assert any(s["pointer"] == step["pointer"] for s in a["inverse"]["steps"] if "derivedFrom" in s)
    a["inverse"]["steps"] = [s for s in a["inverse"]["steps"] if "derivedFrom" not in s]
    for i, s in enumerate(a["inverse"]["steps"], 1):
        s["seq"] = i
    issues = [i for i in art.check(art.seal(a)) if i.code == "CMP-ART-004" and "inverse" in i.message]
    assert issues and issues[0].path == ptr_steps(step)


def test_the_schema_refuses_a_reorder_that_names_a_key_twice():
    for key in ("order", "previousOrder"):
        a = _sample()
        (step,) = _derived(a)
        step["params"][key] = step["params"][key] + step["params"][key][:1]
        assert any(e.validator == "uniqueItems" for e in _errors(a)), key


def ptr_steps(step):
    return f"/steps/{step['seq'] - 1}"


def test_derived_from_must_name_add_or_remove_ops_not_other_kinds():
    a = _sample()
    (step,) = _derived(a)
    impl = next(s for s in a["steps"] if s["kind"] == "field.add" and s["sourceOps"][0] in step["derivedFrom"])
    impl["kind"] = "field.set_property"  # the op the derived step names is now implemented by a property change
    issues = art.check(art.seal(a))
    assert any(i.code == "CMP-ART-004" and "add or remove" in i.message for i in issues), issues
