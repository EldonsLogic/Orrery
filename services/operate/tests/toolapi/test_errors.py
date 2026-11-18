import copy
import json

import pytest
from conftest import OPERATE
from jsonschema import Draft202012Validator
from toolapi import build_error, load_catalog, render_message, validate_catalog
from toolapi.errors import internal_error

CONTRACTS = OPERATE.parents[1] / "contracts"


@pytest.fixture
def cat():
    return load_catalog()


def test_catalog_valid_and_schema(cat):
    assert validate_catalog(cat) == []
    schema = json.loads((CONTRACTS / "tool-api-error-catalog.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert list(Draft202012Validator(schema).iter_errors(cat)) == []
    assert len(cat["entries"]) == 14


def _bad(cat, fn):
    c = copy.deepcopy(cat)
    fn(c["entries"][0])
    return validate_catalog(c)


def test_validate_failure_modes(cat):
    e0 = cat["entries"][0]["id"]
    assert any("undeclared" in p for p in _bad(cat, lambda e: e["messages"].update(en=e["messages"]["en"] + " {oops}")))
    assert any("does not use" in p for p in _bad(cat, lambda e: e["messages"].update(ar="نص")))
    assert any("messages.ar missing" in p for p in _bad(cat, lambda e: e["messages"].pop("ar")))
    assert any("message_key" in p for p in _bad(cat, lambda e: e.update(message_key="errors.domain.other")))
    assert any("message_key" in p for p in _bad(cat, lambda e: e.update(message_key="x." + e0)))
    assert any("class" in p for p in _bad(cat, lambda e: e.update({"class": "internal_error"})))
    assert any("free-text" in p for p in _bad(cat, lambda e: e["params"].update(note={"type": "string", "max_length": 20})))
    assert any("snake_case" in p for p in _bad(cat, lambda e: e.update(id="Bad-Id")))
    for text in ("Frappe rejected {item} {warehouse} {shortfall_qty}", "SELECT name FROM x {item} {warehouse} {shortfall_qty}",
                 "see /apps/x/y.py {item} {warehouse} {shortfall_qty}", "Traceback {item} {warehouse} {shortfall_qty}"):
        assert any("engine" in p for p in _bad(cat, lambda e, t=text: e["messages"].update(en=t))), text
    dup = copy.deepcopy(cat)
    dup["entries"].append(copy.deepcopy(dup["entries"][0]))
    assert any("duplicate" in p for p in validate_catalog(dup))
    assert validate_catalog({"entries": []})


def test_no_engine_names_in_catalog():
    raw = (CONTRACTS / "tool-api-error-catalog.json").read_text(encoding="utf-8").lower()
    for name in ("frappe", "erpnext"):
        assert name not in raw


def test_build_error_happy(cat):
    err = build_error("insufficient_stock", {"item": "ITEM-0001", "warehouse": "Main-Store", "shortfall_qty": "12.5"}, cat)
    assert err["code"] == "guard_failed" and err["message_key"] == "errors.guard_failed" and err["retryable"] is False
    assert err["domain"]["code"] == "insufficient_stock"
    assert build_error("insufficient_stock", err["domain"]["params"], cat) == err  # deterministic
    assert build_error("duplicate_tax_id", {}, cat)["code"] == "invalid_arguments"
    assert build_error("stale_approval_state", {"changed": "amount"}, cat)["retryable"] is True


@pytest.mark.parametrize("code,params", [
    ("no_such_code", {}),
    (None, {}),
    ("insufficient_stock", {}),
    ("insufficient_stock", {"item": "A", "warehouse": "B", "shortfall_qty": "1", "extra": "x"}),
    ("insufficient_stock", {"item": "A", "warehouse": "B", "shortfall_qty": "1e5"}),
    ("insufficient_stock", {"item": "A B<script>", "warehouse": "B", "shortfall_qty": "1"}),
    ("insufficient_stock", {"item": "A" * 65, "warehouse": "B", "shortfall_qty": "1"}),
    ("stale_approval_state", {"changed": "not_in_enum"}),
    ("currency_rate_missing", {"currency": "SAR", "date": "2026-13-45"}),
    ("duplicate_tax_id", "not a dict"),
])
def test_build_error_fails_closed(cat, code, params):
    err = build_error(code, params, cat)
    assert err["code"] == "internal_error" and "domain" not in err
    assert set(err["details"]) == {"correlation_id"}
    assert build_error(code, params, cat, correlation_id="c1") == internal_error("c1")


def test_render_en_ar(cat):
    err = build_error("currency_rate_missing", {"currency": "USD", "date": "2026-03-01"}, cat)
    assert render_message(err, "en", cat) == "No exchange rate is set for USD on 2026-03-01."
    assert "USD" in render_message(err, "ar", cat) and "سعر صرف" in render_message(err, "ar", cat)
    assert render_message(err, "fr", cat) == render_message(err, "en", cat)  # falls back to English
    assert render_message({"code": "engine_error"}, "en", cat) == ""  # no domain: caller uses message_key


def test_render_hostile_params(cat):
    err = build_error("required_field_missing", {"field": "customer_name"}, cat)
    # hostile text can only arrive via a tampered error; the renderer still escapes and strips it
    err["domain"]["params"]["field"] = "<img src=x onerror=1>‮⁦evil‏\n"
    out = render_message(err, "ar", cat)
    assert "<" not in out and ">" not in out and "&lt;img" in out
    assert not any(c in out for c in "‮⁦‏\n")
    assert render_message(err, "ar", cat) == out
