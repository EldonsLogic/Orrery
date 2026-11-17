import copy
import json
import subprocess
import sys

from conftest import FIXTURE, OPERATE
from toolapi import check_tool_api, generate_tool_api, to_bytes


def codes(res):
    return {e.code for e in res.errors}


def tool(res, name):
    return next(t for t in res.tools if t["name"] == name)


def test_fixture_generates_stable_set(bp):
    res = generate_tool_api(bp)
    assert res.ok, [str(e) for e in res.errors]
    names = [t["name"] for t in res.tools]
    assert names == sorted(names) and len(names) == len(set(names))
    assert len(names) == 85
    for n in ("customer.get", "customer.list", "sales_order.create", "sales_order.transition", "sales_invoice.transition",
              "report.run", "metric.query", "approval.decide", "approval.list_mine", "blueprint.propose_change"):
        assert n in names
    assert "sales_order_line.create" not in names  # child entities are embedded, not tools
    assert "sales_order.submit" not in names  # workflow entity: transitions replace submit
    assert res.content_hash.startswith("sha256:")
    assert check_tool_api(res.definition_set()) == []


def test_determinism_and_input_not_mutated(bp):
    before = copy.deepcopy(bp)
    a, b = generate_tool_api(bp), generate_tool_api(copy.deepcopy(bp))
    assert bp == before
    assert to_bytes(a.definition_set()) == to_bytes(b.definition_set())
    assert a.content_hash == b.content_hash
    bp["entities"].reverse()
    assert [t["name"] for t in generate_tool_api(bp).tools] == [t["name"] for t in a.tools]


def test_schemas_from_field_types(bp):
    res = generate_tool_api(bp)
    so = tool(res, "sales_order.create")["input_schema"]
    assert so["additionalProperties"] is False
    assert "total_amount" not in so["properties"]  # computed
    assert so["properties"]["lines"]["type"] == "array"
    assert so["properties"]["order_date"]["format"] == "date"
    assert so["properties"]["branch"]["enum"]
    assert so["properties"]["customer"]["x-entity-ref"] == "customer"
    assert "total_amount" in tool(res, "sales_order.get")["output_schema"]["properties"]
    assert tool(res, "sales_order.get")["output_schema"]["properties"]["total_amount"]["properties"]["currency"]
    assert tool(res, "sales_order.update")["input_schema"]["required"] == ["expected_version", "id"]


def test_risk_mapping_and_agent_flags(bp):
    res = generate_tool_api(bp)
    inv = tool(res, "sales_invoice.transition")
    by = {t["id"]: t for t in inv["transitions"]}
    assert by["submit_invoice"]["risk_class"] == "R3" and by["cancel_invoice"]["risk_class"] == "R4"
    assert by["cancel_invoice_draft"]["risk_class"] == "R1"
    assert by["cancel_invoice"]["agent_creatable"] is False and inv["risk_class"] == "R4" and inv["agent_creatable"] is False
    assert inv["effects"]["ledger"] and inv["effects"]["tax"] and inv["approval"]["agent_required"]
    so = {t["id"]: t for t in tool(res, "sales_order.transition")["transitions"]}
    assert so["approve_large"]["agent_creatable"] is False and so["reject_order"]["agent_creatable"] is False
    assert so["approve_large"]["approval"]["rule"] == "large_sales_order_approval"
    assert so["submit_large"]["approval"]["required"] and so["submit_large"]["approval"]["conditional"]
    assert not so["deliver"]["approval"]["required"]
    assert tool(res, "approval.decide")["agent_creatable"] is False
    assert tool(res, "blueprint.propose_change")["risk_class"] == "R4"
    assert tool(res, "blueprint.propose_change")["agent_creatable"] is False
    assert all(t["agent_creatable"] is False for t in res.tools if t["risk_class"] == "R4")
    assert tool(res, "customer.get")["risk_class"] == "R0" and tool(res, "customer.get")["idempotency"] == "none"
    assert tool(res, "customer.update")["idempotency"] == "required"


def test_roles_map(bp):
    res = generate_tool_api(bp)
    perms = {r["id"]: {p["entity"]: set(p["actions"]) for p in r["permissions"]} for r in bp["roles"]}
    chat = {r["id"] for r in bp["roles"] if r.get("canUseChatActions", True)}
    want = sorted(r for r in chat if "create" in perms[r].get("sales_order", ()))
    assert tool(res, "sales_order.create")["requires"]["roles"] == want
    assert "auditor" not in {x for t in res.tools for x in t["requires"]["roles"]}  # chat disabled for that role
    assert set(tool(res, "report.run")["requires_by_value"]["roles"]) <= {r["id"] for r in bp["reports"]}
    assert tool(res, "report.run")["requires_by_value"]["roles"]["vat_summary"] == ["accountant"]
    assert tool(res, "blueprint.propose_change")["requires"]["roles"] == ["owner"]
    assert tool(res, "customer.get")["field_access"]["hidden_by_role"]["sales_rep"] == ["credit_limit"]
    assert tool(res, "sales_order.transition")["requires"]["scope"] == "from_caller"


def test_ids_stable_and_labels_are_display_only(bp):
    base = generate_tool_api(bp)
    bp["entities"][0]["labels"] = {"ar": "عميل جديد", "en": "Renamed"}
    again = generate_tool_api(bp)
    assert [t["name"] for t in again.tools] == [t["name"] for t in base.tools]
    assert all(t["name"].isascii() for t in again.tools)
    assert tool(again, "customer.get")["labels"]["ar"].endswith("عميل جديد")


def test_arabic_id_refused(bp):
    bp["entities"][0]["id"] = "عميل"
    assert "TAPI-NAME-004" in codes(generate_tool_api(bp))


def test_duplicate_entity_and_platform_collision(bp):
    dup = copy.deepcopy(bp)
    dup["entities"].append(copy.deepcopy(dup["entities"][0]))
    assert "TAPI-NAME-001" in codes(generate_tool_api(dup))
    bp["entities"][0]["id"] = "report"
    assert "TAPI-NAME-002" in codes(generate_tool_api(bp))


def test_reserved_field_name_refused(bp):
    bp["entities"][0]["fields"][0]["id"] = "id"
    assert "TAPI-NAME-003" in codes(generate_tool_api(bp))


def test_forbidden_argument_names_refused(bp):
    for name in ("caller", "role", "roles", "tenant", "tenant_id", "user_id", "role_ids", "scope"):
        b = copy.deepcopy(bp)
        b["entities"][0]["fields"][0]["id"] = name
        res = generate_tool_api(b)
        assert "TAPI-ARG-001" in codes(res), name
        assert res.tools == [] and res.content_hash is None


def test_forbidden_argument_in_child_and_relation(bp):
    b = copy.deepcopy(bp)
    child = next(e for e in b["entities"] if e["id"] == "sales_order_line")
    child["fields"][0]["id"] = "role"
    assert "TAPI-ARG-001" in codes(generate_tool_api(b))
    b = copy.deepcopy(bp)
    next(e for e in b["entities"] if e["id"] == "sales_order")["relations"][0]["id"] = "tenant"
    assert "TAPI-ARG-001" in codes(generate_tool_api(b))


def test_unknown_field_type_refused_not_guessed(bp):
    bp["entities"][0]["fields"][0]["type"] = "geo_point"
    res = generate_tool_api(bp)
    assert "TAPI-FIELD-001" in codes(res) and res.tools == []
    b = copy.deepcopy(bp)
    next(e for e in b["entities"] if e["id"] == "sales_order_line")["fields"][0]["type"] = "weird"  # child too
    assert "TAPI-FIELD-001" in codes(generate_tool_api(b))


def test_select_without_options_and_bad_link_refused(bp):
    f = next(f for f in bp["entities"][0]["fields"] if f["type"] == "select")
    f["options"] = []
    assert "TAPI-FIELD-002" in codes(generate_tool_api(bp))
    b = copy.deepcopy(bp)
    next(f for e in b["entities"] for f in e["fields"] if f["type"] == "link")["target"] = "nope"
    assert "TAPI-REF-001" in codes(generate_tool_api(b))


def test_unknown_role_refused(bp):
    bp["workflows"][0]["transitions"][0]["allowedRoles"] = ["ghost"]
    assert "TAPI-REF-001" in codes(generate_tool_api(bp))


def test_bad_input_and_registry_refused(bp):
    assert "TAPI-INPUT-001" in codes(generate_tool_api({}))
    assert "TAPI-INPUT-001" in codes(generate_tool_api([]))
    assert "TAPI-REGISTRY-001" in codes(generate_tool_api(bp, {"entity_classes": {"customer": "bogus"}}))
    assert "TAPI-REGISTRY-001" in codes(generate_tool_api(bp, {"extra": 1}))


def test_registry_overrides_class(bp):
    res = generate_tool_api(bp, {"entity_classes": {"customer": "ledger"}})
    assert tool(res, "customer.export")["risk_class"] == "R2"


def test_checker_catches_each_hard_rule(bp):
    good = generate_tool_api(bp).definition_set()

    def bad(mutate):
        d = copy.deepcopy(good)
        mutate(d["tools"])
        d["contentHash"] = None
        return {i.code for i in check_tool_api(d["tools"])}

    def r4(tools):
        next(t for t in tools if t["name"] == "blueprint.propose_change")["agent_creatable"] = True
    assert "TAPI-RISK-001" in bad(r4)

    def r4t(tools):
        next(t for t in tools if t["name"] == "sales_invoice.transition")["transitions"][3]["agent_creatable"] = True
    assert "TAPI-RISK-001" in bad(r4t)

    def arg(tools):
        t = next(t for t in tools if t["name"] == "customer.get")
        t["input_schema"]["properties"]["tenantId"] = {"type": "string"}
    assert "TAPI-ARG-001" in bad(arg)

    def nested(tools):
        t = next(t for t in tools if t["name"] == "sales_order.create")
        t["input_schema"]["properties"]["lines"]["items"]["properties"]["user_id"] = {"type": "string"}
    assert "TAPI-ARG-001" in bad(nested)

    def dup(tools):
        tools.append(copy.deepcopy(tools[0]))
    assert "TAPI-NAME-001" in bad(dup)

    def badname(tools):
        tools[0]["name"] = "عميل.get"
    assert "TAPI-NAME-004" in bad(badname)

    def noroles(tools):
        tools[0]["requires"]["roles"] = []
    assert "TAPI-ROLE-001" in bad(noroles)

    def idem(tools):
        next(t for t in tools if t["name"] == "customer.create")["idempotency"] = "none"
    assert "TAPI-IDEM-001" in bad(idem)

    def appr(tools):
        next(t for t in tools if t["name"] == "payment.create")["approval"]["agent_required"] = False
    assert "TAPI-APPROVAL-001" in bad(appr)

    def opened(tools):
        del next(t for t in tools if t["name"] == "customer.create")["input_schema"]["additionalProperties"]
    assert "TAPI-SCHEMA-001" in bad(opened)

    def leak(tools):
        tools[0]["description"] = "talks to ERPNext"
    assert "TAPI-LEAK-001" in bad(leak)

    tampered = copy.deepcopy(good)
    tampered["tools"][0]["description"] = "changed"
    assert "TAPI-HASH-001" in {i.code for i in check_tool_api(tampered)}
    assert "TAPI-SHAPE-001" in {i.code for i in check_tool_api("x")}


def test_cli(bp, tmp_path):
    env = {"PYTHONPATH": str(OPERATE), "PATH": ""}
    ok = subprocess.run([sys.executable, "-m", "toolapi", str(FIXTURE)], capture_output=True, env=env)
    assert ok.returncode == 0
    assert json.loads(ok.stdout)["contentHash"] == generate_tool_api(bp).content_hash
    assert ok.stdout == to_bytes(generate_tool_api(bp).definition_set())
    bp["entities"][0]["fields"][0]["type"] = "geo_point"
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bp))
    r = subprocess.run([sys.executable, "-m", "toolapi", str(p)], capture_output=True, env=env)
    assert r.returncode == 1 and r.stdout == b"" and b"TAPI-FIELD-001" in r.stderr
    r = subprocess.run([sys.executable, "-m", "toolapi", str(tmp_path / "missing.json")], capture_output=True, env=env)
    assert r.returncode == 1
