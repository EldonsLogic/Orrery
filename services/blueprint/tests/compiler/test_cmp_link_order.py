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
        monkeypatch.setattr(mod, "order_by_links", lambda steps, restores=False: (steps, []))


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


# ------------------------------------------------------------------ re-review of #391 (RULES 42 findings)
def test_link_targets_count_only_link_fields_and_every_relation_kind():
    d = {"fields": [{"id": "a", "type": "link", "target": "x"}, {"id": "b", "type": "string", "target": "not_a_link"},
                    {"id": "c", "target": "no_type"}],
         "relations": [{"id": "r", "target": "y", "cardinality": "one"},
                       {"id": "t", "target": "z", "kind": "child_table", "cardinality": "many"}]}
    assert link_targets(d) == {"x", "y", "z"}


def test_a_cycle_refusal_names_only_entities_on_a_cycle_not_a_bridge_between_cycles():
    # a <-> b and c <-> d are cycles; x links a and c links x, so x sits between them but is on no cycle
    ids, issues = _order([_ent("a", "b"), _ent("b", "a"), _ent("c", "x", "d"), _ent("d", "c"), _ent("x", "a")])
    assert sorted(ids) == ["a", "b", "c", "d", "x"]
    assert [i.path for i in issues] == ["/entities/a", "/entities/b", "/entities/c", "/entities/d"]
    assert all("(a, b, c, d)" in i.message for i in issues)


def test_a_restore_cycle_is_broken_by_pointer_and_a_forward_add_cycle_still_refuses():
    steps = [_ent("b", "a"), _ent("a", "b")]
    out, issues = order_by_links(steps, restores=True)
    assert issues == [] and [s["subject"]["id"] for s in out] == ["a", "b"]
    assert {i.code for i in order_by_links(steps)[1]} == {"CMP-ART-007"}


def _cyc(eid):
    return {"id": eid, "labels": {"ar": "س", "en": eid}, "kind": "master",
            "provenance": {"source": "interview", "humanEdited": False},
            "fields": [{"id": "title", "type": "string", "labels": {"ar": "س", "en": "Title"}}]}


def test_removing_a_link_cycle_compiles_and_rolls_back_on_the_fake_adapter():
    """Rev 1 adds A and B; rev 2 adds the Links A->B and B->A as field.add (both exist); rev 3 removes both. The
    quarantine and its inverse (a restore) both break the cycle by pointer: quarantine keeps the stored entity and a
    restore re-activates it, so no Link ever points at a missing type."""
    from test_cmp_incremental import _compile, _fake, _inputs
    h, tk, adapter_id = _fake()
    base, reg, mp = _inputs(adapter_id)
    rev1 = copy.deepcopy(base)
    rev1["entities"] += [_cyc("bb_cyc"), _cyc("aa_cyc")]
    rev2 = copy.deepcopy(rev1)
    rev2["meta"]["revision"] = 2
    for eid, tgt in (("aa_cyc", "bb_cyc"), ("bb_cyc", "aa_cyc")):
        next(e for e in rev2["entities"] if e["id"] == eid)["fields"].append(
            {"id": "to_" + tgt, "type": "link", "target": tgt, "labels": {"ar": "س", "en": "Ref"}})
    rev3 = copy.deepcopy(rev2)
    rev3["meta"]["revision"] = 3
    rev3["entities"] = [e for e in rev3["entities"] if e["id"] not in ("aa_cyc", "bb_cyc")]
    a1, a2, a3 = _compile(rev1, None, reg, mp), _compile(rev2, rev1, reg, mp), _compile(rev3, rev2, reg, mp)
    fwd, inv = _seq(a3, "entity.quarantine"), _seq(a3["inverse"], "entity.add")
    assert sorted(fwd, key=fwd.get) == ["aa_cyc", "bb_cyc"] and sorted(inv, key=inv.get) == ["aa_cyc", "bb_cyc"]
    assert tk.provision(h, blueprint_id=base["meta"]["id"], target=a1["engineTarget"], site_class="sandbox")["ok"]
    for a in (a1, a2):
        assert tk.apply_artifact(h, a)["result"]["status"] == "applied"
    rev2_hash = tk.export(h)["exportHash"]
    out = tk.apply_artifact(h, a3)
    assert out["ok"] and out["result"]["status"] == "applied", out
    assert not {"aa_cyc", "bb_cyc"} & {e["id"] for e in tk.export(h)["export"]["sections"]["entities"]}
    back = tk.rollback(h, a3, approvals={"rollbackApproved": tk.ulid(), "gateApproved": tk.ulid()})
    assert back["ok"] and back["result"]["status"] == "applied", back
    assert all(pc["passed"] for pc in back["result"]["postConditions"])
    assert tk.export(h)["exportHash"] == rev2_hash


def test_an_incremental_cycle_among_new_entities_is_still_refused():
    t, base = _revision(_new("aa_new", "bb_new"), _new("bb_new", "aa_new"))
    r = compile_blueprint(t, H.registry(), H.mapping(), environment="sandbox", base=base)
    assert H.codes(r) == {"CMP-ART-007"}
    assert sorted(i.path for i in r.errors) == ["/entities/aa_new", "/entities/bb_new"]
