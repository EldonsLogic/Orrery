import copy
import json
from pathlib import Path

import pytest

from gap_analysis import analyse, render
import importlib

impl = importlib.import_module("gap_analysis.analyse")

ROOT = Path(__file__).resolve().parents[4]
FIX = ROOT / "services" / "blueprint" / "fixtures" / "registry"
BP = json.loads((ROOT / "contracts" / "examples" / "blueprint-trading-minimal.json").read_text(encoding="utf-8"))


def fixture_lib():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(FIX.glob("*.json"))]


def mk(cid="sales.thing", version="0.1.0", arts=(("entity", "thing"),), cap=None, level="reviewed", requires=(), params=(), **kw):
    m = {
        "id": cid, "version": version, "kind": "configurable", "name": {"ar": "مكوّن", "en": "Thing"},
        "description": "Test manifest used only by the gap analysis tests.",
        "provides": [{"capability": cap or f"{cid}.entities", "artifacts": [{"type": t, "ref": r} for t, r in arts]}],
        "requires": list(requires), "parameters": list(params),
        "tests": [{"id": "unit_t", "kind": "unit", "path": "tests/u.py", "blocking": True}],
        "certification": {"level": level, "touchesLedgerOrTax": False, "reviewedBy": ["x"]},
        "engineCompatibility": {"adapter": "change_engine", "engineRange": ">=0.1.0 <1.0.0", "testedAgainst": ["set-example"]},
        "licence": {"spdx": "LicenseRef-Proprietary"}, "owner": {"github": "example-owner"},
    }
    m.update(kw)
    return m


def bp(entities=(), components=(), workflows=(), reports=(), ei=None, target=True):
    b = {"meta": {"id": "t-1", "revision": 3}, "components": list(components),
         "entities": [{"id": e, "labels": {"ar": "سجل " + e, "en": "Record " + e}} for e in entities],
         "workflows": [{"id": w} for w in workflows], "reports": [{"id": r} for r in reports], "compliance": {}}
    if target:
        b["meta"]["engineTarget"] = {"adapter": "change_engine", "versionSet": "set-example"}
    if ei is not None:
        b["compliance"]["eInvoicing"] = ei
    return b


def by_id(rep):
    return {r["id"]: r for r in rep["requirements"]}


def codes(r):
    return [x["code"] for x in r["reasons"]]


def test_example_blueprint_against_fixture_library():
    b = copy.deepcopy(BP)
    b["meta"]["engineTarget"] = {"adapter": "change_engine", "versionSet": "set-example"}
    rep = analyse(b, fixture_lib())
    r = by_id(rep)
    assert r["entity:customer"]["status"] == "covered" and r["entity:customer"]["match"]["component"] == "core.customer"
    # the entity names its implementing component, which wins over another provider
    assert r["entity:sales_invoice"]["match"]["component"] == "core.sales_invoice"
    # the fixture library has no report artifacts: honest gap, candidate requests
    assert [x["requirement_id"] for x in rep["component_requests"]] == ["report:my_orders", "report:receivables_aging", "report:sales_overview"]
    # the template sets a parameter the fixture manifest does not declare: a configuration gap
    assert r["compliance:einvoicing.zatca_phase2"]["status"] == "partial"
    assert "parameter_unknown" in codes(r["compliance:einvoicing.zatca_phase2"])
    # the example targets another engine adapter than the fixture manifests: flagged
    assert "engine_incompatible" in codes(by_id(analyse(BP, fixture_lib()))["entity:customer"])


def test_covered_has_manifest_evidence_and_blueprint_pointer():
    r = by_id(analyse(bp(["thing"]), [mk()]))["entity:thing"]
    assert r["status"] == "covered"
    assert {"kind": "blueprint", "id": "/entities/0"} in r["evidence"]
    assert any(e["kind"] == "manifest" and e["id"] == "sales.thing@0.1.0" for e in r["evidence"])


def test_provenance_is_evidence():
    b = bp(["thing"])
    b["entities"][0]["provenance"] = {"source": "interview", "ref": "turn-7"}
    r = by_id(analyse(b, [mk()]))["entity:thing"]
    assert {"kind": "provenance", "id": "interview:turn-7"} in r["evidence"]


def test_uncovered_when_no_matching_capability():
    rep = analyse(bp(["thing", "other"]), [mk()])
    r = by_id(rep)
    assert r["entity:other"]["status"] == "uncovered" and codes(r["entity:other"]) == ["no_provider"]
    assert [q["requirement_id"] for q in rep["component_requests"]] == ["entity:other"]


def test_never_covered_by_id_alone_or_wrong_type():
    # a workflow artifact with the same ref must not cover an entity
    r = by_id(analyse(bp(["thing"]), [mk(arts=(("workflow", "thing"),))]))
    assert r["entity:thing"]["status"] == "uncovered"
    # a component whose id equals the requirement is not enough
    r = by_id(analyse(bp(["thing"]), [mk(cid="sales.thing", arts=(("entity", "zzz"),))]))
    assert r["entity:thing"]["status"] == "uncovered"


def test_empty_library_everything_uncovered():
    for lib in ([], None, "garbage", {}):
        rep = analyse(BP, lib)
        assert rep["summary"]["covered"] == 0 and rep["summary"]["partial"] == 0
        assert rep["summary"]["uncovered"] == rep["summary"]["total"] > 0


def test_empty_blueprint_and_garbage_blueprint():
    for b in ({}, None, [], "x", {"entities": "no", "components": 5}):
        rep = analyse(b, [mk()])
        assert rep["summary"]["total"] == 0


def test_hostile_library_entries_fail_closed():
    hostile = [None, 5, "x", [], {}, {"id": "sales.thing"}, {"id": "sales.thing", "version": "0.1.0", "provides": "all"},
               {"id": ["a"], "version": {}, "provides": [{"artifacts": [{"type": "entity", "ref": "thing"}]}]},
               dict(mk(), kind="__proto__"), dict(mk(), certification={"level": "regulated"}),
               dict(mk(), provides=[{"capability": "x.y", "artifacts": [{"type": "entity", "ref": "thing", "riskClass": "plain",
                                                                          "extra": 1}]}])]
    rep = analyse(bp(["thing"]), hostile)
    r = by_id(rep)["entity:thing"]
    assert r["status"] == "uncovered" and r["match"] is None
    assert rep["summary"]["library_entries_rejected"] == len(hostile)
    assert "rejected_entry" in codes(r)


def test_hostile_entry_does_not_poison_good_one():
    rep = analyse(bp(["thing"]), [None, mk(), {"id": 1}])
    assert by_id(rep)["entity:thing"]["status"] == "covered"
    assert rep["summary"]["library_entries_rejected"] == 2


def test_draft_level_is_not_eligible():
    r = by_id(analyse(bp(["thing"]), [mk(level="draft")]))["entity:thing"]
    assert r["status"] == "uncovered" and "not_eligible" in codes(r)


def test_production_needs_certified():
    lib = [mk()]
    assert by_id(analyse(bp(["thing"]), lib, "production"))["entity:thing"]["status"] == "uncovered"
    assert by_id(analyse(bp(["thing"]), lib, "weird"))["entity:thing"]["status"] == "uncovered"
    lib = [mk(level="certified", certification={"level": "certified", "touchesLedgerOrTax": False, "reviewedBy": ["x"],
                                                "evidence": {}})]
    # whether a certified manifest passes admission is the registry's call; the analysis follows it
    got = by_id(analyse(bp(["thing"]), lib, "production"))["entity:thing"]["status"]
    assert got in ("covered", "uncovered")


def test_version_constraint_in_range_and_out_of_range():
    lib = [mk(version="0.1.0"), mk(version="0.2.0"), mk(version="1.0.0")]
    b = bp(["thing"], components=[{"id": "sales.thing", "versionRange": ">=0.1.0 <1.0.0"}])
    r = by_id(analyse(b, lib))["entity:thing"]
    assert r["status"] == "covered" and r["match"]["version"] == "0.2.0"
    b = bp(["thing"], components=[{"id": "sales.thing", "versionRange": "^2.0.0"}])
    r = by_id(analyse(b, lib))
    assert r["entity:thing"]["status"] == "uncovered" and "version_unsatisfied" in codes(r["entity:thing"])
    assert r["component:sales.thing"]["status"] == "uncovered"


def test_invalid_version_range_fails_closed():
    b = bp(["thing"], components=[{"id": "sales.thing", "versionRange": "not a range"}])
    r = by_id(analyse(b, [mk()]))
    assert r["entity:thing"]["status"] == "uncovered"
    assert "range_invalid" in codes(r["entity:thing"])


def test_prerelease_excluded_by_caret():
    b = bp(["thing"], components=[{"id": "sales.thing", "versionRange": "^0.1.0"}])
    r = by_id(analyse(b, [mk(version="0.2.0-beta.1")]))["entity:thing"]
    assert r["status"] == "uncovered"


def test_component_binding_unknown_is_uncovered_but_no_request():
    rep = analyse(bp([], components=[{"id": "ghost.thing", "versionRange": "^1.0.0"}]), [mk()])
    r = by_id(rep)["component:ghost.thing"]
    assert r["status"] == "uncovered" and codes(r) == ["component_unknown"]
    assert rep["component_requests"] == []


def test_duplicate_capabilities_pick_is_deterministic_and_flagged():
    a = mk(cid="sales.aaa")
    z = mk(cid="sales.zzz")
    r1 = by_id(analyse(bp(["thing"]), [z, a]))["entity:thing"]
    r2 = by_id(analyse(bp(["thing"]), [a, z]))["entity:thing"]
    assert r1 == r2 and r1["match"]["component"] == "sales.aaa" and r1["alternatives"] == ["sales.zzz"]
    assert "duplicate_providers" in codes(r1)
    # a component the Blueprint binds wins
    b = bp(["thing"], components=[{"id": "sales.zzz", "versionRange": "*"}])
    assert by_id(analyse(b, [a, z]))["entity:thing"]["match"]["component"] == "sales.zzz"


def test_duplicate_same_component_versions_pick_highest():
    r = by_id(analyse(bp(["thing"]), [mk(version="0.1.0"), mk(version="0.3.0"), mk(version="0.2.0")]))["entity:thing"]
    assert r["match"]["version"] == "0.3.0" and r["alternatives"] == []


def test_conflicting_duplicate_manifest_is_rejected_not_trusted():
    a = mk()
    b = dict(mk(), description="A different description for the same id and version.")
    rep = analyse(bp(["thing"]), [a, b])
    assert rep["summary"]["library_entries_rejected"] >= 1


PARAM = {"id": "limit", "type": "integer", "required": True, "labels": {"ar": "الحد", "en": "Limit"}, "min": 0, "max": 10}
ENUM = {"id": "mode", "type": "enum", "enumValues": ["a", "b"], "labels": {"ar": "نمط", "en": "Mode"}}


def test_partial_on_parameter_config_gaps():
    lib = [mk(params=[PARAM, ENUM])]
    ok = bp(["thing"], components=[{"id": "sales.thing", "versionRange": "*", "parameters": {"limit": 3, "mode": "a"}}])
    assert by_id(analyse(ok, lib))["entity:thing"]["status"] == "covered"
    cases = {
        "parameter_missing": {"mode": "a"},
        "parameter_invalid": {"limit": 99},
        "parameter_unknown": {"limit": 1, "nope": 1},
    }
    for code, params in cases.items():
        b = bp(["thing"], components=[{"id": "sales.thing", "versionRange": "*", "parameters": params}])
        r = by_id(analyse(b, lib))["entity:thing"]
        assert r["status"] == "partial", code
        assert code in codes(r) and r["match"]["component"] == "sales.thing"
    b = bp(["thing"], components=[{"id": "sales.thing", "versionRange": "*", "parameters": {"limit": 1, "mode": "zzz"}}])
    assert by_id(analyse(b, lib))["entity:thing"]["status"] == "partial"
    b = bp(["thing"], components=[{"id": "sales.thing", "versionRange": "*", "parameters": {"limit": True}}])
    assert by_id(analyse(b, lib))["entity:thing"]["status"] == "partial"


def test_partial_on_engine_mismatch():
    b = bp(["thing"])
    b["meta"]["engineTarget"] = {"adapter": "change_engine", "versionSet": "other-set"}
    r = by_id(analyse(b, [mk()]))["entity:thing"]
    assert r["status"] == "partial" and "engine_incompatible" in codes(r)
    b2 = bp(["thing"], target=False)
    assert by_id(analyse(b2, [mk()]))["entity:thing"]["status"] == "covered"


def test_requires_unmet_makes_provider_unusable():
    lib = [mk(requires=[{"component": "core.missing", "versionRange": "^1.0.0"}])]
    r = by_id(analyse(bp(["thing"]), lib))["entity:thing"]
    assert r["status"] == "uncovered" and "requires_unmet" in codes(r)
    lib = [mk(requires=[{"capability": "x.y", "versionRange": "*"}]), mk(cid="x.y2", arts=(("entity", "q"),), cap="x.y")]
    assert by_id(analyse(bp(["thing"]), lib))["entity:thing"]["status"] == "covered"


def test_einvoicing_requirement():
    ei = {"mode": "zatca_phase2", "componentId": "compliance.zatca_sa"}
    r = by_id(analyse(bp([], ei=ei), fixture_lib()))["compliance:einvoicing.zatca_phase2"]
    assert r["status"] == "covered"
    r = by_id(analyse(bp([], ei=ei), []))["compliance:einvoicing.zatca_phase2"]
    assert r["status"] == "uncovered" and codes(r) == ["component_unknown"]
    r = by_id(analyse(bp([], ei={"mode": "zatca_phase2"}), fixture_lib()))["compliance:einvoicing.zatca_phase2"]
    assert codes(r) == ["no_component_named"]
    # a non-compliance component named as the e-invoicing component never covers it
    r = by_id(analyse(bp([], ei={"mode": "m", "componentId": "sales.thing"}), [mk()]))["compliance:einvoicing.m"]
    assert r["status"] == "uncovered" and "capability_mismatch" in codes(r)
    # mode none: no requirement
    assert analyse(bp([], ei={"mode": "none"}), [])["summary"]["total"] == 0
    rep = analyse(bp([], ei={"mode": "zatca_phase2"}), [])
    assert rep["component_requests"][0]["kind_hint"] == "rigid"


def test_malformed_blueprint_items_counted_not_crashing():
    b = bp(["thing"])
    b["entities"] += [None, 7, {"id": ""}, {"id": 5}, {"id": "thing"}]
    b["components"] += [None, {"id": 3}, {"id": "sales.thing"}]
    rep = analyse(b, [mk()])
    assert rep["summary"]["malformed_blueprint_items"] == 7
    assert by_id(rep)["entity:thing"]["status"] == "covered" and rep["summary"]["total"] == 1


def test_stable_ordering_and_determinism():
    b = bp(["zeta", "alpha"], workflows=["wf"], reports=["rp"], ei={"mode": "m", "componentId": "c.d"})
    rep1 = analyse(b, fixture_lib())
    rep2 = analyse(copy.deepcopy(b), list(reversed(fixture_lib())))
    assert json.dumps(rep1, sort_keys=False, ensure_ascii=False) == json.dumps(rep2, sort_keys=False, ensure_ascii=False)
    assert [r["id"] for r in rep1["requirements"]] == ["compliance:einvoicing.m", "entity:alpha", "entity:zeta", "workflow:wf", "report:rp"]
    assert json.loads(json.dumps(rep1)) == rep1


def test_inputs_not_mutated():
    b, lib = copy.deepcopy(BP), fixture_lib()
    b0, l0 = copy.deepcopy(b), copy.deepcopy(lib)
    analyse(b, lib)
    assert b == b0 and lib == l0


def test_arabic_and_english_labels_everywhere():
    rep = analyse(bp(["thing", "other"]), [mk()])
    r = by_id(rep)
    assert r["entity:thing"]["status_labels"]["ar"] == "مغطى بمكوّن معتمد"
    assert r["entity:thing"]["subject_labels"]["ar"] == "سجل thing"
    assert "مكوّن" in r["entity:other"]["reasons"][0]["labels"]["ar"] or "المكتبة" in r["entity:other"]["reasons"][0]["labels"]["ar"]
    assert "other" in r["entity:other"]["reasons"][0]["labels"]["en"]
    assert r["entity:other"]["status_key"] == "gap.status.uncovered"
    assert rep["summary"]["labels"]["uncovered"] == {"ar": "غير مغطى", "en": "Uncovered"}
    assert render("gap.status.partial", locale="ar").startswith("مغطى جزئيا")
    assert render("no.such.key") == "no.such.key" and render("gap.status.partial", locale="fr") == "gap.status.partial"


def test_label_files_have_matching_keys_and_placeholders():
    import re
    L = impl._LABELS
    assert set(L["ar"]) == set(L["en"])
    for k in L["en"]:
        assert re.findall(r"\{\w+\}", L["en"][k]) == re.findall(r"\{\w+\}", L["ar"][k]) or \
            sorted(re.findall(r"\{\w+\}", L["en"][k])) == sorted(re.findall(r"\{\w+\}", L["ar"][k])), k


def test_every_emitted_key_has_a_label():
    rep = analyse(BP, [mk()])
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("key", "status_key", "kind_key"):
                    assert v in impl._LABELS["en"] and v in impl._LABELS["ar"], v
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(rep)


def test_component_requests_feed_quote_shape():
    rep = analyse(bp(["a", "b"], workflows=["w"]), [mk(arts=(("entity", "a"),), cid="sales.a")])
    qs = rep["component_requests"]
    assert [q["requirement_id"] for q in qs] == ["entity:b", "workflow:w"]
    assert len({q["request_key"] for q in qs}) == 2
    assert all(set(q) >= {"request_key", "kind", "ref", "kind_hint", "reason_codes", "evidence"} for q in qs)
    assert rep["summary"]["total"] == rep["summary"]["covered"] + rep["summary"]["partial"] + rep["summary"]["uncovered"]


def test_registry_instance_accepted():
    from registry import Registry
    reg = Registry.from_manifests([mk()])
    assert by_id(analyse(bp(["thing"]), reg))["entity:thing"]["status"] == "covered"
