"""Link-target order (BPL-051, Q-691, ADR-0075): within phase 4 every Link target is added before the entities that link
to it, within phase 16 dependants are quarantined first. Only a `link` field into a new custom entity is a hard edge; a
relation is a soft preference dropped on a cycle; an entity that maps to a built-in engine type adds no edge. A hard
cycle among new entities is split: its smallest-pointer Link field moves to a later field.add (#391 review)."""
import copy

import cmp_helpers as H
from compiler import compile_blueprint, plan_view
from compiler.artifact import content_hash
from compiler.steps import _step, builtin_entities, link_targets, order_by_links

REPO = H.REPO


def _ent(eid, *targets, kind="entity.add", rels=()):
    fields = [{"id": "f_" + t, "type": "link", "target": t, "labels": {"ar": "x", "en": "x"}} for t in targets]
    relations = [{"id": "r_" + t, "target": t, "kind": "child_table", "cardinality": "many"} for t in rels]
    return _step(kind, {"kind": "entity", "id": eid}, "/entities/" + eid, "data_shape",
                 {"definition": {"id": eid, "fields": fields, "relations": relations}}, "/entities/" + eid)


def _order(steps, **kw):
    out, issues = order_by_links(steps, **kw)
    return [s["subject"]["id"] for s in out if s["kind"].startswith("entity.")], issues


def _split(steps, **kw):
    return [s["pointer"] for s in order_by_links(steps, **kw)[0] if s["kind"] == "field.add"]


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


def test_a_cycle_among_new_entities_is_split_at_its_smallest_pointer_link():
    steps = [_ent("a", "b"), _ent("b", "a"), _ent("c", "a"), _ent("d")]
    assert _order(steps) == (["a", "b", "c", "d"], [])
    out = order_by_links(steps)[0]
    add = next(s for s in out if s["kind"] == "field.add")
    assert add["pointer"] == "/entities/a/fields/f_b" and add["phase"] == 5 and add["sourceOps"] == ["/entities/a"]
    assert add["subject"] == {"kind": "field", "id": "f_b", "parents": [{"kind": "entity", "id": "a"}]}
    assert add["params"] == {"definition": {"id": "f_b", "type": "link", "target": "b", "labels": {"ar": "x", "en": "x"}}}
    assert next(s for s in out if s["pointer"] == "/entities/a")["params"]["definition"]["fields"] == []
    assert steps[0]["params"]["definition"]["fields"]  # the input steps are not changed


def test_the_fixture_adds_every_link_target_first():
    a = H.compile_fixture().artifact
    seq = _seq(a, "entity.add")
    assert seq["sales_quote"] < seq["sales_order"] and seq["sales_quote_line"] < seq["sales_quote"]
    custom = set(seq) - builtin_entities()
    for s in a["steps"]:
        if s["kind"] == "entity.add":
            own = s["subject"]["id"]
            assert all(seq[t] < s["seq"] for t in link_targets(s["params"]["definition"]) & custom - {own})
    adds = {s["seq"] for s in a["steps"] if s["kind"] == "entity.add" and s["subject"]["id"] in custom}
    assert all(not set(r["forwardRefs"]) & adds for r in plan_view(a) if r["kind"] == "entity.add")
    assert not [s for s in a["steps"] if s["kind"] == "field.add"]  # the fixture has no hard cycle


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


def _link(bp, eid, fid, target):
    next(e for e in bp["entities"] if e["id"] == eid)["fields"].append(
        {"id": fid, "type": "link", "target": target, "labels": {"ar": "س", "en": fid}})


def test_a_self_link_and_a_link_into_a_built_in_type_need_no_order():
    # item maps to a built-in engine type, which exists before any step; the line links item, item links the line
    bp = H.blueprint()
    _link(bp, "customer", "parent", "customer")
    assert H.compile_fixture(bp=bp).ok
    _link(bp, "item", "last_quote_line", "sales_quote_line")
    r = H.compile_fixture(bp=bp)
    assert r.ok, [str(i) for i in r.errors]
    seq = _seq(r.artifact, "entity.add")
    assert seq["sales_quote_line"] < seq["item"] and not [s for s in r.artifact["steps"] if s["kind"] == "field.add"]


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


def test_a_restore_cycle_is_broken_by_pointer_and_a_forward_add_cycle_is_split():
    steps = [_ent("b", "a"), _ent("a", "b")]
    out, issues = order_by_links(steps, restores=True)
    assert issues == [] and [s["subject"]["id"] for s in out] == ["a", "b"]
    assert order_by_links(steps)[1] == [] and _split(steps) == ["/entities/a/fields/f_b"]


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
    assert out["ok"] and out["result"]["status"] == "applied", {k: v for k, v in out["result"].items() if k != "postConditions"}
    assert not {"aa_cyc", "bb_cyc"} & {e["id"] for e in tk.export(h)["export"]["sections"]["entities"]}
    back = tk.rollback(h, a3, approvals={"rollbackApproved": tk.ulid(), "gateApproved": tk.ulid()})
    assert back["ok"] and back["result"]["status"] == "applied", back
    assert all(pc["passed"] for pc in back["result"]["postConditions"])
    assert tk.export(h)["exportHash"] == rev2_hash


def test_an_incremental_cycle_among_new_entities_is_split_and_its_inverse_quarantines_both():
    t, base = _revision(_new("aa_new", "bb_new"), _new("bb_new", "aa_new"))
    r = compile_blueprint(t, H.registry(), H.mapping(), environment="sandbox", base=base)
    assert r.ok, [str(i) for i in r.errors]
    assert [s["pointer"] for s in r.artifact["steps"] if s["kind"] in ("field.add", "field.reorder")] == \
        ["/entities/aa_new/fields/ref", "/entities/aa_new/fields"]
    assert sorted(_seq(r.artifact["inverse"], "entity.quarantine")) == ["aa_new", "bb_new"]
    assert not list(H.ARTIFACT_VALIDATOR.iter_errors(r.artifact))


# ------------------------------------------------------------------ partner review of #391 at 4fb365aa
def test_builtin_entities_list_is_versioned_and_covers_both_example_mappings():
    doc = H.load(REPO / "contracts" / "engine-builtin-entities.json")
    assert doc["version"] == "0.1.0" and doc["entities"] == sorted(set(doc["entities"]))
    assert builtin_entities() == frozenset(doc["entities"])
    for name in ("golden-path", "purchasing"):
        mp = H.load(REPO / "contracts" / "examples" / f"engine-mapping-{name}.json")
        assert {e["blueprintEntity"] for e in mp["entities"]} <= builtin_entities()


def test_high_a_child_relation_and_a_link_back_to_its_header_compile():
    # sales_quote (custom) has a child relation to sales_quote_line; the line now links back to its header
    bp = H.blueprint()
    _link(bp, "sales_quote_line", "quote", "sales_quote")
    r = H.compile_fixture(bp=bp)
    assert r.ok, [str(i) for i in r.errors]
    seq = _seq(r.artifact, "entity.add")
    assert seq["sales_quote"] < seq["sales_quote_line"]  # the hard Link wins, the relation preference is dropped
    assert not [s for s in r.artifact["steps"] if s["kind"] == "field.add"]


def test_high_a_price_list_line_linking_its_price_list_compiles():
    bp = H.blueprint()
    _link(bp, "price_list_item", "price_list", "price_list")
    assert H.compile_fixture(bp=bp).ok


def test_high_relations_alone_never_split_or_refuse():
    steps = [_ent("a", rels=("b",)), _ent("b", rels=("a",))]
    assert _order(steps) == (["b", "a"], []) and _split(steps) == []  # first preference kept, the closing one dropped
    # a relation preference is kept when it closes no cycle: b before a
    assert _order([_ent("a", rels=("b",)), _ent("b")]) == (["b", "a"], [])


def test_low_a_relation_induced_cycle_keeps_the_hard_link_and_drops_the_relation():
    # a -> b by relation (b first), b -> a by Link (a first): the Link wins and nothing is split
    steps = [_ent("a", rels=("b",)), _ent("b", "a"), _ent("c", rels=("a",))]
    assert _order(steps) == (["a", "b", "c"], []) and _split(steps) == []


def test_medium_a_built_in_and_a_new_custom_entity_linking_each_other_compile():
    bp = H.blueprint()
    bp["entities"].append(_new("segment", "customer"))
    _link(bp, "customer", "segment", "segment")
    r = H.compile_fixture(bp=bp)
    assert r.ok, [str(i) for i in r.errors]
    seq = _seq(r.artifact, "entity.add")
    assert seq["segment"] < seq["customer"] and not [s for s in r.artifact["steps"] if s["kind"] == "field.add"]


def test_low_two_built_in_types_with_mutual_links_compile_in_pointer_order():
    bp = H.blueprint()
    _link(bp, "customer", "default_item", "item")
    _link(bp, "item", "preferred_customer", "customer")
    r = H.compile_fixture(bp=bp)
    assert r.ok, [str(i) for i in r.errors]
    seq = _seq(r.artifact, "entity.add")
    assert seq["customer"] < seq["item"] and not [s for s in r.artifact["steps"] if s["kind"] == "field.add"]


def test_a_split_picks_one_link_per_cycle_by_smallest_pointer():
    steps = [_ent("a", "b"), _ent("b", "a"), _ent("c", "x", "d"), _ent("d", "c"), _ent("x", "a")]
    assert _split(steps) == ["/entities/a/fields/f_b", "/entities/c/fields/f_d"]
    assert _order(steps) == (["a", "b", "x", "c", "d"], [])
    assert _split(steps, restores=True) == []  # a restore re-activates stored types: broken by pointer, never split


def _cyc2(eid, target):
    e = _cyc(eid)
    e["fields"].insert(0, {"id": "to_" + target, "type": "link", "target": target, "labels": {"ar": "س", "en": "Ref"}})
    return e


def test_medium_an_initial_compile_with_a_link_cycle_succeeds_and_applies_on_the_fake_adapter():
    """No base (as Studio compiles): aa_cyc and bb_cyc link each other with their first field. The smallest-pointer
    Link (aa_cyc.to_bb_cyc) moves to a phase 5 field.add and a phase 6 field.reorder puts it back in first place."""
    from test_cmp_incremental import _compile, _fake, _inputs
    h, tk, adapter_id = _fake()
    bp, reg, mp = _inputs(adapter_id)
    bp["entities"] += [_cyc2("bb_cyc", "aa_cyc"), _cyc2("aa_cyc", "bb_cyc")]
    a = _compile(bp, None, reg, mp)
    assert not list(H.ARTIFACT_VALIDATOR.iter_errors(a))
    extra = [(s["kind"], s["pointer"], s["phase"]) for s in a["steps"] if s["pointer"].startswith("/entities/aa_cyc/")]
    assert extra == [("field.add", "/entities/aa_cyc/fields/to_bb_cyc", 5), ("field.reorder", "/entities/aa_cyc/fields", 6)]
    reorder = next(s for s in a["steps"] if s["kind"] == "field.reorder")
    assert reorder["params"] == {"order": ["to_bb_cyc", "title"], "previousOrder": ["title", "to_bb_cyc"]}
    seq = _seq(a, "entity.add")
    assert seq["aa_cyc"] < seq["bb_cyc"]
    assert tk.provision(h, blueprint_id=bp["meta"]["id"], target=a["engineTarget"], site_class="sandbox")["ok"]
    out = tk.apply_artifact(h, a)
    assert out["ok"] and out["result"]["status"] == "applied", {k: v for k, v in out["result"].items() if k != "postConditions"}
    assert all(pc["passed"] for pc in out["result"]["postConditions"])
    ents = {e["id"]: e for e in tk.export(h)["export"]["sections"]["entities"]}
    assert [f["id"] for f in ents["aa_cyc"]["fields"]] == ["to_bb_cyc", "title"]


def test_high_soft_relations_alone_keep_the_golden_order_of_4fb365aa(monkeypatch):
    """With the built-in list switched off, only the relation change applies: the fixture has no relation cycle, so every
    preference is kept and the artifact hash is the one #391 had at 4fb365aa. The built-in list moves it (ADR-0075)."""
    import compiler.steps as st
    monkeypatch.setattr(st, "builtin_entities", lambda: frozenset())
    a = H.compile_fixture().artifact
    assert a["integrity"]["contentHash"] == "sha256:028eba8229bc8a564c26cb7b65b43b007823b880ccf7ab68440496c67ab59427"
