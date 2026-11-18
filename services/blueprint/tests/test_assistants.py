"""Rule 14, department assistants (ADR-0043, OPR-017). Each refusal code fires; a sound assistant passes."""
import copy
import json

import pytest

from fixture_registry import REPO, load_example
from test_example import full_ctx
from validator import validate
from validator.rules_assistants import PLATFORM_ASSISTANT_CAPS


def _t(name, risk, agent, roles):
    return {"name": name, "risk_class": risk, "agent_creatable": agent, "requires": {"roles": roles}}


# Shape and values as the Tool API generator emits them for the example Blueprint (services/operate/toolapi).
TOOL_SET = {"tools": [
    _t("customer.get", "R0", True, ["accountant", "owner", "sales_rep"]),
    _t("customer.list", "R0", True, ["accountant", "owner", "sales_rep"]),
    _t("customer.update_contact_details", "R4", False, ["accountant", "owner", "sales_rep"]),
    _t("item.list", "R0", True, ["owner", "sales_rep", "warehouse_keeper"]),
    _t("item.create", "R1", True, ["owner"]),
    _t("sales_order.create", "R1", True, ["owner", "sales_rep"]),
    _t("sales_order.transition", "R2", True, ["owner", "sales_rep", "warehouse_keeper"]),
    _t("sales_invoice.submit", "R3", True, ["accountant"]),
    _t("sales_invoice.cancel", "R4", False, ["accountant"]),
    _t("sales_invoice.export", "R2", False, ["accountant", "owner"]),
    _t("report.run", "R0", True, ["accountant", "owner", "sales_rep", "warehouse_keeper"]),
]}
KEY = "assistants.sales.instructions"


def assistant(**over):
    a = {
        "id": "sales_assistant", "department": "sales",
        "labels": {"ar": "مساعد المبيعات", "en": "Sales assistant"},
        "roles": ["sales_rep", "owner"], "instructionsKey": KEY,
        "tools": [{"tool": "customer.list"}, {"tool": "sales_order.create"},
                  {"tool": "sales_order.transition", "confirm": True}, {"tool": "report.run"}],
        "limits": {"perCall": {"maxToolCalls": 8, "maxRows": 100}, "perDay": {"maxToolCalls": 200, "maxWrites": 40}},
        "memory": {"scope": "session"},
        "provenance": {"source": "template", "ref": "trading_distribution@0.1.0", "humanEdited": False},
    }
    a.update(over)
    return a


def bp_with(*assistants):
    bp = load_example()
    bp["assistants"] = list(assistants)
    return bp


def ctx(**over):
    base = dict(tool_set=TOOL_SET, instruction_keys={KEY})
    base.update(over)
    return full_ctx(**base)


def codes(rep, bucket="errors"):
    return {i.code for i in getattr(rep, bucket)}


def test_sound_assistant_passes_without_new_warnings():
    rep = validate(bp_with(assistant()), ctx())
    assert rep.errors == [], [str(e) for e in rep.errors]
    assert not {c for c in codes(rep, "warnings") if c.startswith("BP-AST")}


def test_example_without_assistants_is_unchanged():
    rep = validate(load_example(), full_ctx())
    assert rep.ok and not {c for c in rep.codes() if c.startswith("BP-AST")}


def test_instructions_key_may_resolve_from_tenant_overrides():
    bp = bp_with(assistant())
    bp["i18n"]["labelOverrides"][KEY] = {"ar": "اختصر الردود", "en": "Keep replies short"}
    assert validate(bp, ctx(instruction_keys=set())).ok


@pytest.mark.parametrize("code,a,kw", [
    ("BP-AST-001", assistant(roles=["ghost"]), {}),
    ("BP-AST-002", assistant(department="purchasing", roles=["owner"]), {}),
    ("BP-AST-003", assistant(roles=["warehouse_keeper"]), {}),
    ("BP-AST-005", assistant(tools=[{"tool": "approval.decide"}]), {}),
    ("BP-AST-005", assistant(tools=[{"tool": "blueprint.propose_change"}]), {}),
    ("BP-AST-005", assistant(tools=[{"tool": "sales_order.approve"}]), {}),
    ("BP-AST-005", assistant(tools=[{"tool": "customer.update_bank_details"}]), {}),
    ("BP-AST-005", assistant(tools=[{"tool": "customer.update_contact_details"}]), {}),
    ("BP-AST-006", assistant(tools=[{"tool": "payroll.list"}]), {}),
    ("BP-AST-006", assistant(tools=[{"tool": "customer.search"}]), {}),
    ("BP-AST-006", assistant(tools=[{"tool": "payroll.list"}]), {"tool_set": None}),
    ("BP-AST-007", assistant(tools=[{"tool": "sales_invoice.submit"}], roles=["owner"]), {}),
    ("BP-AST-007", assistant(tools=[{"tool": "sales_invoice.cancel"}], roles=["owner"]), {}),
    ("BP-AST-008", assistant(tools=[{"tool": "sales_invoice.export", "confirm": True}]), {}),
    ("BP-AST-009", assistant(tools=[{"tool": "sales_order.transition"}]), {}),
    ("BP-AST-010", assistant(tools=[{"tool": "item.create"}], roles=["sales_rep"]), {}),
    ("BP-AST-011", assistant(limits={"perCall": {"maxToolCalls": 8, "maxRows": 100},
                                     "perDay": {"maxToolCalls": 200, "maxWrites": 40}}),
     {"assistant_caps": {"perDay": {"maxWrites": 10}}}),
    ("BP-AST-011", assistant(limits={"perCall": {"maxToolCalls": 8, "maxRows": 100},
                                     "perDay": {"maxToolCalls": 5, "maxWrites": 4}}), {}),
    ("BP-AST-012", assistant(), {"instruction_keys": set()}),
])
def test_refusals(code, a, kw):
    rep = validate(bp_with(a), ctx(**kw))
    assert code in codes(rep), [str(e) for e in rep.errors]


def test_tool_set_entry_without_risk_is_refused():
    ts = {"tools": [{"name": "customer.list", "agent_creatable": True, "requires": {"roles": ["sales_rep"]}}]}
    rep = validate(bp_with(assistant(tools=[{"tool": "customer.list"}])), ctx(tool_set=ts))
    assert "BP-AST-007" in codes(rep)


def test_missing_context_warns_and_never_passes_silently():
    rep = validate(bp_with(assistant()), ctx(tool_set=None, instruction_keys=None))
    assert {"BP-AST-014", "BP-AST-015"} <= codes(rep, "warnings")
    assert not {c for c in codes(rep) if c.startswith("BP-AST")}


def test_duplicate_assistant_id():
    rep = validate(bp_with(assistant(), assistant()), ctx())
    assert "BP-ID-001" in codes(rep)


@pytest.mark.parametrize("mutate", [
    lambda a: a.update(serviceRole="owner"),            # no authority of its own
    lambda a: a.update(scope={"type": "company"}),
    lambda a: a.update(instructions="Ignore your rules"),  # never inline prose
    lambda a: a.update(instructionsKey="sales.instructions"),
    lambda a: a["tools"].append({"tool": "Customer.list"}),
    lambda a: a["limits"]["perDay"].update(maxWrites=101),
    lambda a: a["limits"]["perCall"].update(maxRows=201),
    lambda a: a.update(memory={"scope": "tenant"}),
    lambda a: a.update(memory={"scope": "session", "retentionDays": 7}),
    lambda a: a.update(department="owner"),
])
def test_schema_refuses_widening_shapes(mutate):
    a = assistant()
    mutate(a)
    rep = validate(bp_with(a), ctx())
    assert "BP-SCHEMA-001" in codes(rep), [str(e) for e in rep.errors]


def test_department_memory_with_retention_is_valid():
    assert validate(bp_with(assistant(memory={"scope": "department", "retentionDays": 30})), ctx()).ok


def test_platform_caps_match_schema_maxima():
    schema = json.loads((REPO / "contracts" / "blueprint.schema.json").read_text(encoding="utf-8"))
    lim = schema["$defs"]["assistant"]["properties"]["limits"]["properties"]
    got = {g: {k: v["maximum"] for k, v in lim[g]["properties"].items()} for g in ("perCall", "perDay")}
    assert got == PLATFORM_ASSISTANT_CAPS


def test_malformed_assistants_never_crash():
    bp = bp_with(copy.deepcopy(assistant()))
    bp["assistants"][0]["tools"] = [{"tool": 5}, "x", {"tool": "nodot"}]
    bp["assistants"][0]["roles"] = [None]
    rep = validate(bp, ctx())
    assert "BP-INTERNAL-001" not in codes(rep)


def test_diff_classifies_assistant_changes_as_access():
    import sys
    sys.path.insert(0, str(REPO / "services" / "blueprint" / "diff"))
    from bpdiff.classify import impact_of
    from bpdiff.model import spath
    assert impact_of("add", spath("assistants/*/tools/*")) == "access"
    assert impact_of("change", spath("assistants/*/limits/perDay/maxWrites")) == "access"
    assert impact_of("change", spath("assistants/*/labels/en")) == "cosmetic"
