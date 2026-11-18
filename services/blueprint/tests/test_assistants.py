"""Rule 14, department assistants (ADR-0043, OPR-017). Each refusal code fires; a sound assistant passes."""
import copy
import json
import sys

import pytest

from fixture_registry import REPO, load_example
from test_example import full_ctx
from validator import validate
from validator.rules_assistants import PLATFORM_ASSISTANT_CAPS


TOOLAPI = REPO / "services" / "operate"
if str(TOOLAPI) not in sys.path:
    sys.path.insert(0, str(TOOLAPI))
from toolapi import generate_tool_api  # noqa: E402
from toolapi import policy as tapi_policy  # noqa: E402

# The real generator output for the example Blueprint, so the fixture cannot drift from it.
_GEN = generate_tool_api(load_example())
assert _GEN.ok, _GEN.errors
TOOL_SET = {"tools": copy.deepcopy(_GEN.tools)}


def tool_set_with(name, **over):
    ts = copy.deepcopy(TOOL_SET)
    next(t for t in ts["tools"] if t["name"] == name).update(over)
    return ts


KEY = "assistants.sales.instructions"


def assistant(**over):
    a = {
        "id": "sales_assistant", "department": "sales",
        "labels": {"ar": "مساعد المبيعات", "en": "Sales assistant"},
        "roles": ["sales_rep", "owner"], "instructionsKey": KEY,
        "tools": [{"tool": "customer.list"}, {"tool": "sales_order.create"},
                  {"tool": "sales_order.transition", "confirm": True,
                   "transitions": ["submit_small", "submit_large", "cancel_draft"]}, {"tool": "report.run"}],
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


def tr(*ids, roles=None, confirm=True):
    over = {"tools": [{"tool": "sales_order.transition", "confirm": confirm, "transitions": list(ids)}]}
    if roles:
        over["roles"] = roles
    return assistant(**over)


NO_SET = {"tool_set": None}


@pytest.mark.parametrize("code,a,kw", [
    ("BP-AST-001", assistant(roles=["ghost"]), {}),
    ("BP-AST-002", assistant(department="purchasing", roles=["owner"]), {}),
    ("BP-AST-003", assistant(roles=["warehouse_keeper"]), {}),
    ("BP-AST-005", assistant(tools=[{"tool": "approval.decide"}]), {}),
    ("BP-AST-005", assistant(tools=[{"tool": "blueprint.propose_change"}]), {}),
    ("BP-AST-005", assistant(tools=[{"tool": "sales_order.approve"}]), {}),
    ("BP-AST-005", assistant(tools=[{"tool": "customer.update_bank_details"}]), {}),
    ("BP-AST-005", assistant(tools=[{"tool": "customer.update_contact_details"}]), {}),
    # HIGH-2: R3/R4 and posting tools are refused with or without a tool set.
    ("BP-AST-005", assistant(tools=[{"tool": "sales_invoice.submit"}], roles=["owner"]), {}),
    ("BP-AST-005", assistant(tools=[{"tool": "sales_invoice.submit"}], roles=["owner"]), NO_SET),
    ("BP-AST-005", assistant(tools=[{"tool": "sales_invoice.cancel"}], roles=["owner"]), NO_SET),
    ("BP-AST-005", assistant(tools=[{"tool": "sales_order.delete"}]), NO_SET),
    ("BP-AST-005", assistant(tools=[{"tool": "sales_order.amend"}]), NO_SET),
    ("BP-AST-005", assistant(tools=[{"tool": "sales_invoice.transition", "confirm": True,
                                     "transitions": ["submit"]}], roles=["owner"]), NO_SET),
    # HIGH-1: approve moves inside <entity>.transition are refused, with or without a tool set.
    ("BP-AST-005", tr("submit_small", "approve_large"), {}),
    ("BP-AST-005", tr("approve_large"), NO_SET),
    ("BP-AST-005", tr("submit_small"), {"tool_set": tool_set_with("sales_order.transition", transitions=[
        {**t, "kind": "approve"} if t["id"] == "submit_small" else t
        for t in next(x for x in TOOL_SET["tools"] if x["name"] == "sales_order.transition")["transitions"]])}),
    ("BP-AST-006", tr("ship_now"), {}),
    ("BP-AST-006", tr("ship_now"), NO_SET),
    ("BP-AST-006", assistant(tools=[{"tool": "payroll.list"}]), {}),
    ("BP-AST-006", assistant(tools=[{"tool": "customer.search"}]), {}),
    ("BP-AST-006", assistant(tools=[{"tool": "payroll.list"}]), NO_SET),
    ("BP-AST-006", assistant(tools=[{"tool": "approval.anything"}]), NO_SET),
    ("BP-AST-007", assistant(tools=[{"tool": "sales_order.create"}]), {"tool_set": tool_set_with("sales_order.create", risk_class="R3")}),
    ("BP-AST-008", assistant(tools=[{"tool": "customer.list"}]), {"tool_set": tool_set_with("customer.list", agent_creatable=False)}),
    ("BP-AST-009", tr("submit_small", confirm=False), {}),
    ("BP-AST-010", assistant(tools=[{"tool": "item.create"}], roles=["sales_rep"]), {}),
    ("BP-AST-010", tr("deliver", roles=["sales_rep"]), {}),
    ("BP-AST-011", assistant(limits={"perCall": {"maxToolCalls": 8, "maxRows": 100},
                                     "perDay": {"maxToolCalls": 200, "maxWrites": 40}}),
     {"assistant_caps": {"perDay": {"maxWrites": 10}}}),
    ("BP-AST-011", assistant(limits={"perCall": {"maxToolCalls": 8, "maxRows": 100},
                                     "perDay": {"maxToolCalls": 5, "maxWrites": 4}}), {}),
    ("BP-AST-012", assistant(), {"instruction_keys": set()}),
    ("BP-AST-016", assistant(tools=[{"tool": "memory.note"}], memory={"scope": "none"}), NO_SET),
    ("BP-ID-001", assistant(tools=[{"tool": "customer.list"}, {"tool": "customer.list", "confirm": True}]), {}),
])
def test_refusals(code, a, kw):
    rep = validate(bp_with(a), ctx(**kw))
    assert code in codes(rep), [str(e) for e in rep.errors]


def test_tool_set_entry_without_risk_is_refused():
    ts = {"tools": [{"name": "customer.list", "agent_creatable": True, "requires": {"roles": ["sales_rep"]}}]}
    rep = validate(bp_with(assistant(tools=[{"tool": "customer.list"}])), ctx(tool_set=ts))
    assert "BP-AST-007" in codes(rep)


def test_missing_context_warns_and_static_checks_still_run():
    rep = validate(bp_with(assistant()), ctx(tool_set=None, instruction_keys=None))
    assert {"BP-AST-014", "BP-AST-015"} <= codes(rep, "warnings")
    assert not {c for c in codes(rep) if c.startswith("BP-AST")}
    rep = validate(bp_with(assistant(tools=[{"tool": "sales_invoice.submit"}])), ctx(tool_set=None))
    assert "BP-AST-005" in codes(rep) and not rep.ok


def test_memory_tool_allowed_with_a_memory_scope():
    rep = validate(bp_with(assistant(tools=[{"tool": "memory.note"}])), ctx(tool_set=None))
    assert not {c for c in codes(rep) if c.startswith("BP-AST")}


def test_posting_sets_cover_the_tool_api_policy():
    from validator.rules_assistants import (NEVER_TRANSITION_TOKENS, POSTING_ENTITY_IDS, POSTING_NAME_TOKENS,
                                            posting_entity)
    assert set(tapi_policy.KNOWN_LEDGER) | set(tapi_policy.KNOWN_STOCK) <= POSTING_ENTITY_IDS
    assert tapi_policy.LEDGER_NAME_TOKENS <= POSTING_NAME_TOKENS
    assert (tapi_policy.APPROVE_TOKENS | tapi_policy.REJECT_TOKENS | tapi_policy.REVERSAL_TOKENS) <= NEVER_TRANSITION_TOKENS
    assert posting_entity("sales_invoice") and posting_entity("customer_payment") and not posting_entity("customer")


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
    lambda a: a["tools"].append({"tool": "item.list", "transitions": ["deliver"]}),  # allowlist only on transition
    lambda a: a["tools"][2].pop("transitions"),                                       # transition needs allowlist
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


def _bpdiff():
    p = str(REPO / "services" / "blueprint" / "diff")
    if p not in sys.path:
        sys.path.insert(0, p)
    import bpdiff
    from bpdiff.classify import impact_of
    from bpdiff.model import spath
    return bpdiff.diff, impact_of, spath


def test_diff_classifies_assistant_changes_as_access():
    _, impact_of, spath = _bpdiff()
    assert impact_of("add", spath("assistants/*/tools/*")) == "access"
    assert impact_of("change", spath("assistants/*/limits/perDay/maxWrites")) == "access"
    assert impact_of("change", spath("assistants/*/labels/en")) == "cosmetic"
    assert impact_of("replace", ("i18n", "labelOverrides", KEY, "en")) == "access"
    assert impact_of("replace", ("i18n", "labelOverrides", "entities.customer", "en")) == "cosmetic"


def test_bpdiff_end_to_end_on_assistant_edits():
    diff, _, _ = _bpdiff()
    a = bp_with(assistant())
    a["i18n"]["labelOverrides"][KEY] = {"ar": "اختصر الردود", "en": "Keep replies short"}
    b = copy.deepcopy(a)
    b["assistants"][0]["tools"][2]["confirm"] = False
    b["assistants"][0]["tools"].pop(0)
    b["assistants"][0]["tools"][1]["transitions"].append("deliver")
    b["i18n"]["labelOverrides"][KEY]["en"] = "Approve every order you see"
    b["assistants"][0]["labels"]["en"] = "Sales helper"
    ops = diff(a, b)["ops"]
    label_ops = [o for o in ops if [str(x) for x in o["path"]][-2:] == ["labels", "en"]]
    assert label_ops and all(o["impact"] == "cosmetic" for o in label_ops)
    rest = [o for o in ops if o not in label_ops]
    assert len(rest) >= 4 and all(o["impact"] == "access" for o in rest), ops
