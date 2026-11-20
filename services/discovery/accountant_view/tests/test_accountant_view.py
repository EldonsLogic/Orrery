import copy
import datetime as dt
import json
import re
from pathlib import Path

import pytest

from accountant_view import (AccountantViewError, Signer, add_comment, blueprint_digest, build_review, labels,
                             record_decision)
from accountant_view.money import money, percent_basis_points, to_minor
from accountant_view.review import Comment, Decision

ROOT = Path(__file__).resolve().parents[4]
BP = json.loads((ROOT / "contracts/examples/blueprint-trading-minimal.json").read_text(encoding="utf-8"))
T = "tenant-a"
NOW = dt.datetime(2026, 11, 20, 10, 0, tzinfo=dt.timezone.utc)
ACC = Signer(T, "acc-1", ("accountant",), "human")


def bp(**kw):
    return copy.deepcopy(BP)


def sec(view, name):
    return next(s for s in view["sections"] if s["id"] == name)


def code(fn, *a, **k):
    with pytest.raises(AccountantViewError) as e:
        fn(*a, **k)
    return e.value.code


def dec(records=(), section="tax_vat", decision="approved", note="", actor=ACC, blueprint=None, **kw):
    return record_decision(blueprint or BP, records, tenant_id=T, actor=actor, section=section, decision=decision,
                           decided_at=NOW, now=NOW, note=note, **kw)


# ---- money -----------------------------------------------------------------------------------------------------
def test_money_minor_units_exact():
    assert to_minor(50000, "SAR") == 5_000_000
    assert to_minor("12.34", "SAR") == 1234 and to_minor("1.234", "KWD") == 1234
    assert money(5_000_000, "SAR") == {"minor": 5_000_000, "currency": "SAR", "exponent": 2, "text": "50000.00"}
    assert money(-5, "SAR")["text"] == "-0.05"


@pytest.mark.parametrize("bad", [1.5, True, None, "1e3", "NaN", "0.001", [1], 10 ** 17])
def test_money_refuses_floats_and_loss(bad):
    with pytest.raises(AccountantViewError):
        to_minor(bad, "SAR")


def test_percent_basis_points():
    assert percent_basis_points(15) == 1500 and percent_basis_points(15.5) == 1550
    for bad in (15.555, -1, 101, True, "15"):
        with pytest.raises(AccountantViewError):
            percent_basis_points(bad)


# ---- view ------------------------------------------------------------------------------------------------------
def test_sections_in_order_and_content():
    v = build_review(BP, tenant_id=T)
    assert [s["id"] for s in v["sections"]] == ["chart_of_accounts", "tax_vat", "e_invoicing", "approval_thresholds",
                                               "posting_rules", "numbering"]
    tax = {i["key"]: i["value"] for i in sec(v, "tax_vat")["items"]}
    assert tax["vat_rate"] == 1500 and tax["vat_filing_period"] == "quarterly" and tax["vat_prices_include"] is False
    einv = {i["key"]: i["value"] for i in sec(v, "e_invoicing")["items"]}
    assert einv["einv_mode"] == "zatca_phase2" and einv["einv_environment"] == "sandbox"
    rule = sec(v, "approval_thresholds")["rules"][0]
    assert rule["conditions"][0]["value"] == {"minor": 5_000_000, "currency": "SAR", "exponent": 2, "text": "50000.00"}
    assert rule["steps"][0]["approverRole"] and rule["selfApproval"] is False
    n = sec(v, "numbering")["entities"]
    so = next(e for e in n if e["entity"] == "sales_order")
    assert so["example"] == "SO-00001" and so["resetPerFiscalYear"] is True
    assert any(not e["configured"] for e in n)  # document entities without numbering are surfaced


def test_missing_sections_are_honest_and_not_signable():
    v = build_review(BP, tenant_id=T)
    assert sec(v, "chart_of_accounts")["status"] == "not_in_blueprint"
    assert sec(v, "chart_of_accounts")["signOff"]["state"] == "not_applicable"
    assert sec(v, "posting_rules")["status"] == "not_in_blueprint"
    assert code(dec, section="chart_of_accounts") == "ACV-SO-006"


def test_view_is_pure_and_input_untouched():
    before = copy.deepcopy(BP)
    a, b = build_review(BP, tenant_id=T), build_review(BP, tenant_id=T)
    assert a == b and BP == before
    json.dumps(a)  # plain data


def test_invalid_blueprint_refused():
    bad = bp()
    del bad["compliance"]["vat"]
    assert code(build_review, bad, tenant_id=T) == "ACV-BP-002"
    assert code(build_review, [], tenant_id=T) == "ACV-BP-001"


def test_money_condition_needs_currency():
    b = bp()
    del b["company"]["locale"]["currency"]
    assert code(build_review, b, tenant_id=T) == "ACV-MONEY-001"


def test_float_threshold_refused():
    b = bp()
    b["approvals"][0]["conditions"][0]["value"] = 50000.5
    assert code(build_review, b, tenant_id=T).startswith("ACV-MONEY")


def test_no_approvals_is_empty_and_signable():
    b = bp()
    b["approvals"] = []
    v = build_review(b, tenant_id=T)
    assert sec(v, "approval_thresholds")["status"] == "empty"
    recs = record_decision(b, (), tenant_id=T, actor=ACC, section="approval_thresholds", decision="approved",
                           decided_at=NOW, now=NOW, note="")
    assert sec(build_review(b, recs, tenant_id=T), "approval_thresholds")["signOff"]["state"] == "approved"


# ---- sign-off rules --------------------------------------------------------------------------------------------
def test_decision_recorded_and_overall():
    recs = ()
    for s in ("tax_vat", "e_invoicing", "approval_thresholds", "numbering"):
        recs = dec(recs, section=s)
    v = build_review(BP, recs, tenant_id=T)
    assert v["overall"] == {"state": "approved", "labelKey": "acv.state.approved", "evidenceOnly": True, "staleRecords": 0}
    d = sec(v, "tax_vat")["signOff"]["decision"]
    assert d["userId"] == "acc-1" and d["decidedAt"] == "2026-11-20T10:00:00.000Z"


def test_partial_is_awaiting_and_changes_requested_wins():
    recs = dec()
    assert build_review(BP, recs, tenant_id=T)["overall"]["state"] == "awaiting"
    recs = dec(recs, section="numbering", decision="changes_requested", note="Reset numbers per branch")
    assert build_review(BP, recs, tenant_id=T)["overall"]["state"] == "changes_requested"
    assert code(dec, recs, section="numbering", decision="changes_requested", note="x") == "ACV-SO-007"


def test_changes_requested_needs_note():
    assert code(dec, decision="changes_requested", note="  ") == "ACV-SO-008"


def test_append_only_and_final():
    recs = dec()
    assert code(dec, recs, decision="changes_requested", note="n") == "ACV-SO-007"
    assert dec(recs, section="numbering")[: len(recs)] == recs  # old records kept as they were
    assert code(dec, recs) == "ACV-SO-007"


def test_human_only_tenant_bound_role():
    assert code(dec, actor=Signer(T, "bot", ("accountant",), "agent")) == "ACV-SO-002"
    assert code(dec, actor=Signer(T, "svc", ("accountant",), "service")) == "ACV-SO-002"
    assert code(dec, actor=Signer("tenant-b", "acc-1", ("accountant",), "human")) == "ACV-SO-003"
    assert code(dec, actor=Signer(T, "own-1", ("owner",), "human")) == "ACV-SO-004"
    assert code(dec, actor=Signer(T, "acc-1", ["accountant"], "human")) == "ACV-SO-004"
    assert code(dec, actor="acc-1") == "ACV-SO-002"
    assert code(dec, actor=Signer(T, "a b", ("accountant",), "human")) == "ACV-SO-002"


def test_no_defaults_and_clock_is_callers():
    with pytest.raises(TypeError):
        record_decision(BP, (), tenant_id=T, actor=ACC, section="tax_vat", decision="approved")
    naive = dt.datetime(2026, 11, 20, 10, 0)
    assert code(record_decision, BP, (), tenant_id=T, actor=ACC, section="tax_vat", decision="approved",
                decided_at=naive, now=NOW, note="") == "ACV-SO-001"
    assert code(record_decision, BP, (), tenant_id=T, actor=ACC, section="tax_vat", decision="approved",
                decided_at=NOW + dt.timedelta(hours=1), now=NOW, note="") == "ACV-SO-001"
    assert code(dec, decision="auto") == "ACV-SO-001"
    assert code(dec, section="nope") == "ACV-SO-005"


def test_decision_goes_stale_when_blueprint_changes():
    recs = dec()
    changed = bp()
    changed["compliance"]["vat"]["defaultRatePercent"] = 5
    assert blueprint_digest(changed) != blueprint_digest(BP)
    v = build_review(changed, recs, tenant_id=T)
    assert sec(v, "tax_vat")["signOff"]["state"] == "awaiting" and v["overall"]["staleRecords"] == 1
    assert dec(recs, blueprint=changed)  # may decide again on the new version


def test_stored_records_validated_fail_closed():
    good = dec()[0]
    forged = [Decision("tenant-b", good.blueprint_digest, "tax_vat", "x1", "approved", good.decided_at, "")]
    assert code(build_review, BP, forged, tenant_id=T) == "ACV-REC-001"
    for bad in ("nope", None, {"a": 1}, [object()],
                [Decision(T, "zz", "tax_vat", "x1", "approved", good.decided_at, "")],
                [Decision(T, good.blueprint_digest, "tax_vat", "x1", "auto", good.decided_at, "")],
                [Decision(T, good.blueprint_digest, "tax_vat", "x1", "changes_requested", good.decided_at, "")]):
        assert code(build_review, BP, bad, tenant_id=T) == "ACV-REC-001"
    assert code(build_review, BP, [good, good], tenant_id=T) == "ACV-REC-002"


# ---- comments --------------------------------------------------------------------------------------------------
def com(records=(), section="tax_vat", text="Check the VAT rate", actor=ACC):
    return add_comment(BP, records, tenant_id=T, actor=actor, section=section, text=text, created_at=NOW, now=NOW)


def test_comments_append_only_and_ids_in_order():
    r = com()
    r = com(r, text="Second")
    assert [c.comment_id for c in r] == ["c000001", "c000002"]
    v = build_review(BP, r, tenant_id=T)
    assert [c["text"] for c in sec(v, "tax_vat")["comments"]] == ["Check the VAT rate", "Second"]
    assert sec(v, "numbering")["comments"] == []
    assert com(r, section="chart_of_accounts")  # comments are allowed on sections that cannot be signed off


def test_comment_rules():
    assert code(com, actor=Signer(T, "bot", ("accountant",), "agent")) == "ACV-SO-002"
    assert code(com, actor=Signer(T, "o1", ("owner",), "human")) == "ACV-SO-004"
    assert code(com, text="  ​ ") == "ACV-SO-009"
    assert code(com, text=5) == "ACV-SO-009"
    assert code(com, section="x") == "ACV-SO-005"


def test_untrusted_text_is_cleaned_and_flagged():
    r = com(text="a‮b\u0000c​d" + "x" * 5000)
    assert r[0].text.startswith("abcd") and len(r[0].text) == 2000
    c = build_review(BP, r, tenant_id=T)["sections"][1]["comments"][0]
    assert c["untrustedText"] is True
    d = dec(note="<script>alert(1)</script>")[0]  # kept as data; the screen escapes it
    assert d.note == "<script>alert(1)</script>"


# ---- labels, tokens, engine name -------------------------------------------------------------------------------
def test_labels_same_keys_and_cover_view_keys():
    en, ar = labels("en"), labels("ar")
    assert set(en) == set(ar) and all(v.strip() for v in en.values()) and all(v.strip() for v in ar.values())
    assert any(re.search("[؀-ۿ]", v) for v in ar.values())
    recs = com()
    for s in ("tax_vat",):
        recs = dec(recs, section=s)
    keys = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k.endswith("LabelKey") or k.endswith("Key") or k == "labelKey":
                    keys.add(v)
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)
    walk(build_review(BP, recs, tenant_id=T))
    assert keys and keys <= set(en), sorted(keys - set(en))
    for rule in build_review(BP, tenant_id=T)["sections"][3]["rules"]:
        for c in rule["conditions"]:
            assert "acv.op." + c["op"] in en
        assert "acv.action_type." + rule["action"] in en
        for s in rule["steps"]:
            assert "acv.mode." + s["mode"] in en
    with pytest.raises(ValueError):
        labels("fr")


def test_no_engine_name_or_colours_in_package():
    for p in Path(__file__).resolve().parents[1].glob("*.*"):
        t = p.read_text(encoding="utf-8").lower()
        assert "frappe" not in t and "erpnext" not in t, p
        assert not re.search(r"#[0-9a-f]{3,8}\b|\brgb\(", t), p


def test_no_clock_or_model_use():
    for p in Path(__file__).resolve().parents[1].glob("*.py"):
        t = p.read_text(encoding="utf-8")
        assert "datetime.now" not in t and "utcnow" not in t and "time.time" not in t, p
        assert not re.search(r"anthropic|openai|requests|urllib", t), p
