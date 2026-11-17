"""DSC-012 Odoo extractor: read-only enforcement (PI-006), L3 labelling (PI-003), budgets, no secrets."""
import json

import pytest

from connectors import Limits, Registry, RunContext, iter_envelopes, run_connector
from connectors.odoo import (DEFAULT_MODELS, MAPPING, TYPE_MAP, OdooConnector, ReadOnlyGateway, READ_METHODS,
                             Odo001MethodNotAllowed, Odo002WriteRefused, Odo003ModelNotAllowed, Odo004BadCall,
                             Odo005SecretLike, Odo007BadConfig, Odo008TransportFailure, Odo009MalformedResponse,
                             register)
from fake_transport import HOSTILE, CANARY, FakeTransport

CTX = RunContext(tenant_id="t-test", job_id="job1")
MODELS = ("res.partner", "res.company")


def run(t, source=b"", ctx=CTX, **kw):
    kw.setdefault("models", MODELS)
    c = OdooConnector(t, **kw)
    ev = []
    return run_connector(c, source, ctx, ev.append), ev


def ent(out, name):
    return next(e for e in out["entities"] if e["name"]["text"] == name)


def cells(out, model="res.partner"):
    return {f["source"]["path"]: f for f in ent(out, model)["fields"]}


def issues(out, code):
    return [i["detail"]["text"] for i in out["issues"] if i["code"]["text"] == code]


def refusal_class(out):
    assert not out["ok"] and out["code"] == "CON-010"
    return out["reason"]


def test_registered_tier1_readonly_and_all_text_is_l3():
    reg = Registry()
    c = register(reg, FakeTransport(), models=MODELS)
    assert reg.get("discovery.odoo") is c and c.tier == 1 and c.writes is False and c.capabilities == {"read"}
    out, _ = run(FakeTransport())
    assert out["ok"] and out["source"]["tier"] == 1
    assert all(e["level"] == "L3" and e["trust"] == "untrusted" for e in iter_envelopes(out))


@pytest.mark.parametrize("m", sorted(READ_METHODS - {"version"}))
def test_read_methods_pass(m):
    t = FakeTransport()
    gw = ReadOnlyGateway(t, frozenset(MODELS))
    args = {"read": [[1]], "name_get": [[1]]}.get(m, [[]] if m == "search_count" else [])
    kw = {"limit": 5} if m == "search_read" else {}
    if m == "search_read":
        kw["fields"] = ["id"]
    if m in ("read", "name_get"):
        t.call = lambda *a: []  # shape only; the gateway is what is under test
    gw.call("res.partner", m, args, kw)
    assert gw.calls == 1


@pytest.mark.parametrize("m", ["write", "create", "unlink", "copy", "execute_kw", "execute", "action_confirm",
                               "button_validate", "message_post", "_compute", "Write", "post", "load"])
def test_write_style_methods_refused(m):
    t = FakeTransport()
    gw = ReadOnlyGateway(t, frozenset(MODELS))
    with pytest.raises(Odo002WriteRefused):
        gw.call("res.partner", m, [[1], {"name": "x"}], {})
    assert t.log == []


@pytest.mark.parametrize("m", ["frobnicate", "search", "read_group", "", None, 5])
def test_unknown_methods_refused(m):
    t = FakeTransport()
    with pytest.raises(Odo001MethodNotAllowed):
        ReadOnlyGateway(t, frozenset(MODELS)).call("res.partner", m, [], {})
    assert t.log == []


def test_unknown_model_refused_in_gateway_and_request():
    t = FakeTransport()
    gw = ReadOnlyGateway(t, frozenset(MODELS))
    for model in ("res.users", "ir.config_parameter", "", None):
        with pytest.raises(Odo003ModelNotAllowed):
            gw.call(model, "search_read", [[]], {"limit": 1})
    with pytest.raises(Odo003ModelNotAllowed):
        gw.call("res.partner", "version", [], {})
    assert t.log == []
    out, _ = run(t, json.dumps({"models": ["res.users"]}).encode())
    assert refusal_class(out) == "extract raised Odo003ModelNotAllowed"
    assert t.log == []


def test_bad_call_shapes_refused():
    gw = ReadOnlyGateway(FakeTransport(), frozenset(MODELS))
    for kw in ({}, {"limit": 0}, {"limit": 501}, {"limit": True}, {"limit": 5, "sudo": True}):
        with pytest.raises(Odo004BadCall):
            gw.call("res.partner", "search_read", [[]], kw)
    with pytest.raises(Odo004BadCall):
        gw.call("res.partner", "read", [list(range(501))], {})


def test_secrets_refused_in_input_and_never_echoed():
    t = FakeTransport()
    for body in ({"api_key": CANARY}, {"models": ["res.partner"], "auth": {"Password": CANARY}}):
        out, _ = run(t, json.dumps(body).encode())
        assert refusal_class(out) == "extract raised Odo005SecretLike" and CANARY not in json.dumps(out)
    with pytest.raises(Odo005SecretLike) as e:
        ReadOnlyGateway(t, frozenset(MODELS)).call("res.partner", "fields_get", [], {"context": {"token": CANARY}})
    assert CANARY not in str(e.value)
    assert t.log == []


def test_transport_error_text_is_dropped_and_secret_never_in_output_events_or_repr():
    class Boom(FakeTransport):
        def call(self, *a):
            raise RuntimeError(f"connect failed password={CANARY}")
    out, ev = run(Boom())
    assert refusal_class(out) == "extract raised Odo008TransportFailure"
    assert CANARY not in json.dumps(out) + json.dumps(ev)
    t = FakeTransport()
    out, ev = run(t)
    assert out["ok"] and CANARY not in json.dumps(out, ensure_ascii=False) + json.dumps(ev)
    assert CANARY not in repr(OdooConnector(t)) and CANARY not in repr(ReadOnlyGateway(t, frozenset()))
    with pytest.raises(Odo008TransportFailure) as e:
        Boom().call  # noqa: B018
        ReadOnlyGateway(Boom(), frozenset(MODELS)).call("res.partner", "fields_get", [], {})
    assert CANARY not in str(e.value) and e.value.__cause__ is None


def test_secret_like_fields_withheld_not_fetched():
    t = FakeTransport()
    out, _ = run(t)
    fetched = set(t.reads("res.partner")[0][2]["fields"])
    assert "signup_token" not in fetched and "signup_token" not in json.dumps(
        [c["text"] for c in cells(out).values()])
    assert any("signup_token" in d for d in issues(out, "secret_like_field_withheld"))
    assert out["stats"]["secret_like_withheld"] == 1


def test_binary_not_fetched_and_flagged():
    t = FakeTransport()
    out, _ = run(t)
    assert "image_1920" not in t.reads("res.partner")[0][2]["fields"]
    assert any("image_1920" in d for d in issues(out, "binary_not_fetched"))
    assert not any(p.endswith(".image_1920") for p in (f["source"]["path"] for f in ent(out, "res.partner")["fields"]
                                                      if f["source"]["kind"] == "cell"))
    assert out["stats"]["binary_fields_skipped"] == 1


def test_odoo_conventions_many2one_false_selection_x2many_boolean():
    out, _ = run(FakeTransport())
    c = cells(out)
    assert c["res.partner[1].company_id"]["text"] == "Sample Co"
    assert c["res.partner[1].company_id#id"]["text"] == "1"
    assert c["res.partner[1].currency_id"]["text"] == "SAR"  # multi-currency preserved
    assert "res.partner[1].email" not in c and c["res.partner[2].email"]["text"] == "p2@example.invalid"
    assert "res.partner[1].x_custom_note" not in c  # False is empty, not the text "False"
    assert out["stats"]["empty_cells"] > 0
    assert c["res.partner[1].is_company"]["text"] == "true" and c["res.partner[2].is_company"]["text"] == "false"
    assert c["res.partner[1].state"]["text"] == "draft" and c["res.partner[2].state"]["text"] == "done"
    assert "res.partner[1].child_ids" not in c  # empty x2many
    assert c["res.partner[1].create_date"]["text"] == "2000-01-01 00:00:00"
    assert c["res.partner[1].name"]["text"] == "شركة الاختبار 1"  # Arabic kept as data


def test_field_metadata_labels_selection_required_relation():
    out, _ = run(FakeTransport())
    c = cells(out)
    assert c["res.partner.name#label"]["text"] == "الاسم"
    assert "required=true" in c["res.partner.name#spec"]["text"]
    assert "selection=draft:مسودة|done:Done" in c["res.partner.state#spec"]["text"]
    assert "relation=res.company" in c["res.partner.company_id#spec"]["text"]
    assert "neutral_type=reference" in c["res.partner.company_id#spec"]["text"]
    assert c["res.partner.name#map"]["text"] == "party.name:text"
    assert c["res.partner.company_id#map"]["text"] == "record.company:reference"  # multi-company generic


def test_unmapped_fields_reported_not_dropped():
    out, _ = run(FakeTransport())
    c = cells(out)
    assert "res.partner.x_custom_note#map" not in c and "res.partner.x_custom_note#spec" in c
    assert any(d.startswith("res.partner.x_custom_note") for d in issues(out, "unmapped_field"))
    assert out["stats"]["unmapped_fields"] >= 1
    # a model with no mapping at all is reported once, every field unmapped
    t = FakeTransport()
    t.data["x.custom"] = ({"id": {"type": "integer", "string": "ID"}, "foo": {"type": "char", "string": "Foo"}},
                          [{"id": 1, "foo": "bar"}])
    out, _ = run(t, models=("x.custom",))
    assert issues(out, "unmapped_model") and ent(out, "x.custom")["fields"]
    assert any(d.startswith("x.custom.foo") for d in issues(out, "unmapped_field"))


def test_paging_across_pages_and_hard_page_size():
    t = FakeTransport(partners=7)
    out, _ = run(t, page_size=3)
    reads = t.reads("res.partner")
    assert [r[2]["offset"] for r in reads] == [0, 3, 6] and all(r[2]["limit"] <= 3 for r in reads)
    assert out["stats"]["records"] == 8 and len(
        [p for p in cells(out) if p.endswith(".id") and "[" in p]) == 7  # 7 partners + company handled below
    assert not issues(out, "budget_stopped_paging")
    with pytest.raises(Odo007BadConfig):
        OdooConnector(FakeTransport(), page_size=501)


def test_page_and_record_budgets_stop_paging():
    t = FakeTransport(partners=20)
    out, _ = run(t, page_size=3, max_pages=2)
    assert len(t.reads("res.partner")) == 2 and out["stats"]["truncated_models"] == 1
    assert "pages" in issues(out, "budget_stopped_paging")[0]
    t = FakeTransport(partners=20)
    out, _ = run(t, page_size=4, max_records_per_model=6)
    assert [r[2]["limit"] for r in t.reads("res.partner")] == [4, 2] and "records" in issues(
        out, "budget_stopped_paging")[0]
    t = FakeTransport(partners=20)
    out, _ = run(t, page_size=5, max_records_total=9)
    assert sum(r[2]["limit"] for r in t.reads()) <= 9
    # framework budgets still apply: steps -> CON-013
    out, _ = run(FakeTransport(partners=20), ctx=RunContext(tenant_id="t", job_id="j", limits=Limits(max_steps=30)))
    assert not out["ok"] and out["code"] == "CON-013"


def test_deterministic():
    a, _ = run(FakeTransport(hostile_at=2))
    b, _ = run(FakeTransport(hostile_at=2))
    assert json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)


def test_hostile_text_is_l3_and_flagged_never_acted_on():
    t = FakeTransport(hostile_at=3)
    out, ev = run(t)
    f = cells(out)["res.partner[3].name"]
    assert f["text"] == HOSTILE and f["level"] == "L3" and f["trust"] == "untrusted"
    assert "instruction_like" in f["sanitisation"]["flags"]
    assert any(e["type"] == "injection.suspected" for e in ev)
    assert all(c[1] in READ_METHODS for c in t.log)  # nothing but reads, whatever the data says


def test_model_unavailable_is_reported_not_fatal():
    out, _ = run(FakeTransport(missing=("res.company",)))
    assert out["ok"] and issues(out, "model_unavailable") and out["stats"]["models_unavailable"] == 1


def test_malformed_responses_fail_closed():
    class Bad(FakeTransport):
        def call(self, model, method, args, kwargs):
            if method == "search_count":
                return "many"
            return super().call(model, method, args, kwargs)
    out, _ = run(Bad())
    assert refusal_class(out) == "extract raised Odo009MalformedResponse"


def test_version_metadata_and_server_entity():
    out, _ = run(FakeTransport())
    assert {f["source"]["path"]: f["text"] for f in ent(out, "server")["fields"]}["server.server_version"] == "17.0"


def test_default_models_and_mapping_tables():
    for m in ("res.partner", "product.product", "product.category", "uom.uom", "account.tax", "account.account",
              "account.journal", "sale.order", "sale.order.line", "purchase.order", "purchase.order.line",
              "account.move", "account.move.line", "stock.location", "stock.warehouse", "stock.quant",
              "account.payment"):
        assert m in DEFAULT_MODELS and m in MAPPING
    assert all(nt in set(TYPE_MAP.values()) for d in MAPPING.values() for _, nt in d.values())
    assert "binary" in TYPE_MAP.values()
