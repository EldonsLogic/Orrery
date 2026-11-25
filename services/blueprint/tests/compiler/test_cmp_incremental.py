"""Incremental compile (BPL-039): base-to-target artifact with an embedded inverse, checked against the contract and
round-tripped through the fake adapter (forward apply, then rollback restores the base export). Synthetic data only."""
import copy
import hashlib

import pytest

import cmp_helpers as H
from bpdiff import diff, invert
from compiler import to_bytes
from compiler.incremental import irreversible_reason


def _inputs(adapter_id=None):
    """The fixture, optionally re-targeted at the fake adapter with attachment fields dropped (as in test_cmp_props)."""
    bp, mp, mans = H.blueprint(), H.mapping(), copy.deepcopy(H.manifests())
    if adapter_id:
        bp["meta"]["engineTarget"]["adapter"] = mp["engine"]["adapter"] = adapter_id
        for m in mans:
            m["engineCompatibility"]["adapter"] = adapter_id
        for e in bp["entities"]:
            e["fields"] = [f for f in e["fields"] if f["type"] != "attachment"]
    return bp, H.registry(mans), mp


def _entity(bp, eid):
    return next(e for e in bp["entities"] if e["id"] == eid)


def _field(bp, eid, fid):
    return next(f for f in _entity(bp, eid)["fields"] if f["id"] == fid)


def _edit(base):
    """Revision 2: one of each reversible change kind."""
    t = copy.deepcopy(base)
    t["meta"]["revision"] = 2
    cust = _entity(t, "customer")
    cust["labels"]["en"] = "Client"                                        # entity.set_property
    cust["fields"].append({"id": "notes", "type": "text", "labels": {"ar": "ملاحظات", "en": "Notes"}})  # field.add
    _field(t, "customer", "customer_name")["maxLength"] = 200               # field.set_property, widening
    supp = _entity(t, "supplier")
    supp["fields"] = [f for f in supp["fields"] if f["id"] != "city"]  # field.quarantine
    t["company"]["tradeName"]["en"] = "Al Waha Trading"                    # settings.set
    t["workflows"][0]["labels"]["en"] = "Order flow"                      # workflow.upsert
    t["locations"].append({"id": "wh_dammam", "kind": "warehouse", "labels": {"ar": "مستودع الدمام", "en": "Dammam"}})
    return t


def _compile(target, base, reg, mp):
    r = H.compile_fixture(bp=target, reg=reg, mp=mp) if base is None else \
        __import__("compiler").compile_blueprint(target, reg, mp, environment="sandbox", base=base)
    assert r.ok, [str(i) for i in r.errors]
    return r.artifact


def test_forward_and_inverse_follow_the_schema_and_the_validator_rules():
    base, reg, mp = _inputs()
    fwd = _compile(_edit(base), base, reg, mp)
    inv = fwd["inverse"]
    assert not list(H.ARTIFACT_VALIDATOR.iter_errors(fwd))
    assert fwd["kind"] == "forward" and inv["kind"] == "inverse" and inv["inverse"] is None
    assert fwd["blueprint"]["base"] == inv["blueprint"]["target"] and fwd["blueprint"]["target"] == inv["blueprint"]["base"]
    assert fwd["blueprint"]["base"]["hash"] == H.sha(base) and inv["engineTarget"] == fwd["engineTarget"]
    d = diff(base, _edit(base))
    assert fwd["blueprint"]["diffHash"] == H.sha(d) and inv["blueprint"]["diffHash"] == H.sha(invert(d))
    for a, src in ((fwd, d), (inv, invert(d))):
        body = {k: v for k, v in a.items() if k not in ("artifactId", "integrity")}
        assert a["integrity"]["contentHash"] == H.sha(body) and a["artifactId"] == "art_" + H.sha(body)[7:39]
        covered = sorted([p for s in a["steps"] for p in s["sourceOps"]] + [s["pointer"] for s in a["skippedOps"]])
        assert covered == sorted(op["pointer"] for op in src["ops"])  # every op exactly once
        assert [s["seq"] for s in a["steps"]] == list(range(1, len(a["steps"]) + 1))
    assert fwd["risk"]["irreversibleSteps"] == 0  # the widening is rollbackable; its inverse narrows (same rules)
    assert inv["risk"]["irreversibleSteps"] == 1
    kinds = {s["kind"] for s in fwd["steps"]}
    assert {"entity.set_property", "field.add", "field.set_property", "field.quarantine", "settings.set",
            "workflow.upsert", "location.upsert"} <= kinds
    assert {"field.add", "field.quarantine", "location.disable"} <= {s["kind"] for s in inv["steps"]}


def test_compile_is_deterministic():
    base, reg, mp = _inputs()
    a = to_bytes(_compile(_edit(base), base, reg, mp))
    b = to_bytes(_compile(_edit(copy.deepcopy(base)), copy.deepcopy(base), reg, mp))
    assert a == b and hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()


def test_an_unchanged_blueprint_gives_an_empty_artifact():
    base, reg, mp = _inputs()
    a = _compile(copy.deepcopy(base), base, reg, mp)
    assert not list(H.ARTIFACT_VALIDATOR.iter_errors(a))
    assert a["blueprint"]["base"] == a["blueprint"]["target"]
    for x in (a, a["inverse"]):
        assert x["steps"] == [] and x["skippedOps"] == [] and x["postConditions"] == [] and x["risk"]["total"] == 0


@pytest.mark.parametrize("prop, before, after, reason", [
    ("precision", 2, 0, "precision_reduction"), ("type", "money", "decimal", "type_change")])
def test_a_step_that_loses_data_marks_the_artifact_not_rollbackable(prop, before, after, reason):
    base, reg, mp = _inputs()
    t = copy.deepcopy(base)
    t["meta"]["revision"] = 2
    f = _field(t, "customer", "credit_limit")
    assert f[prop] == before
    f[prop] = after
    a = _compile(t, base, reg, mp)
    bad = [s for s in a["steps"] if not s["reversible"]]
    assert [irreversible_reason(s) for s in bad] == [reason] and a["risk"]["irreversibleSteps"] == 1
    assert a["inverse"] is not None and not list(H.ARTIFACT_VALIDATOR.iter_errors(a))


def test_widening_is_reversible_and_narrowing_is_not():
    step = {"kind": "field.set_property", "params": {"property": "/maxLength", "before": 140, "after": 200}}
    assert irreversible_reason(step) is None
    assert irreversible_reason({**step, "params": {"property": "/maxLength", "after": 20}}) == "length_reduction"
    assert irreversible_reason({**step, "params": {"property": "/maxLength", "before": 20}}) is None


@pytest.mark.parametrize("edit, code", [
    (lambda t: t["meta"].update(id="another-blueprint"), "CMP-INC-001"),
    (lambda t: t["meta"]["engineTarget"].update(versionSet="set-example-2"), None),  # the registry refuses first
    (lambda t: t["meta"].update(revision=0), None),  # invalid Blueprint: the validator refuses first
    (lambda t: t["entities"].reverse(), "CMP-ART-001"),  # reorder of an unordered collection has no step kind
])
def test_refusals(edit, code):
    base, reg, mp = _inputs()
    t = copy.deepcopy(base)
    t["meta"]["revision"] = 2
    edit(t)
    r = __import__("compiler").compile_blueprint(t, reg, mp, environment="sandbox", base=base)
    assert not r.ok and r.artifact is None and r.errors
    if code:
        assert code in {i.code for i in r.errors}


def test_a_lower_target_revision_is_refused():
    base, reg, mp = _inputs()
    later = copy.deepcopy(base)
    later["meta"]["revision"] = 3
    r = __import__("compiler").compile_blueprint(base, reg, mp, environment="sandbox", base=later)
    assert "CMP-INC-003" in {i.code for i in r.errors}


# ------------------------------------------------------------------ round trip through the fake adapter (BPL-025)
def _fake():
    harness = pytest.importorskip("adapter.harness")
    tk = pytest.importorskip("adapter.testkit")
    return harness.FakeHarness(), tk, pytest.importorskip("adapter.fake").ADAPTER_ID


def _rollback_approvals(tk):
    """The inverse's semantic step (maxLength back to 140) needs the storage gate (contract 5.7)."""
    return {"rollbackApproved": tk.ulid(), "gateApproved": tk.ulid()}


def test_forward_then_rollback_restores_the_base_export_on_the_fake_adapter():
    h, tk, adapter_id = _fake()
    base, reg, mp = _inputs(adapter_id)
    initial = _compile(base, None, reg, mp)
    fwd = _compile(_edit(base), base, reg, mp)
    assert tk.provision(h, blueprint_id=base["meta"]["id"], target=initial["engineTarget"], site_class="sandbox")["ok"]
    assert tk.apply_artifact(h, initial)["result"]["status"] == "applied"
    base_hash = tk.export(h)["exportHash"]
    out = tk.apply_artifact(h, fwd)
    assert out["ok"] and out["result"]["status"] == "applied", out
    assert all(pc["passed"] for pc in out["result"]["postConditions"])
    assert tk.export(h)["exportHash"] != base_hash
    back = tk.rollback(h, fwd, approvals=_rollback_approvals(tk))
    assert back["ok"] and back["result"]["status"] == "applied", back
    assert back["result"]["artifactId"] == fwd["inverse"]["artifactId"]
    assert tk.export(h)["exportHash"] == base_hash
    assert tk.status(h)["applied"]["artifactId"] == initial["artifactId"]


def test_the_fake_adapter_refuses_to_roll_back_an_irreversible_artifact():
    h, tk, adapter_id = _fake()
    base, reg, mp = _inputs(adapter_id)
    t = copy.deepcopy(base)
    t["meta"]["revision"] = 2
    _field(t, "customer", "credit_limit")["precision"] = 0
    initial, fwd = _compile(base, None, reg, mp), _compile(t, base, reg, mp)
    tk.provision(h, blueprint_id=base["meta"]["id"], target=initial["engineTarget"], site_class="sandbox")
    tk.apply_artifact(h, initial)
    assert tk.apply_artifact(h, fwd)["result"]["status"] == "applied"
    back = tk.rollback(h, fwd)
    err = tk.rejected_error(back)
    assert err["code"] == "rollback_not_possible" and err["details"]["reasonCode"] == "irreversible_step"


def _opts(t):
    return _field(t, "customer", "customer_type")["options"]


def _drop_vat_summary(t):
    t["reports"] = [r for r in t["reports"] if r["id"] != "vat_summary"]
    for role in t["roles"]:
        home = role.get("homeView", {})
        if "vat_summary" in home.get("reports", []):
            home["reports"].remove("vat_summary")


@pytest.mark.parametrize("edit, kind", [
    (lambda t: _opts(t).append({"value": "ngo", "labels": {"ar": "جمعية", "en": "NGO"}}), "option.add"),
    (lambda t: _opts(t).reverse(), "option.reorder"),
    (lambda t: _entity(t, "supplier")["fields"].reverse(), "field.reorder"),
    (lambda t: t["roles"][0]["labels"].update(en="Renamed"), "role.upsert"),
    (_drop_vat_summary, "report.disable"),
])
def test_each_kind_compiles_with_an_inverse_that_names_the_same_subject(edit, kind):
    base, reg, mp = _inputs()
    t = copy.deepcopy(base)
    t["meta"]["revision"] = 2
    edit(t)
    a = _compile(t, base, reg, mp)
    assert not list(H.ARTIFACT_VALIDATOR.iter_errors(a)) and kind in {s["kind"] for s in a["steps"]}
    assert {s["pointer"] for s in a["steps"]} == {s["pointer"] for s in a["inverse"]["steps"]}


# ------------------------------------------------------------------ review fixes (BPL-039)
def test_an_unknown_op_kind_is_refused_not_read_as_a_property_change():
    from compiler.incremental import _classify, steps_from_diff
    base, _, _ = _inputs()
    t = copy.deepcopy(base)
    t["meta"]["revision"] = 2
    _entity(t, "customer")["labels"]["en"] = "Client"
    d = diff(base, t)
    op = next(o for o in d["ops"] if o["op"] == "replace" and o["path"][:2] == ["entities", "customer"])
    assert _classify(op, base, t)[0] == "entity.set_property"
    moved = {**op, "op": "move"}
    assert _classify(moved, base, t) == ""
    steps, _, issues = steps_from_diff({**d, "ops": [moved]}, base, t)
    assert steps == [] and [i.code for i in issues] == ["CMP-ART-001"]


def test_an_engine_target_change_is_refused_when_both_revisions_validate():
    """Both revisions pass every gate (manifests tested against both version sets, draft mapping UNVERIFIED), so only
    CMP-INC-002 stops it."""
    from compiler import compile_blueprint
    base, _, mp = _inputs()
    mans = copy.deepcopy(H.manifests())
    for m in mans:
        m["engineCompatibility"]["testedAgainst"].append("set-example-2")
    reg = H.registry(mans)
    t = copy.deepcopy(base)
    t["meta"]["revision"] = 2
    t["meta"]["engineTarget"]["versionSet"] = "set-example-2"
    assert compile_blueprint(base, reg, mp, environment="sandbox").ok
    assert compile_blueprint(t, reg, mp, environment="sandbox").ok
    r = compile_blueprint(t, reg, mp, environment="sandbox", base=base)
    assert not r.ok and r.artifact is None and [i.code for i in r.errors] == ["CMP-INC-002"]


def test_equal_precision_or_length_is_not_a_cut_and_one_less_is():
    mk = lambda prop, b, a: {"kind": "field.set_property", "params": {"property": prop, "before": b, "after": a}}  # noqa: E731
    for prop in ("/precision", "/maxLength"):
        assert irreversible_reason(mk(prop, 5, 5)) is None
        assert irreversible_reason(mk(prop, 5, 6)) is None
    assert irreversible_reason(mk("/precision", 5, 4)) == "precision_reduction"
    assert irreversible_reason(mk("/maxLength", 5, 4)) == "length_reduction"


@pytest.mark.parametrize("kind", ["field.set_property", "relation.set_property"])
def test_a_link_target_change_is_flagged(kind):
    step = {"kind": kind, "params": {"property": "/target", "before": "customer", "after": "supplier"}}
    assert irreversible_reason(step) == "link_target_change"


# contract 9.4 phases, written out independently of compiler.steps
PHASES = {"settings.set": 1, "component.enable": 2, "component.configure": 2, "location.upsert": 3, "entity.add": 4,
          "field.add": 5, "relation.add": 5, "option.add": 5, "binding.add": 5, "field.reorder": 6, "option.reorder": 6,
          "entity.set_property": 6, "field.set_property": 6, "relation.set_property": 6, "binding.set_property": 6,
          "role.upsert": 7, "workflow.upsert": 8, "approval.upsert": 9, "report.upsert": 10, "report.disable": 11,
          "approval.disable": 12, "workflow.disable": 13, "role.disable": 14, "binding.disable": 15,
          "option.quarantine": 15, "relation.quarantine": 15, "field.quarantine": 15, "entity.quarantine": 16,
          "location.disable": 17, "component.disable": 18}


def test_steps_are_ordered_by_phase_then_pointer_then_kind_per_contract_9_4():
    base, reg, mp = _inputs()
    t = _edit(base)
    _entity(t, "supplier")["fields"].reverse()
    t["roles"][0]["labels"]["en"] = "Renamed"
    _drop_vat_summary(t)
    a = _compile(t, base, reg, mp)
    for art in (a, a["inverse"]):
        steps = art["steps"]
        assert len(steps) > 8 and [s["seq"] for s in steps] == list(range(1, len(steps) + 1))
        assert all(s["phase"] == PHASES[s["kind"]] for s in steps)
        assert [(s["phase"], s["pointer"], s["kind"]) for s in steps] == \
            sorted((s["phase"], s["pointer"], s["kind"]) for s in steps)
    # phase 6 holds kinds whose alphabetical order differs from their pointer order: pointer must win
    p6 = [s for s in a["steps"] if s["phase"] == 6]
    assert [s["pointer"] for s in p6] == sorted(s["pointer"] for s in p6)
    assert [s["kind"] for s in p6] != sorted(s["kind"] for s in p6)


def test_the_inverse_lists_the_base_components_not_the_target_ones():
    base, reg_, mp = _inputs()
    mans = copy.deepcopy(H.manifests())
    extra = copy.deepcopy(next(m for m in mans if m["id"] == "core.customer"))
    extra["id"] = "core.extra"
    reg = H.registry(mans + [extra])
    t = copy.deepcopy(base)
    t["meta"]["revision"] = 2
    t["components"].append({"id": "core.extra", "versionRange": "^0.1.0",
                            "provenance": copy.deepcopy(t["components"][0]["provenance"])})
    a = _compile(t, base, reg, mp)
    ids = lambda x: {c["id"] for c in x["components"]}  # noqa: E731
    assert "core.extra" in ids(a) and "core.extra" not in ids(a["inverse"])
    assert ids(a["inverse"]) == {c["id"] for c in base["components"]}
    assert "component.enable" in {s["kind"] for s in a["steps"]}


def test_a_step_takes_the_highest_impact_of_its_coalesced_ops():
    from compiler.incremental import _SEVERITY, steps_from_diff
    base, _, _ = _inputs()
    t = copy.deepcopy(base)
    t["meta"]["revision"] = 2
    wf = t["workflows"][0]
    wf["labels"]["en"] = "Order flow"
    wf["states"][0]["labels"]["en"] = "Changed state"
    d = diff(base, t)
    ops = [o for o in d["ops"] if o["path"][:2] == ["workflows", wf["id"]]]
    assert len(ops) >= 2
    lo, hi = _SEVERITY[0], _SEVERITY[-1]
    for order in (ops, ops[::-1]):
        marked = [{**o, "impact": hi if i == 1 else lo} for i, o in enumerate(order)]
        steps, _, _ = steps_from_diff({**d, "ops": marked}, base, t)
        step = next(s for s in steps if s["kind"] == "workflow.upsert")
        assert len(step["sourceOps"]) == len(ops) and step["impact"] == hi
