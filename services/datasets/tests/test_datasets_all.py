"""DAT-002 dataset tests: determinism, consistency, identifier rules, bilingual completeness, edge cases, safety."""
import hashlib
import json
import re
import subprocess
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from services.datasets import DEFAULT_SEED, GENERATOR_VERSION
from services.datasets.generator import BIDI_CHARS, build_market, generate
from services.datasets.loader import DATA_DIR, load_all, load_manifest, load_market
from services.datasets.money import compute_totals
from services.datasets.names import MARKETS

MARKET_CODES = sorted(MARKETS)
D = Decimal


@pytest.fixture(scope="module")
def data():
    return load_all()


@pytest.fixture(scope="module", params=MARKET_CODES)
def mk(request, data):
    return data[request.param]


def q(x):
    return D(x).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def all_text():
    for p in sorted(DATA_DIR.glob("*.json")):
        yield p.name, p.read_text(encoding="utf-8")


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from strings(k)
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


# ---------- determinism ----------
def test_generate_twice_identical_bytes():
    assert generate(DEFAULT_SEED) == generate(DEFAULT_SEED)


def test_committed_files_equal_fresh_generation():
    fresh = generate(DEFAULT_SEED)
    assert sorted(fresh) == sorted(p.name for p in DATA_DIR.glob("*.json"))
    for name, raw in fresh.items():
        assert (DATA_DIR / name).read_bytes() == raw, name


def test_manifest_hashes_and_sizes_match_files():
    man = load_manifest()
    for e in man["files"]:
        raw = (DATA_DIR / e["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == e["sha256"]
        assert len(raw) == e["bytes"]
    assert man["total_bytes"] == sum(e["bytes"] for e in man["files"])


def test_manifest_records_seed_and_version_and_counts():
    man = load_manifest()
    assert man["seed"] == DEFAULT_SEED and man["generator_version"] == GENERATOR_VERSION
    assert man["classification"] == "C1" and man["synthetic"] is True
    for e in man["files"]:
        doc = json.loads((DATA_DIR / e["path"]).read_text(encoding="utf-8"))
        assert e["counts"]["customers"] == len(doc["customers"]) and e["counts"]["sales_orders"] == len(doc["sales_orders"])
        assert doc["meta"]["seed"] == man["seed"]


def test_different_seed_changes_output_but_not_structure():
    other = generate(DEFAULT_SEED + 1)
    mine = generate(DEFAULT_SEED)
    assert other["ksa.json"] != mine["ksa.json"]
    a, b = json.loads(other["ksa.json"]), json.loads(mine["ksa.json"])
    assert len(a["sales_orders"]) == len(b["sales_orders"]) and a["customers"][0]["vat_number"] != b["customers"][0]["vat_number"]


def test_files_are_stable_json_sorted_keys_trailing_newline():
    for name, text in all_text():
        assert text.endswith("\n")
        obj = json.loads(text)
        again = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        assert BIDI_CHARS.sub(lambda m: "\\u%04x" % ord(m.group(0)), again) == text, name


def test_loader_refuses_tampered_file(tmp_path):
    for p in DATA_DIR.glob("*.json"):
        (tmp_path / p.name).write_bytes(p.read_bytes())
    ksa = tmp_path / "ksa.json"
    ksa.write_bytes(ksa.read_bytes().replace(b"SAR", b"XXX", 1))
    with pytest.raises(ValueError):
        load_market("SA", tmp_path)


def test_cli_check_passes():
    root = Path(__file__).resolve().parents[3]
    r = subprocess.run([sys.executable, "-m", "services.datasets", "--check"], cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# ---------- coverage of markets ----------
def test_all_four_markets_present_with_currency(data):
    assert sorted(data) == ["AE", "EG", "QA", "SA"]
    assert {m: d["meta"]["currency"] for m, d in data.items()} == {"SA": "SAR", "AE": "AED", "EG": "EGP", "QA": "QAR"}


def test_vat_rate_is_a_config_value_and_used_everywhere(mk):
    rate = mk["config"]["vat"]["rate_percent"]
    assert "not tax logic" in mk["config"]["vat"]["source"]
    for doc in mk["sales_orders"] + mk["sales_invoices"] + mk["credit_notes"]:
        for v in doc["expected"]["vat_lines"]:
            assert v["rate_percent"] == str(D(rate))
    assert {i["vat_rate_percent"] for i in mk["items"]} == {rate}


def test_documented_rates_per_market(data):
    assert [data[m]["config"]["vat"]["rate_percent"] for m in ("SA", "AE", "EG", "QA")] == ["15", "5", "14", "0"]
    assert data["SA"]["config"]["rounding"]["mode"] == "ROUND_HALF_UP"


# ---------- internal consistency ----------
def test_references_resolve(mk):
    items = {i["code"] for i in mk["items"]}
    custs = {c["code"] for c in mk["customers"]}
    whs = {w["code"] for w in mk["warehouses"]}
    orders = {o["id"] for o in mk["sales_orders"]}
    dns = {d["id"] for d in mk["delivery_notes"]}
    invs = {i["id"] for i in mk["sales_invoices"]}
    pls = {p["code"] for p in mk["price_lists"]}
    for o in mk["sales_orders"]:
        assert o["customer"] in custs and o["warehouse"] in whs and o["price_list"] in pls
        assert all(l["item"] in items for l in o["lines"])
    for d in mk["delivery_notes"]:
        assert d["sales_order"] in orders and d["customer"] in custs and d["warehouse"] in whs
        assert all(l["item"] in items for l in d["lines"])
    for i in mk["sales_invoices"]:
        assert i["sales_order"] in orders and i["delivery_note"] in dns and i["customer"] in custs
    for c in mk["credit_notes"]:
        assert c["sales_invoice"] in invs
    for p in mk["payments"]:
        assert p["sales_invoice"] in invs and p["customer"] in custs
    for r in mk["opening_stock"]:
        assert r["item"] in items and r["warehouse"] in whs
    for pl in mk["price_lists"]:
        assert set(pl["rates"]) == items


def test_ids_unique(mk):
    for key in ("customers", "suppliers", "items", "sales_orders", "delivery_notes", "sales_invoices"):
        ids = [x.get("code") or x["id"] for x in mk[key]]
        assert len(ids) == len(set(ids)), key


def test_unit_prices_match_price_list(mk):
    pl = {p["code"]: p["rates"] for p in mk["price_lists"]}
    for o in mk["sales_orders"]:
        for l in o["lines"]:
            assert l["unit_price"] == pl[o["price_list"]][l["item"]]


def test_stock_never_negative_and_balances_match_replay(mk):
    bal = {(r["warehouse"], r["item"]): r["quantity"] for r in mk["opening_stock"]}
    assert all(v > 0 for v in bal.values())
    for dn in mk["delivery_notes"]:
        for l in dn["lines"]:
            bal[(dn["warehouse"], l["item"])] -= l["quantity"]
            assert bal[(dn["warehouse"], l["item"])] >= 0
    got = {(b["warehouse"], b["item"]): b["quantity"] for b in mk["expected"]["stock_balances"]}
    assert got == bal


def test_delivery_never_exceeds_order_and_invoice_never_exceeds_delivery(mk):
    orders = {o["id"]: o for o in mk["sales_orders"]}
    dns = {d["id"]: d for d in mk["delivery_notes"]}
    for d in mk["delivery_notes"]:
        ordered = {l["item"]: l["quantity"] for l in orders[d["sales_order"]]["lines"]}
        for l in d["lines"]:
            assert l["quantity"] <= ordered[l["item"]]
    for i in mk["sales_invoices"]:
        delivered = {l["item"]: l["quantity"] for l in dns[i["delivery_note"]]["lines"]}
        for l in i["lines"]:
            assert l["quantity"] <= delivered[l["item"]]


def test_document_totals_equal_decimal_sum_of_lines(mk):
    rate = mk["config"]["vat"]["rate_percent"]
    for doc in mk["sales_orders"] + mk["sales_invoices"] + mk["credit_notes"]:
        e = doc["expected"]
        nets = []
        for l in doc["lines"]:
            gross = D(l["quantity"]) * D(l["unit_price"])
            net = gross - q(gross * D(l["discount_percent"]) / 100)
            assert D(l["line_net"]) == net
            nets.append(net)
        sub = sum(nets, D("0"))
        disc = q(sub * D(doc.get("discount_percent", "0")) / 100)
        vat = q((sub - disc) * D(rate) / 100)
        assert (D(e["subtotal"]), D(e["document_discount"]), D(e["net_total"])) == (sub, disc, sub - disc)
        assert D(e["vat_amount"]) == vat == D(e["vat_lines"][0]["tax_amount"])
        assert D(e["total"]) == sub - disc + vat
        assert all(len(v.split(".")[1]) == 2 for v in (e["subtotal"], e["vat_amount"], e["total"]))


def test_invoice_totals_never_exceed_order_totals_and_outstanding_adds_up(mk):
    orders = {o["id"]: o for o in mk["sales_orders"]}
    for i in mk["sales_invoices"]:
        assert D(i["expected"]["total"]) <= D(orders[i["sales_order"]]["expected"]["total"])
        assert D(i["outstanding_amount"]) == D(i["expected"]["total"]) - D(i["paid_amount"]) - D(i["credited_amount"])
        assert D(i["outstanding_amount"]) >= 0
    total = sum(D(i["outstanding_amount"]) for i in mk["sales_invoices"])
    assert D(mk["expected"]["receivables_total"]) == total


def test_golden_path_rows(mk):
    so1, so2 = mk["sales_orders"][0], mk["sales_orders"][1]
    assert so1["customer"] == "CUST-001" and so1["warehouse"] == "W1"
    assert [(l["item"], l["quantity"], l["unit_price"]) for l in so1["lines"]] == [("ITEM-001", 10, "15.00")]
    assert so1["expected"]["net_total"] == "150.00"
    assert so2["discount_percent"] == "10" and so2["expected"]["net_total"] == "135.00"
    opening = [r for r in mk["opening_stock"] if r["item"] == "ITEM-001"]
    assert opening == [{"item": "ITEM-001", "quantity": 100, "valuation_rate": "10.00", "warehouse": "W1"}]
    assert mk["delivery_notes"][0]["expected"]["cost_of_goods_sold"] == "100.00"


def test_rounding_probe_exercises_half_up(data):
    for code in ("SA", "AE", "EG"):
        so = next(o for o in data[code]["sales_orders"] if o["scenario"] == "rounding_probe")
        raw = D(so["expected"]["vat_unrounded"])
        assert raw.as_tuple().exponent == -3 and str(raw).endswith("5")  # exact half cent
        assert D(so["expected"]["vat_amount"]) == raw.quantize(D("0.01"), rounding=ROUND_HALF_UP) > raw


def test_negative_amounts_round_away_from_zero():
    pos = compute_totals([(1, "37.50", "0")], "0", "15")["vat_amount"]
    neg = compute_totals([(1, "-37.50", "0")], "0", "15")["vat_amount"]
    assert pos == "5.63" and neg == "-5.63"


def test_credit_limit_story(mk):
    custs = {c["code"]: c for c in mk["customers"]}
    out = {}
    for i in mk["sales_invoices"]:
        out[i["customer"]] = out.get(i["customer"], D(0)) + D(i["outstanding_amount"])
    for code, v in out.items():
        assert v <= D(custs[code]["credit_limit"])
    held = [o for o in mk["sales_orders"] if o["hold_reason"]]
    assert [o["id"] for o in held] == ["SO-0009"] and held[0]["status"] == "pending_approval"
    assert D(held[0]["expected"]["total"]) > D(custs[held[0]["customer"]]["credit_limit"])


def test_statuses_and_roles_line_up_with_blueprint_fixture(mk):
    bp = json.loads((Path(__file__).resolve().parents[2] / "blueprint/fixtures/trading-distribution.blueprint.json").read_text("utf-8"))
    states = {s["id"] for w in bp["workflows"] if w["entity"] == "sales_order" for s in w["states"]}
    assert {o["status"] for o in mk["sales_orders"]} <= states
    assert {r["id"] for r in mk["roles"]} == {r["id"] for r in bp["roles"]}
    assert {u["role"] for u in mk["users"]} == {r["id"] for r in bp["roles"]}
    item = next(e for e in bp["entities"] if e["id"] == "item")
    opts = {f["id"]: {o["value"] for o in f.get("options", [])} for f in item["fields"]}
    assert {i["item_group"] for i in mk["items"]} <= opts["item_group"] and {i["unit"] for i in mk["items"]} <= opts["unit"]
    cust = next(e for e in bp["entities"] if e["id"] == "customer")
    groups = next(f for f in cust["fields"] if f["id"] == "customer_group")
    assert {c["customer_group"] for c in mk["customers"]} <= {o["value"] for o in groups["options"]}


# ---------- identifiers ----------
def test_saudi_vat_numbers_have_brksa40_shape_and_fake_marker(data):
    sa = data["SA"]
    nums = [sa["tenant"]["vat_number"]] + [p["vat_number"] for p in sa["customers"] + sa["suppliers"] if p["vat_number"]]
    assert len(nums) >= 10
    for n in nums:
        assert re.fullmatch(r"3\d{13}3", n), n  # 15 digits, first and last 3 (BR-KSA-40)
        assert n[1:6] == "99999", n  # reserved-looking marker block


def test_other_markets_tax_ids_carry_the_fake_marker_and_shape(data):
    for code, rx in (("AE", r"100\d{12}"), ("EG", r"\d{9}"), ("QA", r"\d{10}")):
        for p in [data[code]["tenant"]] + data[code]["customers"] + data[code]["suppliers"]:
            if p.get("vat_number"):
                assert re.fullmatch(rx, p["vat_number"]), (code, p["vat_number"])
                assert "999" in p["vat_number"]
    for p in data["AE"]["customers"] + data["QA"]["customers"]:
        if p["vat_number"]:
            assert "99999" in p["vat_number"]


def test_tax_ids_unique_within_market(mk):
    nums = [p["vat_number"] for p in mk["customers"] + mk["suppliers"] if p["vat_number"]] + [mk["tenant"]["vat_number"]]
    assert len(nums) == len(set(nums))


def test_registration_numbers_carry_marker(mk):
    for p in [mk["tenant"]] + mk["customers"] + mk["suppliers"]:
        if p.get("cr_number"):
            assert "99999" in p["cr_number"]


def test_emails_only_on_reserved_example_domains(mk):
    for text in strings(mk):
        for m in re.finditer(r"[\w.+-]+@([\w.-]+)", text):
            assert re.search(r"(^|\.)example\.(com|org)$", m.group(1)), m.group(0)


def test_every_party_has_an_example_email_and_fake_phone(mk):
    for p in [mk["tenant"]] + mk["customers"] + mk["suppliers"]:
        assert re.fullmatch(r"[a-z0-9.-]+@[a-z0-9.-]+\.example\.(com|org)", p["email"])
        assert re.fullmatch(r"\+(966|971|20|974) 000 000 0\d{3}", p["phone"]), p["phone"]


def test_no_real_looking_phone_numbers_anywhere(data):
    for code, doc in data.items():
        for text in strings(doc):
            for m in re.finditer(r"\+\d[\d ]{6,}", text):
                assert re.fullmatch(r"\+\d{2,3} 000 000 0\d{3}", m.group(0)), m.group(0)


def test_no_iban_or_card_like_numbers(data):
    for doc in data.values():
        for text in strings(doc):
            assert not re.search(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b", text)
            for m in re.finditer(r"\b\d{13,19}\b", text):  # only fake barcodes (999 prefix) and fake 15-digit tax ids
                assert m.group(0).startswith("999") or re.fullmatch(r"(3|100)99999\d+", m.group(0)), m.group(0)


# ---------- bilingual and edge cases ----------
def test_every_party_item_warehouse_has_both_names(mk):
    for p in mk["customers"] + mk["suppliers"] + mk["items"] + mk["warehouses"] + mk["price_lists"] + mk["users"]:
        assert p["name_ar"].strip() and p["name_en"].strip(), p
    t = mk["tenant"]
    assert t["legal_name_ar"] and t["legal_name_en"] and t["trade_name_ar"] and t["trade_name_en"]
    for p in mk["customers"] + mk["suppliers"] + mk["items"]:
        assert re.search("[؀-ۿ]", p["name_ar"]), p["name_ar"]
        assert re.search("[A-Za-z]", p["name_en"]), p["name_en"]


def test_edge_cases_present(mk):
    tags = {t: c for c in mk["customers"] for t in c["edge_cases"]}
    assert set(tags) == {"long_name", "apostrophes", "bidi_control_characters", "arabic_indic_digits"}
    long_ = tags["long_name"]
    assert 120 <= len(long_["name_en"]) <= 140 and 120 <= len(long_["name_ar"]) <= 140
    ap = tags["apostrophes"]["name_en"]
    assert "'" in ap and "’" in ap
    assert re.search("[٠-٩]", tags["arabic_indic_digits"]["name_ar"])
    bidi = tags["bidi_control_characters"]
    assert BIDI_CHARS.search(bidi["name_en"]) and BIDI_CHARS.search(bidi["name_ar"]) and bidi["bidi_controls"]


def test_bidi_controls_are_balanced_isolates_and_escaped_in_files(mk):
    bidi = next(c for c in mk["customers"] if "bidi_control_characters" in c["edge_cases"])
    name = bidi["name_en"]
    assert name.count("⁧") == name.count("⁩") == 1  # RLI closed by PDI
    assert not re.search("[‪-‮]", name)  # no embeddings or overrides
    for fname, text in all_text():
        assert not BIDI_CHARS.search(text), fname  # written as \\u escapes, never raw


def test_only_the_flagged_customers_contain_format_characters(mk):
    for c in mk["customers"]:
        has = bool(BIDI_CHARS.search(c["name_en"] + c["name_ar"]))
        assert has == ("bidi_control_characters" in c["edge_cases"])


def test_arabic_indic_digits_appear_in_data_and_order_note(mk):
    assert re.search("[٠-٩]", mk["sales_orders"][0]["notes_ar"])


# ---------- limits and safety ----------
def test_size_limits():
    sizes = [p.stat().st_size for p in DATA_DIR.iterdir()]
    assert max(sizes) < 100_000 and sum(sizes) < 300_000


def test_no_secret_like_strings():
    pats = [r"-----BEGIN", r"\bAKIA[0-9A-Z]{16}\b", r"\bgh[pousr]_[A-Za-z0-9]{20,}", r"\bxox[abprs]-", r"\bsk-[A-Za-z0-9_-]{20,}",
            r"AIza[0-9A-Za-z_-]{30,}", r"(?i)(password|passwd|secret|api[_-]?key|token)\"\s*:"]
    for name, text in all_text():
        for p in pats:
            assert not re.search(p, text), (name, p)


def test_engine_names_never_appear_in_data():
    for name, text in all_text():
        assert not re.search(r"(?i)frappe|erpnext", text), name


def test_no_local_paths_or_urls_other_than_example(data):
    for name, text in all_text():
        assert "/Users/" not in text and "/private/" not in text
        for m in re.finditer(r"https?://([\w.-]+)", text):
            assert m.group(1).endswith(("example.com", "example.org")), (name, m.group(0))


def test_everything_labelled_synthetic(mk):
    assert mk["meta"]["classification"] == "C1" and mk["meta"]["synthetic"] is True
    assert "not tax authority output" in mk["meta"]["notice"]
    assert "not tax authority output" in mk["expected"]["label"]
    for p in [mk["tenant"]] + mk["customers"] + mk["suppliers"] + mk["items"] + mk["users"]:
        assert p["synthetic"] is True


def test_build_market_is_pure():
    assert build_market("SA", DEFAULT_SEED) == build_market("SA", DEFAULT_SEED)
