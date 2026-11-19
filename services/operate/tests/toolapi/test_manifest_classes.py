"""ADR-0037: component manifests declare entity risk classes (raise only); the Blueprint carries transitions[].kind."""
import copy
import json

import pytest

from conftest import OPERATE
from toolapi import check_tool_api, generate_tool_api
from toolapi import policy as P

CONTRACTS = OPERATE.parents[1] / "contracts"
L0 = "l0:platform-policy-test"


def codes(res):
    return {e.code for e in res.errors}


def tool(res, name):
    return next(t for t in res.tools if t["name"] == name)


def add_entity(b, eid, kind="document"):
    b["entities"].append({"id": eid, "kind": kind, "labels": {"ar": eid, "en": eid},
                          "fields": [{"id": "amount", "type": "decimal", "labels": {"en": "Amount"}}]})
    owner = next(r for r in b["roles"] if r["id"] == "owner")
    owner["permissions"].append({"entity": eid, "actions": ["read", "create", "update", "submit", "cancel", "delete"]})
    return b


def manifest(decls, level="reviewed", mid="sales.warranty", version="0.1.0"):
    """Only the parts the generator reads; schema validity is tested separately below."""
    return {"id": mid, "version": version, "certification": {"level": level},
            "provides": [{"capability": f"{mid}.entities",
                          "artifacts": [{"type": "entity", "ref": r, "riskClass": c} for r, c in decls.items()]}]}


# ---- class source --------------------------------------------------------------------------------------------------
def test_absent_from_manifest_and_table_stays_refused(mini):
    res = generate_tool_api(add_entity(mini, "warranty_claim"), manifests=[manifest({"other_thing": "plain"})])
    assert "TAPI-CLASS-001" in codes(res) and res.tools == []


@pytest.mark.parametrize("decl,cls,cancel", [("plain", "plain", "R2"), ("stock", "stock", "R4"), ("ledger", "ledger", "R4"),
                                             ("tax", "ledger", "R4")])
def test_reviewed_manifest_classifies_unknown_entity(mini, decl, cls, cancel):
    ms = [manifest({"warranty_claim": decl})]
    res = generate_tool_api(add_entity(mini, "warranty_claim"), manifests=ms)
    assert res.ok, [str(e) for e in res.errors]
    assert tool(res, "warranty_claim.create")["entity_class"] == cls
    assert tool(res, "warranty_claim.cancel")["risk_class"] == cancel
    assert check_tool_api(res.definition_set(), manifests=ms) == []


def test_tax_adds_the_tax_effect_on_writes_only(mini):
    res = generate_tool_api(add_entity(mini, "warranty_claim"), manifests=[manifest({"warranty_claim": "tax"})])
    sub = tool(res, "warranty_claim.submit")
    assert sub["effects"]["tax"] is True and sub["effects"]["ledger"] is True and sub["approval"]["agent_required"] is True
    assert tool(res, "warranty_claim.get")["effects"]["tax"] is False


def test_unreviewed_manifest_cannot_introduce_a_class_but_can_raise(mini, bp):
    for level in ("draft", "tested"):
        res = generate_tool_api(add_entity(copy.deepcopy(mini), "warranty_claim"),
                                manifests=[manifest({"warranty_claim": "plain"}, level)])
        assert "TAPI-CLASS-001" in codes(res)
    res = generate_tool_api(bp, manifests=[manifest({"customer": "ledger"}, "draft")])
    assert res.ok and tool(res, "customer.create")["entity_class"] == "ledger"


def test_manifest_raises_a_reviewed_class(bp):
    ms = [manifest({"customer": "stock"})]
    res = generate_tool_api(bp, manifests=ms)
    assert tool(res, "customer.create")["entity_class"] == "stock"
    assert tool(res, "customer.create")["effects"]["ledger"] is True
    assert check_tool_api(res.definition_set(), manifests=ms) == []


@pytest.mark.parametrize("eid,decl", [("sales_invoice", "plain"), ("delivery_note", "plain"), ("sales_invoice", "stock"),
                                      ("petty_cash_voucher", "plain")])
def test_manifest_may_not_lower(mini, eid, decl):
    if eid == "petty_cash_voucher":
        add_entity(mini, eid)  # unlisted, ledger by name token
    res = generate_tool_api(mini, manifests=[manifest({eid: decl})])
    assert "TAPI-MANIFEST-002" in codes(res) and res.tools == []


def test_same_class_is_not_lowering(bp):
    assert generate_tool_api(bp, manifests=[manifest({"sales_invoice": "ledger", "customer": "plain"})]).ok


def test_registry_and_manifest_take_the_highest(mini):
    add_entity(mini, "warranty_claim")
    reg = {"source": L0, "entity_classes": {"warranty_claim": "ledger"}}
    res = generate_tool_api(mini, reg, [manifest({"warranty_claim": "stock"})])
    assert tool(res, "warranty_claim.create")["entity_class"] == "ledger"


def test_conflicting_manifests_take_the_highest(mini):
    add_entity(mini, "warranty_claim")
    ms = [manifest({"warranty_claim": "plain"}), manifest({"warranty_claim": "stock"}, mid="stock.warranty")]
    assert tool(generate_tool_api(mini, manifests=ms), "warranty_claim.create")["entity_class"] == "stock"


def test_permission_entity_refused(mini, bp):
    res = generate_tool_api(add_entity(mini, "access_matrix"), manifests=[manifest({"access_matrix": "permission"})])
    assert "TAPI-DOMAIN-001" in codes(res)
    res = generate_tool_api(bp, manifests=[manifest({"customer": "permission"}, "draft")])
    assert "TAPI-DOMAIN-001" in codes(res)


@pytest.mark.parametrize("bad", ["nope", [1], [{"version": "0.1.0"}],
                                 [manifest({"warranty_claim": "secret"})],
                                 [{"id": "a.b", "version": "0.1.0", "provides": [{"artifacts": [
                                     {"type": "report", "ref": "x", "riskClass": "plain"}]}]}]])
def test_malformed_manifests_refused(bp, bad):
    assert "TAPI-MANIFEST-001" in codes(generate_tool_api(bp, manifests=bad))


# ---- recorded and rechecked ----------------------------------------------------------------------------------------
def test_manifests_recorded_and_checker_needs_them(bp):
    ms = [manifest({"customer": "stock"})]
    defs = generate_tool_api(bp, manifests=ms).definition_set()
    assert defs["manifests"]["components"] == ["sales.warranty@0.1.0"] and defs["manifests"]["sha256"].startswith("sha256:")
    assert defs["toolApiVersion"] == "0.2.0"
    assert "TAPI-MANIFEST-003" in {i.code for i in check_tool_api(defs)}
    assert "TAPI-MANIFEST-003" in {i.code for i in check_tool_api(defs, manifests=[manifest({"customer": "ledger"})])}
    plain = generate_tool_api(bp).definition_set()
    assert plain["manifests"] is None and check_tool_api(plain) == []
    assert "TAPI-MANIFEST-003" in {i.code for i in check_tool_api(plain, manifests=ms)}


def test_no_declarations_change_nothing(bp):
    a = generate_tool_api(bp)
    b = generate_tool_api(bp, manifests=[{"id": "core.x", "version": "1.0.0", "provides": []}])
    assert a.content_hash == b.content_hash and b.manifests is None


def test_cli_manifest(bp, tmp_path):
    import subprocess
    import sys
    (tmp_path / "bp.json").write_text(json.dumps(bp), encoding="utf-8")
    (tmp_path / "m.json").write_text(json.dumps(manifest({"customer": "stock"})), encoding="utf-8")
    out = subprocess.run([sys.executable, str(OPERATE / "toolapi" / "__main__.py"), str(tmp_path / "bp.json"),
                          "--manifest", str(tmp_path / "m.json")], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["manifests"]["components"] == ["sales.warranty@0.1.0"]


# ---- contracts carry the fields ------------------------------------------------------------------------------------
def _schema(name):
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def test_contract_enums_match_policy():
    bp = _schema("blueprint.schema.json")
    tr = bp["$defs"]["workflow"]["properties"]["transitions"]["items"]["properties"]["kind"]
    assert tuple(tr["enum"]) == P.TRANSITION_KINDS
    m = _schema("component.manifest.schema.json")
    art = m["properties"]["provides"]["items"]["properties"]["artifacts"]["items"]
    assert tuple(art["properties"]["riskClass"]["enum"]) == P.MANIFEST_RISK_CLASSES


def test_schemas_accept_new_fields_and_refuse_misuse(mini):
    js = pytest.importorskip("jsonschema")
    bp_v = js.Draft202012Validator(_schema("blueprint.schema.json"))
    wf = mini["workflows"][0]
    wf["transitions"][0]["kind"] = "advance"
    assert list(bp_v.iter_errors(mini)) == []
    wf["transitions"][0]["kind"] = "bogus"
    assert list(bp_v.iter_errors(mini)) != []
    m_v = js.Draft202012Validator(_schema("component.manifest.schema.json"))
    fixture = OPERATE.parents[1] / "services/blueprint/fixtures/registry/sales.credit_note.json"
    m = json.loads(fixture.read_text(encoding="utf-8"))
    assert list(m_v.iter_errors(m)) == []  # 0.1.0 manifests stay valid
    m["provides"][0]["artifacts"][0]["riskClass"] = "tax"
    assert list(m_v.iter_errors(m)) == []
    m["provides"][1]["artifacts"][0]["riskClass"] = "ledger"  # on a function artifact
    assert list(m_v.iter_errors(m)) != []
