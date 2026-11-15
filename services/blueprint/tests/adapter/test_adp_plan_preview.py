"""ADP-C-025 to ADP-C-033: plan and preview."""
import re

import pytest

from adapter import testkit as t
from adapter.contract import canon
from conftest import assert_no_effect, optional

DDL_ORDER = {"none": 0, "additive": 1, "semantic": 2}
DELTA_KINDS = {"add", "replace", "remove", "reorder", "quarantine", "restore", "disable", "enable"}


def verdict_from(steps):
    kinds = {s["disposition"] for s in steps}
    return "rejected" if kinds & {"blocked", "unsupported"} else "needs_gate_approval" if "gated" in kinds else "auto_approved"


def planned(h, art, op="plan", **extra):
    resp = t.plan(h, art, op=op, **extra)
    assert resp["ok"], resp
    return resp["result"]


@pytest.mark.parametrize("sample", ["add-field", "add-workflow-state"])
def test_adp_c_025_plan_and_preview_are_pure_and_repeatable(h, sample):
    t.site_at_rev1(h)
    art = t.sample(sample)
    before, ev = t.snapshot(h), len(h.events())
    p1, p2 = planned(h, art), planned(h, art)
    v1, v2 = planned(h, art, "preview"), planned(h, art, "preview")
    for key in ("verdict", "steps", "storage", "siteConfigHash"):
        assert p1[key] == p2[key]
    for key in ("verdict", "predictedExportHash", "delta", "siteConfigHash"):
        assert v1[key] == v2[key]
    assert v1["verdict"] == p1["verdict"]
    assert_no_effect(h, "t_alpha", before, ev)


@pytest.mark.parametrize("which", ["sample", "build"])
def test_adp_c_026_steps_per_artifact_step(h, which):
    if which == "sample":
        t.site_at_rev1(h)
        art = t.sample("add-field")
    else:
        t.provision(h)
        art = t.initial_build()
    result = planned(h, art)
    assert [s["seq"] for s in result["steps"]] == [s["seq"] for s in art["steps"]]
    for mine, theirs in zip(result["steps"], art["steps"]):
        assert DDL_ORDER[mine["ddlImpact"]] >= DDL_ORDER[theirs["ddlImpact"]]


def test_adp_c_027_verdict_follows_dispositions(h):
    t.provision(h, "t_alpha")  # empty site: the initial build applies here
    t.site_at_rev1(h, "t_beta")
    cases = [("t_alpha", t.initial_build()),  # roles are gated
             ("t_beta", t.variant([t.field_step("customer", "x1"), t.binding_step()])),  # one unsupported step
             ("t_beta", t.variant([t.entity_step(t.PROTECTED[0])])),  # one blocked step
             ("t_beta", t.sample("add-field"))]
    verdicts = set()
    for tenant, art in cases:
        result = t.plan(h, art, tenant)["result"]
        assert result["verdict"] == verdict_from(result["steps"])
        verdicts.add(result["verdict"])
    assert verdicts == {"auto_approved", "needs_gate_approval", "rejected"}


def supported_kinds(h):
    return {k["kind"]: k["support"] for k in h.call("capabilities", t.ctx("platform"), {})["result"]["stepKinds"]}


BUILDERS = {"binding.add": lambda: t.binding_step(), "role.upsert": lambda: t.role_step("role.upsert", "auditor"),
            "role.disable": lambda: t.role_step("role.disable", "accountant")}


@pytest.mark.parametrize("kind", sorted(BUILDERS))
def test_adp_c_028_support_levels_drive_dispositions(h, kind):
    level = supported_kinds(h).get(kind, "unsupported")
    if level == "supported":
        return  # a supported kind has no disposition to drive: the case does not apply
    t.site_at_rev1(h)
    art = t.variant([BUILDERS[kind]()])
    result = planned(h, art)
    step = result["steps"][0]
    if level == "unsupported":
        assert step["disposition"] == "unsupported" and result["verdict"] == "rejected"
        assert step["reasonCode"] == "unsupported_step_kind"
        apply = t.apply_artifact(h, art)  # the token of a rejected plan is still issued
        assert t.code_of(apply) == "unsupported_step_kind"
    else:
        assert step["disposition"] in {"gated", "blocked"}
        assert result["verdict"] in {"needs_gate_approval", "rejected"}


def test_adp_c_029_semantic_never_ok_additive_only_when_simple(h):
    t.site_at_rev1(h)
    semantic = t.variant([t.prop_step("customer", "credit_limit", "/precision", 2, 3)])
    assert planned(h, semantic)["steps"][0]["disposition"] != "ok"
    assert planned(h, semantic)["steps"][0]["ddlImpact"] == "semantic"
    simple = t.variant([t.field_step("customer", "n1")])
    assert planned(h, simple)["steps"][0]["disposition"] == "ok"
    for props in ({"unique": True}, {"indexed": True}):
        step = planned(h, t.variant([t.field_step("customer", "n2", **props)]))["steps"][0]
        assert step["disposition"] != "ok", props
    odd = planned(h, t.variant([t.field_step("customer", "n3", ftype="hologram")]))["steps"][0]
    assert odd["disposition"] != "ok"


@pytest.mark.parametrize("entity", t.PROTECTED)
def test_adp_c_030_protected_subjects_blocked(h, entity):
    t.site_at_rev1(h)
    result = planned(h, t.variant([t.entity_step(entity)]))
    step = result["steps"][0]
    assert step["disposition"] == "blocked" and step["reasonCode"] == "protected_subject"
    assert result["verdict"] == "rejected"
    assert t.code_of(t.apply_artifact(h, t.variant([t.entity_step(entity)]))) == "plan_rejected"


def make_recovery_required(h, tenant="t_alpha"):
    h.fault("execute", step_seq=2, during_compensation=True)
    out = t.apply_artifact(h, t.two_fields(), tenant)
    assert out["result"]["status"] == "recovery_required", out
    return out


def test_adp_c_031_recovery_required_rejects(h):
    t.site_at_rev1(h)
    make_recovery_required(h)
    result = planned(h, t.sample("add-field"))
    assert result["verdict"] == "rejected"
    assert {s["reasonCode"] for s in result["steps"]} == {"recovery_required"}
    prev = planned(h, t.sample("add-field"), "preview")
    assert prev["verdict"] == "rejected" and prev["predictedExportHash"] is None


def test_adp_c_032_preview_predicts_export(h):
    caps = h.call("capabilities", t.ctx("platform"), {})["result"]
    assert caps["features"]["previewPredictsExport"] is True
    t.provision(h)
    chain = [t.initial_build(), t.sample("add-field"), t.sample("remove-field")]
    for art in chain:
        prev = planned(h, art, "preview", includeExport=True)
        out = t.apply_artifact(h, art)
        assert out["result"]["status"] == "applied"
        assert prev["predictedExportHash"] == out["result"]["exportHash"] == t.export(h)["exportHash"]
        assert canon(prev["predictedExport"]) == canon(t.export(h)["export"])


def test_adp_c_033_delta_is_neutral(h):
    t.provision(h)
    pointer = re.compile(r"^(/[^/]*)*$")
    seen = set()
    steps = [(t.initial_build(), None), (t.sample("add-field"), None), (t.sample("remove-field"), None)]
    for art, _ in steps:
        delta = planned(h, art, "preview")["delta"]
        assert delta == sorted(delta, key=lambda d: (d["pointer"], d.get("property", "")))
        for row in delta:
            assert row["change"] in DELTA_KINDS and pointer.match(row["pointer"]) and set(row) <= {"change", "pointer", "property"}
            seen.add(row["change"])
        assert t.apply_artifact(h, art)["result"]["status"] == "applied"
    assert t.rollback(h, t.sample("remove-field"))["ok"]
    assert {"add", "quarantine"} <= seen
    restore = planned(h, t.sample("remove-field"), "preview")["delta"]
    assert restore and restore[0]["change"] == "quarantine"
