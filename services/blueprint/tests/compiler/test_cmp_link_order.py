"""Link-target order (BPL-051, Q-691): within phase 4 every Link target is added before the entities that link to it,
within phase 16 dependants are quarantined first; a Link cycle among new entities refuses with CMP-ART-007."""
import copy

import cmp_helpers as H
from compiler import compile_blueprint, plan_view
from compiler.artifact import content_hash
from compiler.steps import _step, link_targets, order_by_links


def _ent(eid, *targets, kind="entity.add"):
    fields = [{"id": "f_" + t, "type": "link", "target": t, "labels": {"ar": "x", "en": "x"}} for t in targets]
    return _step(kind, {"kind": "entity", "id": eid}, "/entities/" + eid, "data_shape",
                 {"definition": {"id": eid, "fields": fields}}, "/entities/" + eid)


def _order(steps):
    out, issues = order_by_links(steps)
    return [s["subject"]["id"] for s in out], issues


def _seq(art, kind):
    return {s["subject"]["id"]: s["seq"] for s in art["steps"] if s["kind"] == kind}


def test_link_targets_cover_link_fields_and_relations():
    d = {"fields": [{"id": "a", "type": "link", "target": "x"}, {"id": "b", "type": "string"}],
         "relations": [{"id": "r", "target": "y", "cardinality": "many"}]}
    assert link_targets(d) == {"x", "y"}
    assert link_targets(None) == set()


def test_a_target_is_added_before_the_entity_that_links_to_it():
    # the #381 bench case: sales_order links sales_quote and sorts before it by pointer
    assert _order([_ent("sales_order", "sales_quote"), _ent("sales_quote")]) == (["sales_quote", "sales_order"], [])


def test_ties_break_by_pointer_and_unlinked_steps_keep_their_order():
    steps = [_ent("a"), _ent("b", "d"), _ent("c"), _ent("d")]
    assert _order(steps) == (["a", "c", "d", "b"], [])
    plain = [_ent("a"), _ent("b"), _ent("c")]
    assert order_by_links(plain) == (plain, [])


def test_a_self_link_and_a_link_to_an_entity_outside_the_phase_add_no_edge():
    assert _order([_ent("a", "a", "existing"), _ent("b", "a")]) == (["a", "b"], [])


def test_quarantine_removes_dependants_first():
    steps = [_ent("a", kind="entity.quarantine"), _ent("b", "c", kind="entity.quarantine"),
             _ent("c", kind="entity.quarantine"), _ent("d", "a", kind="entity.quarantine")]
    assert _order(steps) == (["b", "c", "d", "a"], [])


def test_a_cycle_among_new_entities_is_refused_naming_only_its_members():
    ids, issues = _order([_ent("a", "b"), _ent("b", "a"), _ent("c", "a"), _ent("d")])
    assert sorted(ids) == ["a", "b", "c", "d"]
    assert [(i.code, i.path) for i in issues] == [("CMP-ART-007", "/entities/a"), ("CMP-ART-007", "/entities/b")]


def test_the_fixture_adds_every_link_target_first():
    a = H.compile_fixture().artifact
    seq = _seq(a, "entity.add")
    assert seq["sales_quote"] < seq["sales_order"] and seq["price_list_item"] < seq["price_list"]
    for s in a["steps"]:
        if s["kind"] == "entity.add":
            assert all(seq[t] < s["seq"] for t in link_targets(s["params"]["definition"]) if t != s["subject"]["id"])
    adds = {s["seq"] for s in a["steps"] if s["kind"] == "entity.add"}
    assert all(not set(r["forwardRefs"]) & adds for r in plan_view(a) if r["kind"] == "entity.add")


def _new(eid, target):
    return {"id": eid, "labels": {"ar": "س", "en": eid}, "kind": "master", "provenance": {"source": "interview", "humanEdited": False},
            "fields": [{"id": "ref", "type": "link", "target": target, "labels": {"ar": "س", "en": "Ref"}},
                       {"id": "cust", "type": "link", "target": "customer", "labels": {"ar": "س", "en": "C"}}]}


def _revision(*entities):
    base = H.blueprint()
    t = copy.deepcopy(base)
    t["meta"]["revision"] = 2
    t["entities"] += list(entities)
    t["entities"][0]["labels"]["en"] = "Client"
    return t, base


def _unordered(monkeypatch):
    import compiler.incremental as inc
    import compiler.steps as st
    for mod in (st, inc):
        monkeypatch.setattr(mod, "order_by_links", lambda steps: (steps, []))


def test_steps_without_links_among_new_entities_compile_as_before(monkeypatch):
    t, base = _revision(_new("aa_new", "customer"), _new("bb_new", "supplier"))
    new = compile_blueprint(t, H.registry(), H.mapping(), environment="sandbox", base=base)
    init = H.compile_fixture().artifact
    _unordered(monkeypatch)
    old = compile_blueprint(t, H.registry(), H.mapping(), environment="sandbox", base=base)
    assert new.ok and new.artifact == old.artifact
    assert content_hash(new.artifact) == content_hash(old.artifact)
    # initial build: only the phase 4 entity.add steps move; every other step keeps its seq and content
    before = H.compile_fixture().artifact
    assert [s for s in init["steps"] if s["phase"] != 4] == [s for s in before["steps"] if s["phase"] != 4]
    assert sorted(s["pointer"] for s in init["steps"] if s["phase"] == 4) == \
        [s["pointer"] for s in before["steps"] if s["phase"] == 4]


def test_a_cycle_in_a_blueprint_is_refused_and_a_self_link_is_not():
    bp = H.blueprint()
    cust = next(e for e in bp["entities"] if e["id"] == "customer")
    cust["fields"].append({"id": "parent", "type": "link", "target": "customer", "labels": {"ar": "أصل", "en": "Parent"}})
    assert H.compile_fixture(bp=bp).ok
    item = next(e for e in bp["entities"] if e["id"] == "item")
    item["fields"].append({"id": "last_quote_line", "type": "link", "target": "sales_quote_line",
                           "labels": {"ar": "آخر سطر", "en": "Last quote line"}})
    r = H.compile_fixture(bp=bp)
    assert H.codes(r) == {"CMP-ART-007"}
    assert sorted(i.path for i in r.errors) == ["/entities/item", "/entities/sales_quote_line"]


def test_incremental_adds_order_targets_first_and_the_inverse_removes_dependants_first():
    t, base = _revision(_new("aa_dep", "zz_tgt"), _new("zz_dep", "aa_tgt"), _new("aa_tgt", "customer"),
                        _new("zz_tgt", "customer"))
    r = compile_blueprint(t, H.registry(), H.mapping(), environment="sandbox", base=base)
    assert r.ok, [str(i) for i in r.errors]
    fwd, inv = _seq(r.artifact, "entity.add"), _seq(r.artifact["inverse"], "entity.quarantine")
    assert sorted(fwd, key=fwd.get) == ["aa_tgt", "zz_dep", "zz_tgt", "aa_dep"]
    assert sorted(inv, key=inv.get) == ["aa_dep", "zz_dep", "aa_tgt", "zz_tgt"]
