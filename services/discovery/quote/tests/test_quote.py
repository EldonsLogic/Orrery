import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quote import (QuoteError, default_price_book, digest, generate_quote, load_price_book, money, quote_state,
                   render, validate_price_book, verify_quote)
from quote.money import mul_bp, percent_text

ROOT = Path(__file__).resolve().parents[4]
NOW = datetime(2026, 11, 20, 9, 30, tzinfo=timezone.utc)
BP = json.loads((ROOT / "contracts" / "examples" / "blueprint-trading-minimal.json").read_text(encoding="utf-8"))


def blueprint(country="SA", bid="t-1", rev=3):
    return {"meta": {"id": bid, "revision": rev}, "company": {"country": country}}


def req(kind, ref, status, comp=None, ver="1.0.0"):
    r = {"id": f"{kind}:{ref}", "kind": kind, "ref": ref, "status": status, "match": None}
    if comp:
        r["match"] = {"component": comp, "version": ver}
    return r


def gap(reqs=(), bid="t-1", rev=3, hints=None, env="sandbox", malformed=0, rejected=0):
    reqs = list(reqs)
    reqs_out = []
    requests = []
    for r in reqs:
        reqs_out.append(r)
        if r["status"] == "uncovered" and r["kind"] != "component":
            requests.append({"request_key": f"key-{r['id']}", "requirement_id": r["id"], "kind": r["kind"], "ref": r["ref"],
                             "kind_hint": (hints or {}).get(r["id"], "rigid" if r["kind"] == "compliance" else "configurable")})
    c = {k: sum(1 for r in reqs if r["status"] == k) for k in ("covered", "partial", "uncovered")}
    return {"schema": "1", "environment": env, "blueprint": {"id": bid, "revision": rev},
            "summary": {"total": len(reqs), **c, "malformed_blueprint_items": malformed, "library_entries_rejected": rejected}, "requirements": reqs_out, "component_requests": requests}


def pb(**over):
    p = copy.deepcopy(default_price_book())
    p.update(over)
    return p


def q(reqs=(), country="SA", book=None, **kw):
    return generate_quote(blueprint(country), gap(reqs), book or default_price_book(), now=NOW, **kw)


# ---- shape and draft status -------------------------------------------------------------------------------

def test_empty_gap_list_is_base_fee_only():
    r = q()
    assert [x["id"] for x in r["lines"]["recurring"]] == ["base_platform"]
    assert r["lines"]["one_off"] == [] and r["unpriced"] == [] and r["complete"] is True
    assert r["totals"]["recurring"]["subtotal"]["minor"] == 200000
    assert r["totals"]["recurring"]["tax"]["amount"]["minor"] == 30000          # 15% placeholder
    assert r["totals"]["one_off"]["total"]["minor"] == 0


def test_always_a_draft_never_binding():
    r = q()
    assert r["status"] == "draft" and r["binding"] is False and r["requires_human_approval"] is True
    keys = [w["key"] for w in r["warnings"]]
    assert "quote.warning.draft_not_binding" in keys and "quote.warning.placeholder_prices" in keys


def test_covered_partial_and_uncovered_lines():
    r = q([req("component", "sales.core", "covered", "sales.core", "1.2.0"),
           req("entity", "customer", "covered", "sales.core", "1.2.0"),     # same component: one module line
           req("workflow", "approve", "partial", "wf.basic", "0.3.0"),
           req("compliance", "zatca", "uncovered"),
           req("report", "aging", "uncovered")])
    rec = {x["id"]: x for x in r["lines"]["recurring"]}
    assert set(rec) == {"base_platform", "module:sales.core", "module:wf.basic"}
    assert rec["module:sales.core"]["requirements"] == ["component:sales.core", "entity:customer"]
    one = {x["id"]: x["total"]["minor"] for x in r["lines"]["one_off"]}
    assert one["configuration:wf.basic"] == 150000
    assert sorted(one.values()) == [150000, 800000, 2000000]                  # configuration, configurable, rigid build
    assert r["totals"]["recurring"]["subtotal"]["minor"] == 200000 + 2 * 30000
    assert r["totals"]["one_off"]["subtotal"]["minor"] == 150000 + 800000 + 2000000


def test_per_component_price_overrides_default():
    book = pb()
    book["currencies"]["SAR"]["components"]["sales.core"] = 55555
    r = q([req("component", "sales.core", "covered", "sales.core")], book=book)
    assert r["lines"]["recurring"][1]["unit"]["minor"] == 55555


def test_uncovered_component_binding_is_unpriced_not_invented():
    r = q([req("component", "ghost.thing", "uncovered")])
    assert r["complete"] is False and len(r["unpriced"]) == 1
    assert "quote.warning.unpriced_items" in [w["key"] for w in r["warnings"]]
    assert r["lines"]["one_off"] == []


def test_tax_and_subtotals_are_separate_per_section():
    r = q([req("entity", "e", "uncovered")])
    t = r["totals"]
    assert t["one_off"]["subtotal"]["minor"] == 800000
    assert t["one_off"]["tax"]["amount"]["minor"] == 120000
    assert t["one_off"]["total"]["minor"] == 920000
    assert t["recurring"]["total"]["minor"] == 230000
    assert all(x["total"]["minor"] >= 0 for x in r["lines"]["recurring"] + r["lines"]["one_off"])


def test_allowances_are_info_not_charged():
    r = q()
    assert r["allowances"]["ai_actions_monthly"]["quantity"] == 1000
    assert r["allowances"]["overage_pack"]["price"]["text"] == "400.00"
    assert r["totals"]["recurring"]["subtotal"]["minor"] == 200000


# ---- money, rounding, currencies --------------------------------------------------------------------------

@pytest.mark.parametrize("minor,bp,want", [(1, 5000, 1), (3, 5000, 2), (1, 4999, 0), (333, 1500, 50), (10, 1500, 2), (30, 1500, 5),
                                           (0, 1500, 0), (7, 10000, 7), (5, 1000, 1), (4, 1000, 0)])
def test_half_up_rounding(minor, bp, want):
    assert mul_bp(minor, bp) == want   # 333*0.15 = 49.95 -> 50; 10*0.15 = 1.5 -> 2 (half up, not banker's)


def test_rounding_refuses_bad_input():
    for a, b in [(-1, 100), (1, -1), (1, 10001), (1.5, 100), (True, 100), (1, True)]:
        with pytest.raises(QuoteError):
            mul_bp(a, b)


def test_tax_half_up_on_real_quote():
    book = pb()
    book["currencies"]["SAR"]["base_platform_monthly"] = 10      # 10 * 15% = 1.5 minor -> 2
    assert q(book=book)["totals"]["recurring"]["tax"]["amount"]["minor"] == 2


def test_each_market_currency_and_digits():
    for cc, cur, tax in (("SA", "SAR", 30000), ("AE", "AED", 9750), ("EG", "EGP", 280000), ("QA", "QAR", 0)):
        r = q(country=cc)
        assert r["currency"] == cur and r["totals"]["recurring"]["subtotal"]["exponent"] == 2
        assert r["totals"]["recurring"]["tax"]["amount"]["minor"] == tax


def test_three_decimal_currency():
    book = pb()
    book["markets"]["KW"] = {"currency": "KWD", "tax": {"rate_bp": 500}}
    book["currencies"]["KWD"] = {**copy.deepcopy(book["currencies"]["SAR"]), "base_platform_monthly": 12345}
    r = q(country="KW", book=book)
    t = r["totals"]["recurring"]
    assert t["subtotal"] == {"minor": 12345, "currency": "KWD", "exponent": 3, "text": "12.345"}
    assert t["tax"]["amount"]["minor"] == 617        # 617.25 -> 617
    assert money(5, "KWD")["text"] == "0.005" and money(-1500, "KWD")["text"] == "-1.500"


def test_zero_decimal_currency():
    book = pb()
    book["markets"]["JP"] = {"currency": "JPY", "tax": {"rate_bp": 1000}}
    book["currencies"]["JPY"] = {**copy.deepcopy(book["currencies"]["SAR"]), "base_platform_monthly": 12345}
    r = q(country="JP", book=book)
    assert r["totals"]["recurring"]["subtotal"]["text"] == "12345"
    assert r["totals"]["recurring"]["tax"]["amount"]["minor"] == 1235   # 1234.5 -> 1235 half up
    assert money(7, "JPY")["text"] == "7"


def test_money_refuses_floats_and_unknown_currency():
    for bad in (1.5, True, "5", None):
        with pytest.raises(QuoteError):
            money(bad, "SAR")
    with pytest.raises(QuoteError):
        money(1, "XXX")


def test_percent_text():
    assert [percent_text(x) for x in (0, 1500, 1450, 125, 10000)] == ["0", "15", "14.5", "1.25", "100"]


def test_discount_line_rounds_half_up_and_precedes_tax():
    r = q([req("entity", "e", "uncovered")], discount_bp=2500)   # 800000 * 25% = 200000
    one = r["lines"]["one_off"]
    assert one[-1]["id"] == "discount" and one[-1]["total"]["minor"] == -200000
    assert r["totals"]["one_off"]["subtotal"]["minor"] == 600000
    assert r["totals"]["one_off"]["tax"]["amount"]["minor"] == 90000
    book = pb()
    book["currencies"]["SAR"]["build_one_off"]["configurable"] = 5
    r = q([req("entity", "e", "uncovered")], book=book, discount_bp=5000)  # 2.5 -> 3 off, leaves 2
    assert r["totals"]["one_off"]["subtotal"]["minor"] == 2


def test_discount_on_nothing_adds_no_line():
    assert q(discount_bp=5000)["lines"]["one_off"] == []


@pytest.mark.parametrize("bad", [-1, 10001, 1.5, True, "10"])
def test_bad_discount(bad):
    with pytest.raises(QuoteError) as e:
        q(discount_bp=bad)
    assert e.value.code == "QTE-ARG-001"


def test_huge_prices_and_overflow_refused():
    book = pb()
    book["currencies"]["SAR"]["base_platform_monthly"] = 10 ** 12
    book["currencies"]["SAR"]["module_default_monthly"] = 10 ** 12
    reqs = [req("component", f"c{i}", "covered", f"c{i}") for i in range(1100)]
    with pytest.raises(QuoteError) as e:
        q(reqs, book=book)
    assert e.value.code == "QTE-RANGE-001"          # subtotal 1.1e15 refused


def test_many_lines_refused_and_large_but_valid_quote_ok():
    with pytest.raises(QuoteError) as e:
        q([req("component", f"c{i}", "covered", f"c{i}") for i in range(2100)])
    assert e.value.code == "QTE-RANGE-002"
    r = q([req("component", f"c{i}", "covered", f"c{i}") for i in range(1500)])
    assert r["totals"]["recurring"]["subtotal"]["minor"] == 200000 + 1500 * 30000


def test_huge_but_valid_allowance_counts():
    book = pb()
    book["currencies"]["SAR"]["allowances"]["ai_actions_monthly"] = 10 ** 9
    assert q(book=book)["allowances"]["ai_actions_monthly"]["quantity"] == 10 ** 9
    book["currencies"]["SAR"]["allowances"]["ai_actions_monthly"] = 10 ** 9 + 1
    with pytest.raises(QuoteError):
        q(book=book)


# ---- bilingual labels -------------------------------------------------------------------------------------

def test_arabic_and_english_labels_everywhere():
    r = q([req("component", "sales.core", "covered", "sales.core", "1.0.0"), req("compliance", "zatca", "uncovered")])
    base = r["lines"]["recurring"][0]["labels"]
    assert base["ar"] == "رسوم المنصة الأساسية (مستخدمون غير محدودين)" and base["en"].startswith("Base platform fee")
    mod = r["lines"]["recurring"][1]["labels"]
    assert "sales.core" in mod["ar"] and "الوحدة" in mod["ar"] and "Module sales.core version 1.0.0" == mod["en"]
    build = r["lines"]["one_off"][0]["labels"]
    assert "zatca" in build["ar"] and "للامتثال" in build["ar"] and "compliance-bound" in build["en"]
    assert r["totals"]["recurring"]["tax"]["labels"]["ar"] == "ضريبة القيمة المضافة 15% على الاشتراك الشهري"
    assert r["labels"]["title"]["ar"] == "عرض سعر (مسودة)"
    for w in r["warnings"]:
        assert w["labels"]["ar"] != w["labels"]["en"] and not w["labels"]["ar"].startswith("quote.")


def test_label_files_have_the_same_keys_and_placeholders():
    import re
    d = json.loads((ROOT / "services" / "discovery" / "quote" / "labels.json").read_text(encoding="utf-8"))
    assert set(d["ar"]) == set(d["en"])
    for k in d["en"]:
        assert re.findall(r"\{[a-z_]+\}", d["en"][k]) == re.findall(r"\{[a-z_]+\}", d["ar"][k]), k


def test_render_is_single_pass_and_never_raises():
    assert render("quote.line.module", {"component": "{version}", "version": "2"}) == "Module {version} version 2"
    assert render("no.such.key") == "no.such.key" and render("quote.title", locale="fr") == "quote.title"


def test_hostile_blueprint_text_is_cleaned_in_labels():
    r = generate_quote(blueprint(), gap([{**req("entity", "x", "uncovered"), "ref": "a‮b\x00c\n" + "z" * 500}]),
                       default_price_book(), now=NOW)
    ref = r["lines"]["one_off"][0]["params"]["ref"]
    assert "‮" not in ref and "\x00" not in ref and "\n" not in ref and len(ref) <= 120


# ---- price book validation (hostile input) ----------------------------------------------------------------

def mutate(fn):
    book = copy.deepcopy(default_price_book())
    fn(book)
    return book


HOSTILE = {
    "float price": lambda b: b["currencies"]["SAR"].update(base_platform_monthly=1.5),
    "bool price": lambda b: b["currencies"]["SAR"].update(base_platform_monthly=True),
    "string price": lambda b: b["currencies"]["SAR"].update(base_platform_monthly="100"),
    "negative price": lambda b: b["currencies"]["SAR"].update(module_default_monthly=-1),
    "huge price": lambda b: b["currencies"]["SAR"].update(configuration_one_off=10 ** 12 + 1),
    "negative component": lambda b: b["currencies"]["SAR"]["components"].update({"a.b": -5}),
    "odd component id": lambda b: b["currencies"]["SAR"]["components"].update({"A B;<script>": 5}),
    "unknown key": lambda b: b.update(extra=1),
    "unknown currency key": lambda b: b["currencies"]["SAR"].update(secret_discount=1),
    "missing key": lambda b: b["currencies"]["SAR"].pop("build_one_off"),
    "bad rate": lambda b: b["markets"]["SA"]["tax"].update(rate_bp=10001),
    "float rate": lambda b: b["markets"]["SA"]["tax"].update(rate_bp=1500.0),
    "market without currency table": lambda b: b["markets"].update(XX={"currency": "USD", "tax": {"rate_bp": 0}}),
    "unknown currency": lambda b: (b["markets"]["SA"].update(currency="ZZZ"), b["currencies"].update(ZZZ=b["currencies"]["SAR"])),
    "bad market key": lambda b: b["markets"].update({"sa": b["markets"]["SA"]}),
    "validity zero": lambda b: b.update(validity_days=0),
    "validity huge": lambda b: b.update(validity_days=3650),
    "bad status": lambda b: b.update(status="final"),
    "bad schema": lambda b: b.update(schema="price-book/9"),
    "bad id": lambda b: b.update(id="../../x"),
    "zero pack": lambda b: b["currencies"]["SAR"]["allowances"].update(overage_pack_size=0),
    "no markets": lambda b: b.update(markets={}),
    "not a dict": lambda b: None,
}


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_hostile_price_book_refused(name):
    book = mutate(HOSTILE[name])
    if name == "not a dict":
        book = ["x"]
    with pytest.raises(QuoteError) as e:
        q(book=book)
    assert e.value.code == "QTE-PB-001"


def test_price_book_file_loader_refuses_duplicates_nan_and_junk(tmp_path):
    good = (ROOT / "services/discovery/quote/price_book.placeholder.json").read_text(encoding="utf-8")
    for name, text in {"dup": good.replace('"status": "placeholder",', '"status": "placeholder", "status": "approved",'),
                       "nan": good.replace('"validity_days": 30', '"validity_days": NaN'),
                       "junk": "{not json"}.items():
        p = tmp_path / f"{name}.json"
        p.write_text(text, encoding="utf-8")
        with pytest.raises(QuoteError):
            load_price_book(p)
    with pytest.raises(QuoteError):
        load_price_book(tmp_path / "missing.json")


def test_shipped_price_book_is_valid_and_marked_placeholder():
    book = default_price_book()
    assert book["status"] == "placeholder" and book["id"].startswith("placeholder")
    assert validate_price_book(book) is book


def test_price_book_id_and_digest_recorded_and_pinnable():
    r = q()
    assert r["price_book"] == {"id": "placeholder-v0", "status": "placeholder", "digest": digest(default_price_book())}
    q(expected_price_book_digest=r["price_book"]["digest"])
    changed = pb()
    changed["currencies"]["SAR"]["base_platform_monthly"] += 1
    with pytest.raises(QuoteError) as e:
        q(book=changed, expected_price_book_digest=r["price_book"]["digest"])
    assert e.value.code == "QTE-PB-002"


def test_approved_book_drops_placeholder_warning():
    r = q(book=pb(status="approved"))
    assert "quote.warning.placeholder_prices" not in [w["key"] for w in r["warnings"]]


# ---- input consistency -----------------------------------------------------------------------------------

def test_stale_gap_report_for_other_revision_refused():
    with pytest.raises(QuoteError) as e:
        generate_quote(blueprint(rev=4), gap(rev=3), default_price_book(), now=NOW)
    assert e.value.code == "QTE-GAP-002"
    with pytest.raises(QuoteError):
        generate_quote(blueprint(bid="other"), gap(), default_price_book(), now=NOW)


def test_tampered_gap_summary_refused():
    g = gap([req("entity", "e", "uncovered")])
    g["summary"]["uncovered"] = 0
    with pytest.raises(QuoteError) as e:
        generate_quote(blueprint(), g, default_price_book(), now=NOW)
    assert e.value.code == "QTE-GAP-003"


@pytest.mark.parametrize("mut", [lambda g: g.update(schema="2"), lambda g: g.pop("requirements"),
                                 lambda g: g["requirements"].append("x"), lambda g: g.update(summary=None)])
def test_malformed_gap_refused(mut):
    g = gap([req("entity", "e", "uncovered")])
    mut(g)
    with pytest.raises(QuoteError):
        generate_quote(blueprint(), g, default_price_book(), now=NOW)


def test_covered_without_match_refused():
    with pytest.raises(QuoteError):
        q([req("entity", "e", "covered")])


def test_unknown_country_and_bad_blueprint_refused():
    with pytest.raises(QuoteError) as e:
        q(country="US")
    assert e.value.code == "QTE-BP-002"
    for bad in (None, {}, {"meta": {}, "company": None}):
        with pytest.raises(QuoteError):
            generate_quote(bad, gap(), default_price_book(), now=NOW)


def test_works_with_real_gap_analysis_output():
    import gap_analysis
    lib = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "services/blueprint/fixtures/registry").glob("*.json"))]
    g = gap_analysis.analyse(BP, lib)
    r = generate_quote(BP, g, default_price_book(), now=NOW)
    n_requests = len(g["component_requests"])
    assert len([x for x in r["lines"]["one_off"] if x["kind"].startswith("build_")]) == n_requests
    assert verify_quote(r)
    json.dumps(r)   # serialisable


# ---- clock, validity, digest ------------------------------------------------------------------------------

def test_clock_must_be_aware_and_is_normalised():
    for bad in (datetime(2026, 1, 1), "2026-01-01", None):
        with pytest.raises(QuoteError) as e:
            generate_quote(blueprint(), gap(), default_price_book(), now=bad)
        assert e.value.code == "QTE-CLOCK-001"
    riyadh = datetime(2026, 11, 20, 12, 30, 45, 999, tzinfo=timezone(timedelta(hours=3)))
    r = generate_quote(blueprint(), gap(), default_price_book(), now=riyadh)
    assert r["issued_at"] == "2026-11-20T09:30:45Z" and r["valid_until"] == "2026-12-20T09:30:45Z"


def test_validity_can_shorten_not_extend():
    assert q(validity_days=7)["validity_days"] == 7
    assert q(validity_days=90)["validity_days"] == 30
    for bad in (0, 91, 1.5, True):
        with pytest.raises(QuoteError):
            q(validity_days=bad)


def test_expiry_boundaries():
    r = q(validity_days=10)
    assert quote_state(r, NOW) == "valid"
    assert quote_state(r, NOW + timedelta(days=10) - timedelta(seconds=1)) == "valid"
    assert quote_state(r, NOW + timedelta(days=10)) == "expired"
    assert quote_state(r, NOW + timedelta(days=400)) == "expired"
    assert quote_state(r, NOW - timedelta(seconds=1)) == "not_yet_valid"
    with pytest.raises(QuoteError):
        quote_state(r, datetime(2027, 1, 1))


def test_same_inputs_same_quote_and_id_from_digest():
    a, b = q(), q()
    assert a == b and a["quote_id"] == "QTE-" + a["digest"][:16].upper()
    assert q(country="AE")["digest"] != a["digest"]
    assert generate_quote(blueprint(), gap(), default_price_book(), now=NOW + timedelta(seconds=1))["digest"] != a["digest"]


def test_input_order_does_not_change_digest():
    reqs = [req("entity", "a", "uncovered"), req("entity", "b", "covered", "m.b"), req("entity", "c", "covered", "m.a")]
    a = q(reqs)
    b = q(list(reversed(reqs)))
    assert [x["id"] for x in a["lines"]["recurring"]] == [x["id"] for x in b["lines"]["recurring"]]


def test_tamper_evident():
    r = q([req("entity", "e", "uncovered")])
    assert verify_quote(r)
    for edit in (lambda x: x["lines"]["one_off"][0]["total"].update(minor=1),
                 lambda x: x.update(valid_until="2099-01-01T00:00:00Z"),
                 lambda x: x.update(binding=True),
                 lambda x: x["price_book"].update(status="approved"),
                 lambda x: x["totals"]["recurring"]["total"].update(minor=0),
                 lambda x: x.update(quote_id="QTE-0000000000000000"),
                 lambda x: x.pop("digest")):
        t = copy.deepcopy(r)
        edit(t)
        assert not verify_quote(t)
        with pytest.raises(QuoteError) as e:
            quote_state(t, NOW)
        assert e.value.code == "QTE-TAMPER-001"
    assert verify_quote("x") is False and verify_quote({"digest": 1}) is False


def test_does_not_mutate_inputs():
    b, g, p = blueprint(), gap([req("entity", "e", "uncovered")]), default_price_book()
    snap = copy.deepcopy((b, g, p))
    generate_quote(b, g, p, now=NOW)
    assert (b, g, p) == snap


def test_no_model_or_network_imports():
    src = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "services/discovery/quote").glob("*.py"))
    for banned in ("anthropic", "openai", "import requests", "urllib", "socket", "import random", "time.time", "datetime.now", "utcnow", "float("):
        assert banned not in src, banned


# ---- PR #215 review regressions ---------------------------------------------------------------------------

def _g_with_requests(reqs, extra):
    g = gap(reqs)
    g["component_requests"] += extra
    return g


def _gen(g, **kw):
    return generate_quote(blueprint(), g, default_price_book(), now=NOW, **kw)


def _rq(rid, key, kind="entity", ref="x", hint="rigid"):
    return {"request_key": key, "requirement_id": rid, "kind": kind, "ref": ref, "kind_hint": hint}


def test_m1_request_for_covered_unknown_or_duplicate_requirement_adds_no_charge():
    covered = [req("entity", "x", "covered", "m.x")]
    for g in (_g_with_requests(covered, [_rq("entity:x", "k1")]),                      # covered requirement
              _g_with_requests(covered, [_rq("entity:ghost", "k1")]),                  # unknown requirement
              _g_with_requests([req("entity", "y", "uncovered")], [_rq("entity:y", "k2")]),   # second request, same requirement
              _g_with_requests([req("component", "c", "uncovered")], [_rq("component:c", "k1")])):  # component kind: no requests
        with pytest.raises(QuoteError) as e:
            _gen(g)
        assert e.value.code == "QTE-GAP-003"


def test_m1_uncovered_without_request_is_unpriced():
    g = gap([req("entity", "y", "uncovered")])
    g["component_requests"] = []
    r = _gen(g)
    assert r["lines"]["one_off"] == [] and len(r["unpriced"]) == 1 and r["complete"] is False


def test_m3_dropped_input_makes_quote_incomplete():
    for kw, reason in (({"malformed": 7}, "malformed_blueprint_items"), ({"rejected": 2}, "library_entries_rejected")):
        r = _gen(gap(**kw))
        assert r["complete"] is False and reason in r["incomplete_reasons"]
        assert "quote.warning.malformed_inputs" in [w["key"] for w in r["warnings"]]
    assert _gen(gap())["complete"] is True
    g = gap()
    g["summary"]["malformed_blueprint_items"] = -1
    with pytest.raises(QuoteError):
        _gen(g)


def test_m2_content_digest_binding_and_strict_revision():
    b = blueprint()
    g = gap()
    g["blueprint"]["digest"] = digest(b)
    r = generate_quote(b, g, default_price_book(), now=NOW)
    assert r["inputs"]["gap_bound_by"] == "content_digest"
    assert "quote.warning.gap_not_content_bound" not in [w["key"] for w in r["warnings"]]
    b2 = {**b, "company": {"country": "SA", "x": 1}}
    with pytest.raises(QuoteError) as e:
        generate_quote(b2, g, default_price_book(), now=NOW)
    assert e.value.code == "QTE-GAP-002"
    assert _gen(gap())["inputs"]["gap_bound_by"] == "id_and_revision"
    assert "quote.warning.gap_not_content_bound" in [w["key"] for w in _gen(gap())["warnings"]]
    for brev, grev in ((1, True), (True, 1), (1.0, 1), (1, 1.0)):
        with pytest.raises(QuoteError):
            generate_quote({"meta": {"id": "t-1", "revision": brev}, "company": {"country": "SA"}}, gap(rev=grev), default_price_book(), now=NOW)


def test_m4_environment_and_production_eligibility():
    assert _gen(gap())["production_eligible"] is False
    assert "quote.warning.not_production_eligible" in [w["key"] for w in _gen(gap())["warnings"]]
    ok = req("entity", "e", "covered", "m.e")
    ok["match"]["production_eligible"] = True
    r = _gen(gap([ok], env="production"))
    assert r["production_eligible"] is True and "quote.warning.not_production_eligible" not in [w["key"] for w in r["warnings"]]
    bad = req("entity", "f", "covered", "m.f")           # production run but a match not flagged eligible
    assert _gen(gap([ok, bad], env="production"))["production_eligible"] is False


def test_low_price_book_unhashable_values_coded():
    for fn in (lambda b: b["markets"]["SA"].update(currency=["SAR"]), lambda b: b.update(status=["placeholder"]),
               lambda b: b.update(currencies=[]), lambda b: b["markets"].update(SA=[1])):
        with pytest.raises(QuoteError) as e:
            q(book=mutate(fn))
        assert e.value.code == "QTE-PB-001"


def test_low_non_json_content_coded():
    for bad in (float("nan"), {1, 2}, {"a": {1: "x"}}):
        b = {"meta": {"id": "t-1", "revision": 3}, "company": {"country": "SA"}, "x": bad}
        with pytest.raises(QuoteError) as e:
            generate_quote(b, gap(), default_price_book(), now=NOW)
        assert e.value.code == "QTE-JSON-001"
    assert digest({"1": "a"}) != digest({"1": "b"})
    with pytest.raises(QuoteError):
        digest({1: "a"})
    deep = cur = {}
    for _ in range(5000):
        cur["a"] = {}
        cur = cur["a"]
    assert verify_quote({"digest": "x", "deep": deep}) is False


def test_low_semver_ordering_of_module_version():
    r = q([req("entity", "a", "covered", "m.a", "9.0.0"), req("entity", "b", "covered", "m.a", "10.0.0"),
           req("entity", "c", "covered", "m.a", "10.0.0-rc.1")])
    assert r["lines"]["recurring"][1]["params"]["version"] == "10.0.0"
    with pytest.raises(QuoteError):
        q([req("entity", "a", "covered", "m.a", "banana")])


def test_low_unsafe_ids_refused_and_line_ids_unique():
    for r in (req("entity", "x", "covered", "m.x‮\x00x"), {**req("entity", "x", "covered", "m.x"), "id": "ent ity\n"}):
        with pytest.raises(QuoteError):
            q([r])
    g = gap([req("entity", "a", "uncovered"), req("entity", "b", "uncovered")])
    for x in g["component_requests"]:
        x["request_key"] = "k" * 40 + x["ref"]      # long keys differing late: no truncation collision
    ids = [x["id"] for x in _gen(g)["lines"]["one_off"]]
    assert len(ids) == len(set(ids)) == 2


def test_low_market_currency_mismatch_needs_explicit_override():
    book = mutate(lambda b: b["markets"]["SA"].update(currency="AED"))
    with pytest.raises(QuoteError) as e:
        q(book=book)
    assert e.value.code == "QTE-PB-001"
    book["markets"]["SA"]["currency_override"] = True
    assert q(book=book)["currency"] == "AED"
    book["markets"]["SA"]["currency_override"] = "yes"
    with pytest.raises(QuoteError):
        q(book=book)


def test_low_qatar_zero_rate_label_says_no_vat_and_refs_keep_spaces():
    r = q(country="QA")
    assert "No VAT" in r["totals"]["recurring"]["tax"]["labels"]["en"]
    r = q([{**req("entity", "x", "uncovered"), "ref": "Sales order"}])
    assert r["lines"]["one_off"][0]["params"]["ref"] == "Sales order"


def test_input_order_digest_with_sorted_requests():
    reqs = [req("entity", "a", "uncovered"), req("entity", "b", "covered", "m.b")]
    assert q(reqs)["digest"] == q(reqs)["digest"]
