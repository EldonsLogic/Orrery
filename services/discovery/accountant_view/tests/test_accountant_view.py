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


def test_missing_currency_uses_country_default():  # LOW
    b = bp()
    del b["company"]["locale"]["currency"]
    r = sec(build_review(b, tenant_id=T), "approval_thresholds")
    assert r["currency"] == "SAR" and r["currencySource"] == "country_default"
    assert r["rules"][0]["conditions"][0]["value"]["minor"] == 5_000_000


def _with_cond(field, op, value, entity="sales_order"):
    b = bp()
    b["approvals"][0]["appliesTo"]["entity"] = entity
    b["approvals"][0]["conditions"] = [{"field": field, "op": op, "value": value}]
    return b


def cond(b):
    return sec(build_review(b, tenant_id=T), "approval_thresholds")["rules"][0]["conditions"][0]


def test_threshold_units_lists_relations_percent_unknown():  # M3
    c = cond(_with_cond("total_amount", "in", [50000, "100000.50"]))
    assert c["kind"] == "list" and [x["value"]["minor"] for x in c["value"]] == [5_000_000, 10_000_050]
    b = _with_cond("customer.credit_limit", "gte", 50000)
    b["entities"][2].setdefault("relations", []).append({"id": "customer", "target": "customer", "cardinality": "one"})
    assert cond(b)["kind"] == "money" and cond(b)["value"]["minor"] == 5_000_000
    b = _with_cond("discount", "gt", 10)
    b["entities"][2]["fields"].append({"id": "discount", "type": "percent", "labels": {"ar": "خ", "en": "Discount"}})
    assert cond(b) == {"field": "discount", "op": "gt", "kind": "percent_bp", "value": 1000}
    assert cond(_with_cond("ghost.amount", "gt", 10))["kind"] == "unknown_unit"
    assert code(build_review, _with_cond("total_amount", "gte", 1.5), tenant_id=T).startswith("ACV-MONEY")
    assert code(build_review, _with_cond("ghost.name", "eq", 1.1), tenant_id=T) == "ACV-BP-004"
    assert cond(_with_cond("status", "is_set", None) if False else _with_cond("ghost.name", "eq", "x"))["kind"] == "value"


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
    o = v["overall"]  # chart of accounts and posting rules were never reviewed: not a plain "approved" (M1)
    assert o["state"] == "approved_signable_only" and o["evidenceOnly"] is True
    assert o["notReviewed"] == ["chart_of_accounts", "posting_rules"] and o["staleRecords"] == 0 and o["quarantined"] == 0
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
    assert code(dec, recs) == "ACV-SO-007"  # a second approval is refused
    assert dec(recs, section="numbering")[: len(recs)] == recs  # old records kept as they were
    rej = dec(recs, decision="changes_requested", note="n")
    assert rej[: len(recs)] == recs
    assert code(dec, rej) == "ACV-SO-007" and code(dec, rej, decision="changes_requested", note="m") == "ACV-SO-007"


def test_later_rejection_beats_earlier_approval():  # M4
    recs = dec(decision="approved")
    recs = dec(recs, decision="changes_requested", note="Rate is wrong", actor=Signer(T, "acc-2", ("accountant",), "human"))
    v = build_review(BP, recs, tenant_id=T)
    assert sec(v, "tax_vat")["signOff"]["state"] == "changes_requested" and v["overall"]["state"] == "changes_requested"


def test_human_only_tenant_bound_role():
    assert code(dec, actor=Signer(T, "bot", ("accountant",), "agent")) == "ACV-SO-002"
    assert code(dec, actor=Signer(T, "svc", ("accountant",), "service")) == "ACV-SO-002"
    assert code(dec, actor=Signer("tenant-b", "acc-1", ("accountant",), "human")) == "ACV-SO-003"
    assert code(dec, actor=Signer(T, "own-1", ("owner",), "human")) == "ACV-SO-004"
    assert code(dec, actor=Signer(T, "own-1", ("owner", "accountant"), "human")) == "ACV-SO-010"  # M5
    assert code(com, actor=Signer(T, "own-1", ("owner", "accountant"), "human")) == "ACV-SO-010"
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


def _good():
    return dec()[0]


def test_foreign_tenant_record_refused_whole():
    g = _good()
    forged = [Decision("tenant-b", g.blueprint_digest, "tax_vat", "x1", "approved", g.decided_at, "")]
    assert code(build_review, BP, forged, tenant_id=T) == "ACV-REC-001"
    for bad in ("nope", None, {"a": 1}, 5):
        assert code(build_review, BP, bad, tenant_id=T) == "ACV-REC-001"


def _mut(g, **kw):
    d = dict(tenant_id=g.tenant_id, blueprint_digest=g.blueprint_digest, section=g.section, user_id=g.user_id,
             decision=g.decision, decided_at=g.decided_at, note=g.note)
    d.update(kw)
    return Decision(**d)


def test_bad_stored_records_are_quarantined_not_fatal():  # M2 and the "bricked view" LOW
    g = _good()
    bad = [_mut(g, note="ok\u202egnp.exe\u0007", decision="approved"),
           _mut(g, decided_at="2026-99-99T99:99:99.000Z"),
           _mut(g, decided_at=5), _mut(g, user_id=None), _mut(g, decision="auto"), _mut(g, blueprint_digest="zz"),
           _mut(g, decision="changes_requested", note=""), _mut(g, section="chart_of_accounts"),  # not signable
           _mut(g, decided_at="2100-01-01T00:00:00.000Z"), object(),
           Comment(T, g.blueprint_digest, "tax_vat", 7, "u1", g.decided_at, "x"),
           Comment(T, g.blueprint_digest, "tax_vat", "c1", "u1", g.decided_at, "a\u202eb"),
           Comment(T, g.blueprint_digest, "tax_vat", "c1", "u1", g.decided_at, "")]
    for b in bad:
        v = build_review(BP, [b, g], tenant_id=T)
        assert v["overall"]["quarantined"] == 1, b
        assert sec(v, "tax_vat")["signOff"]["state"] == "integrity_error"  # R1: never approved next to a bad row
        assert v["overall"]["state"] == "integrity_error"
        assert sec(v, "tax_vat")["signOff"]["decision"]["userId"] == g.user_id == "acc-1"
        assert sec(v, "tax_vat")["signOff"]["decision"]["note"] == "" and sec(v, "tax_vat")["signOff"]["decision"]["decidedAt"] == g.decided_at
        assert all("\u202e" not in json.dumps(c, ensure_ascii=False) for c in sec(v, "tax_vat")["comments"])
    assert sec(build_review(BP, [bad[7], g], tenant_id=T), "chart_of_accounts")["signOff"]["decision"] is None


def test_duplicate_and_out_of_order_stored_records_quarantined():
    g = _good()
    v = build_review(BP, [g, g], tenant_id=T)
    assert v["overall"]["quarantined"] == 1 and sec(v, "tax_vat")["signOff"]["state"] == "integrity_error"
    rej = _mut(g, decision="changes_requested", note="n")
    v = build_review(BP, [rej, g], tenant_id=T)  # approval after a rejection never happened
    assert sec(v, "tax_vat")["signOff"]["state"] == "changes_requested" and v["overall"]["quarantined"] == 1
    c = Comment(T, g.blueprint_digest, "tax_vat", "c000001", "u1", g.decided_at, "hi")
    assert build_review(BP, [c, c], tenant_id=T)["overall"]["quarantined"] == 1
    # writes still work on top of a store holding a bad row
    assert dec([g, g], section="numbering")


def test_writer_never_persists_what_reader_refuses():
    late = dt.datetime(2100, 6, 1, tzinfo=dt.timezone.utc)
    assert code(record_decision, BP, (), tenant_id=T, actor=ACC, section="tax_vat", decision="approved",
                decided_at=late, now=late, note="") == "ACV-SO-001"


# ---- digest, staleness, history -------------------------------------------------------------------------------
def test_digest_ignores_build_state_but_not_content():  # H1
    recs = dec()
    moved = bp()
    moved["meta"]["buildState"] = "owner_approved"
    assert blueprint_digest(moved) == blueprint_digest(BP)
    v = build_review(moved, recs, tenant_id=T)
    assert sec(v, "tax_vat")["signOff"]["state"] == "approved" and v["overall"]["staleRecords"] == 0
    for path in (("meta", "revision"), ("company", "crNumber")):
        c = bp()
        c[path[0]][path[1]] = 99 if path[1] == "revision" else "1010000001"
        assert blueprint_digest(c) != blueprint_digest(BP)


def test_canonical_form_is_documented_and_stable():
    from accountant_view.view import canonical
    assert canonical({"b": "ع", "a": [1, True], "meta": {"buildState": "x", "k": 1}}) == \
        '{"a":[1,true],"b":"ع","meta":{"k":1}}'.encode("utf-8")


def test_open_change_request_survives_a_trivial_edit():  # M6
    recs = dec(decision="changes_requested", note="VAT rate wrong")
    recs = com(recs, text="see note")
    edited = bp()
    edited["company"]["legalName"]["en"] += " "
    v = build_review(edited, recs, tenant_id=T)
    s = sec(v, "tax_vat")["signOff"]
    assert s["state"] == "awaiting" and s["openChangeRequest"]["note"] == "VAT rate wrong"
    assert s["openChangeRequest"]["stale"] is True
    assert v["overall"]["openChangeRequests"] == ["tax_vat"] and v["overall"]["staleRecords"] == 2
    assert [c["text"] for c in v["history"]["comments"]] == ["see note"] and v["history"]["comments"][0]["stale"]
    # a fresh decision on the new version replaces the open request
    recs2 = dec(recs, blueprint=edited, decision="approved")
    assert sec(build_review(edited, recs2, tenant_id=T), "tax_vat")["signOff"]["openChangeRequest"] is None


def test_hostile_blueprints_get_stable_codes():  # LOW
    nan = bp()
    nan["compliance"]["vat"]["defaultRatePercent"] = float("nan")
    sur = bp()
    sur["company"]["legalName"]["en"] = "a\ud800b"
    deep = bp()
    deep["approvals"][0]["conditions"][0]["value"] = cur = []
    for _ in range(5000):
        nxt = []
        cur.append(nxt)
        cur = nxt
    for b in (nan, sur, deep):
        assert code(build_review, b, tenant_id=T) in ("ACV-BP-002", "ACV-BP-004")


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
    assert com(r, section="chart_of_accounts")
    other = add_comment(BP, (), tenant_id="tenant-b", actor=Signer("tenant-b", "a9", ("accountant",), "human"),
                        section="tax_vat", text="x", created_at=NOW, now=NOW)
    assert other[0].comment_id == "c000001"  # ids are per tenant  # comments are allowed on sections that cannot be signed off


def test_comment_rules():
    assert code(com, actor=Signer(T, "bot", ("accountant",), "agent")) == "ACV-SO-002"
    assert code(com, actor=Signer(T, "o1", ("owner",), "human")) == "ACV-SO-004"
    assert code(com, text="  ​ ") == "ACV-SO-009"
    assert code(com, text=5) == "ACV-SO-009"
    assert code(com, section="x") == "ACV-SO-005"


def test_untrusted_text_is_cleaned_and_flagged():
    r = com(text="a‮b\u0000c​d" + "x" * 1500)
    assert r[0].text.startswith("abcd")
    assert code(com, text="x" * 2001) == "ACV-SO-011" and code(dec, note="x" * 2001) == "ACV-SO-011"  # R6
    assert com(text="x" * 1999 + " ")[0].text == "x" * 1999  # trailing space stripped, no boundary bug
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


# ---- second review (R1 to R7) -----------------------------------------------------------------------------------
def _rejection_after_approval():
    appr = dec()[0]
    rej = _mut(appr, decision="changes_requested", note="VAT rate wrong", user_id="acc-2")
    return appr, rej


@pytest.mark.parametrize("corrupt", [dict(note="wrong\u200b"), dict(decided_at="2026-02-30T10:00:00.000Z"),
                                     dict(note="wrong\u202e"), dict(user_id="a b")])
def test_corrupted_rejection_never_leaves_an_approval_standing(corrupt):  # R1
    appr, rej = _rejection_after_approval()
    v = build_review(BP, [appr, _mut(rej, **corrupt)], tenant_id=T)
    assert v["overall"]["quarantined"] == 1
    assert v["overall"]["state"] == "integrity_error" and not v["overall"]["state"].startswith("approved")
    assert sec(v, "tax_vat")["signOff"]["state"] == "integrity_error"


def test_record_without_tenant_refuses_the_read():  # R1
    appr, rej = _rejection_after_approval()
    for t in (None, 5, ""):
        assert code(build_review, BP, [appr, _mut(rej, tenant_id=t)], tenant_id=T) == "ACV-REC-001"


def test_digest_survives_a_real_state_transition():  # R2
    t = bp()
    t["meta"]["buildState"] = "owner_approved"
    t["meta"]["updatedAt"] = "2026-11-21T09:30:00Z"
    assert blueprint_digest(t) == blueprint_digest(BP)
    recs = dec()
    assert sec(build_review(t, recs, tenant_id=T), "tax_vat")["signOff"]["state"] == "approved"
    from accountant_view.view import canonical
    assert b"updatedAt" not in canonical(BP) and b"buildState" not in canonical(BP) and b"createdAt" in canonical(BP)


def test_open_change_request_does_not_depend_on_store_order():  # R3
    v1, v2, v3 = bp(), bp(), bp()
    v2["company"]["legalName"]["en"] += " 2"
    v3["company"]["legalName"]["en"] += " 3"
    t1, t2 = NOW, NOW + dt.timedelta(minutes=2)
    r1 = record_decision(v1, (), tenant_id=T, actor=ACC, section="tax_vat", decision="approved", decided_at=t1, now=t1, note="")
    r2 = record_decision(v2, (), tenant_id=T, actor=ACC, section="tax_vat", decision="changes_requested", decided_at=t2, now=t2, note="fix it")
    for order in ([r1[0], r2[0]], [r2[0], r1[0]]):
        v = build_review(v3, order, tenant_id=T)
        assert sec(v, "tax_vat")["signOff"]["openChangeRequest"]["note"] == "fix it"


@pytest.mark.parametrize("role", ["Owner", "owner ", "ADMIN", "administrator", "Super_Admin"])
def test_owner_equivalent_roles_refused_case_insensitively(role):  # R4
    assert code(dec, actor=Signer(T, "x1", ("accountant", role), "human")) == "ACV-SO-010"
    assert code(dec, actor=Signer(T, "x1", ("accountant", 5), "human")) == "ACV-SO-004"


def test_comment_id_never_reuses_a_quarantined_id():  # R5
    r = com()
    broken = Comment(T, r[0].blueprint_digest, "tax_vat", "c000001", "u1", r[0].created_at, "a\u200bb")
    nxt = com([broken])
    assert nxt[-1].comment_id == "c000002"


def test_subclass_records_refused():  # R7
    class Sneaky(Decision):  # could override any attribute or method after the shape check
        pass
    g = _good()
    s_ = Sneaky(g.tenant_id, g.blueprint_digest, "numbering", "u1", "approved", g.decided_at, "")
    v = build_review(BP, [s_], tenant_id=T)
    assert v["overall"]["quarantined"] == 1 and sec(v, "numbering")["signOff"]["decision"] is None
