"""OPR-006 slice 2: `metric.query` generated from the metric registry and executed with the caller's own roles."""
import json
import sys
from pathlib import Path

import pytest

OPERATE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(OPERATE))
sys.path.insert(0, str(OPERATE.parent))

from metrics import MetricService, default_registry  # noqa: E402
from metrics.errors import CODES  # noqa: E402
from runtime import ToolRequest  # noqa: E402
from runtime.metric_tool import DOMAIN, MetricToolPort  # noqa: E402
from toolapi.errors import load_catalog  # noqa: E402
from toolapi.generate import generate_tool_api  # noqa: E402

ROOT = OPERATE.parents[1]
T = "t_abc"
EVENTS = [{"event_id": "E1", "type": "document.issued", "tenant_id": T, "sequence": 1,
           "occurred_at": "2026-11-02T10:00:00Z",
           "data": {"document_id": "INV-1", "document_type": "invoice", "total": "115.005", "currency": "SAR"}}]


def req(args, roles=("owner",), tool="metric.query", tenant=T):
    return ToolRequest(tool=tool, arguments=args, idempotency_key="", tenant_id=tenant, user_id="u1",
                       role_ids=tuple(roles), session_id="s", run_id="r")


def port(events=EVENTS):
    return MetricToolPort(MetricService(default_registry(), lambda t: list(events)))


def test_every_met_code_has_a_catalog_entry_and_ar_text():
    cat = {e["id"]: e for e in load_catalog()["entries"]}
    assert set(DOMAIN) == set(CODES)
    for eid in DOMAIN.values():
        assert cat[eid]["messages"]["ar"] and cat[eid]["params"] == {}


def test_generator_uses_registry_with_role_filtering():
    bp = json.loads((ROOT / "contracts/examples/blueprint-trading-minimal.json").read_text(encoding="utf-8"))
    res = generate_tool_api(bp, metrics=default_registry())
    t = next(x for x in res.tools if x["name"] == "metric.query")
    assert t["kind"] == "read" and t["risk_class"] == "R0"
    assert t["input_schema"]["properties"]["metric"]["enum"] == sorted(default_registry())
    assert t["requires"]["roles"] == ["owner"]  # registry roles intersected with this Blueprint's chat roles
    rbv = t["requires_by_value"]
    assert rbv["argument"] == "metric" and all(v == ["owner"] for v in rbv["roles"].values())
    assert "roles" not in t["input_schema"]["properties"] and "tenant_id" not in t["input_schema"]["properties"]
    plain = generate_tool_api(bp)  # default behaviour unchanged
    assert next(x for x in plain.tools if x["name"] == "metric.query")["input_schema"] != t["input_schema"]


def test_value_is_code_computed_and_result_has_no_events():
    r = port().call(req({"metric": "sales.revenue", "period": "2026-11", "currency": "SAR"}))
    assert r.status == "ok"
    assert r.result["value"] == "115.01" and r.result["metric"] == "sales.revenue"
    assert set(r.result) == {"metric", "label_key", "unit", "value", "currency", "params"}
    assert "E1" not in json.dumps(r.result) and "INV-1" not in json.dumps(r.result)


@pytest.mark.parametrize("args,roles,domain", [
    ({"metric": "nope.x"}, ("owner",), "metric_unknown"),
    ({"metric": "sales.revenue", "period": "2026-11", "currency": "SAR"}, ("warehouse_keeper",), "metric_permission_denied"),
    ({"metric": "sales.revenue", "period": "2026-11", "currency": "SAR", "roles": ["owner"]}, ("owner",),
     "metric_invalid_params"),
    ({"metric": "sales.revenue", "period": "2026-11"}, ("owner",), "metric_invalid_params"),
])
def test_refusals_use_catalog_codes_and_caller_roles_only(args, roles, domain):
    r = port().call(req(args, roles))
    assert r.status == "error" and r.error["domain"]["code"] == domain


def test_tenant_mismatch_refused():
    bad = [dict(EVENTS[0], tenant_id="t_other")]
    r = port(bad).call(req({"metric": "sales.order_count", "period": "2026-11"}))
    assert r.status == "error" and r.error["domain"]["code"] == "metric_tenant_mismatch"
    assert r.result is None


def test_missing_identity_and_other_tools_fail_closed():
    r = port().call(req({"metric": "sales.order_count", "period": "2026-11"}, tenant=""))
    assert r.error["domain"]["code"] == "metric_no_principal"
    assert port().call(req({}, tool="sales_order.get")).error["code"] == "unknown_tool"
