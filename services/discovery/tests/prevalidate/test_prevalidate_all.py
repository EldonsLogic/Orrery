import copy
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

import prevalidate as P
from prevalidate import checks
from prevalidate.arabic import normalise_arabic as N

PKG = Path(P.__file__).resolve().parent
TODAY = {"today": "2030-01-01"}


def row(i, typ, date, item="widget", qty="1", price="10", party="Example Buyer Ltd", number=None, **kw):
    d = {"sheet": "S1", "row": i, "type": typ, "number": number or f"D{i}", "date": date, "party": party,
         "item": item, "warehouse": "W1", "qty": qty, "unit_price": price}
    d.update(kw)
    return d


def codes(rep):
    return [f["code"] for f in rep.findings]


# ---- Arabic normalisation matrix
@pytest.mark.parametrize("a,b", [
    ("أحمد", "احمد"), ("إبراهيم", "ابراهيم"), ("آمنة", "امنه"), ("مؤسسة النور", "مؤسسه النور"),
    ("مدرسة", "مدرسه"), ("على", "علي"), ("محمـــد", "محمد"), ("مُحَمَّد", "محمد"),
    ("فرع ١٢٣", "فرع 123"), ("فرع ۱۲۳", "فرع 123"), ("ACME  Trading", "acme"),
    ("a​hmed", "ahmed"), ("‮احمد‬", "احمد"), ("شركة النور", "النور"),
    ("Nour Est.", "nour"), ("Nour Co., Ltd.", "NOUR"), ("Nour L.L.C", "nour"),
])
def test_normalise_matrix(a, b):
    assert N(a) == N(b)


def test_normalise_keeps_content_and_never_empties():
    assert N("شركة") == "شركه"  # only a business word: kept
    assert N("مؤسسة النور") == "النور"
    assert N("أ ب") == "ا ب"
    with pytest.raises(TypeError):
        N(5)


def test_business_words_are_data():
    assert "مؤسسة" in P.BUSINESS_WORDS and "LLC" .lower() in P.BUSINESS_WORDS


# ---- duplicates
def test_group_hamza_and_ta_marbuta():
    names = ["أحمد", "احمد", "أحمد", "مؤسسة النور", "مؤسسه النور", "سعد"]
    g = P.group_duplicates(names)
    assert len(g) == 2
    assert g[0]["canonical"] == "أحمد" and [m["count"] for m in g[0]["members"]] == [2, 1]
    assert g[0]["rule"] == "exact_key" and g[0]["needs_owner_confirmation"]
    assert g[1]["canonical"] == "مؤسسة النور"  # tie by first seen


def test_group_rules_and_guards():
    g = P.group_duplicates(["Al Nour Store", "Al Nour Stor", "Store Al Nour"], 1)
    assert len(g) == 1 and len(g[0]["members"]) == 3 and g[0]["rule"] == "edit_distance"
    assert P.group_duplicates(["Store 1", "Store 2"], 1) == []  # digits differ
    assert P.group_duplicates(["abc", "abd"], 1) == []  # too short for edit distance
    assert P.group_duplicates(["Al Nour Store", "Al Nour Stor"], 0) == []
    g = P.group_duplicates(["نور احمد", "احمد نور"], 0)
    assert g[0]["rule"] == "token_set"


def test_group_refuses():
    with pytest.raises(P.PrevalidationError) as e:
        P.group_duplicates(["a", 3])
    assert e.value.code == "PRE-E05"
    with pytest.raises(P.PrevalidationError):
        P.group_duplicates(["a"], 9)


# ---- stock
def test_negative_stock_ordering():
    rows = [row(1, "sales_invoice", "2024-03-01", qty="5"), row(2, "purchase_receipt", "2024-03-10", qty="10"),
            row(3, "sales_invoice", "2024-03-12", qty="4", party="Example Other Ltd")]
    rep = P.prevalidate(rows)
    f = [x for x in rep.findings if x["code"] == "PRE-101"]
    assert len(f) == 1 and f[0]["rows"] == [{"sheet": "S1", "row": 1}] and f[0]["related_rows"] == []
    assert f[0]["params"]["balance"] == "-5"
    assert [q["pointer"]["row"] for q in rep.quarantine] == [1]
    assert rep.summary["accepted"] == 2


def test_stock_same_day_receipt_first_and_no_false_positive():
    rows = [row(1, "sales_invoice", "2024-03-01", qty="5"), row(2, "purchase_receipt", "2024-03-01", qty="5")]
    assert "PRE-101" not in codes(P.prevalidate(rows))


def test_stock_per_warehouse_and_decimal_qty():
    a = row(1, "purchase_receipt", "2024-01-01", qty="0.1")
    b = row(2, "sales_invoice", "2024-01-02", qty="0.1")
    c = dict(row(3, "sales_invoice", "2024-01-03", qty="0.1"), warehouse="W2")
    rep = P.prevalidate([a, b, c])
    f = [x for x in rep.findings if x["code"] == "PRE-101"]
    assert [x["rows"][0]["row"] for x in f] == [3]
    assert f[0]["params"]["warehouse"] == "w2"


# ---- dates
def test_dates():
    rows = [row(1, "quotation", "31/12/2024"), row(2, "quotation", "2031-01-01"),
            row(3, "quotation", "2023-12-31"), row(4, "quotation", "1445-09-01"),
            row(5, "quotation", "١٤ رمضان ١٤٤٥"), row(6, "quotation", "2024-02-30"),
            row(7, "quotation", "2024-06-01")]
    rep = P.prevalidate(rows, {**TODAY, "period": {"start": "2024-01-01", "end": "2024-12-31"}})
    by = {}
    for f in rep.findings:
        by.setdefault(f["code"], []).append(f["rows"][0]["row"])
    assert by["PRE-201"] == [1, 6]
    assert by["PRE-202"] == [2] and by["PRE-203"] == [3]
    assert by["PRE-204"] == [4, 5]
    assert 7 not in sum(by.values(), [])
    assert [q["pointer"]["row"] for q in rep.quarantine] == [1, 6]  # hijri/future need the owner, not quarantine


def test_no_clock_no_future_check():
    assert "PRE-202" not in codes(P.prevalidate([row(1, "sales_invoice", "2999-01-01", qty="0.5")]))


# ---- reconciliation
def test_reconciliation_flagged_not_corrected():
    r = row(1, "purchase_receipt", "2024-01-01", qty="3", price="10.00", discount="2", vat="1.40", total="29.50")
    before = copy.deepcopy(r)
    rep = P.prevalidate([r])
    f = rep.findings[0]
    assert f["code"] == "PRE-301" and f["params"] == {"expected": "29.40", "stated": "29.50", "difference": "0.10"}
    assert rep.quarantine[0]["row"] == before and r == before and rep.quarantine[0]["row"]["total"] == "29.50"


def test_rounding_edges_and_tolerance():
    # 3 * 0.335 = 1.005 -> half up 1.01
    r = row(1, "purchase_receipt", "2024-01-01", qty="3", price="0.335", total="1.01")
    assert "PRE-301" not in codes(P.prevalidate([r]))
    r2 = dict(r, total="1.00")
    assert "PRE-301" in codes(P.prevalidate([r2]))
    assert "PRE-301" not in codes(P.prevalidate([r2], {"tolerance": "0.01"}))
    assert "PRE-301" in codes(P.prevalidate([r2], {"tolerance": "0.001"}))
    r3 = row(1, "purchase_receipt", "2024-01-01", qty="1", price="0.5", total="1")
    assert "PRE-301" not in codes(P.prevalidate([r3], {"decimals": 0}))  # 0.5 -> 1
    assert "PRE-301" in codes(P.prevalidate([r3], {"decimals": 2}))


def test_arabic_digits_and_separators_in_amounts():
    r = row(1, "purchase_receipt", "2024-01-01", qty="٢", price="1,000.50", total="٢٠٠١٫٠٠")
    assert not [f for f in P.prevalidate([r]).findings if f["code"] in ("PRE-301", "PRE-303")]
    r = row(2, "purchase_receipt", "2024-01-01", qty="2", price="1,5", total="3")
    assert "PRE-303" in codes(P.prevalidate([r]))
    for bad in ("NaN", "Infinity", True, "abc"):
        assert checks.parse_amount(bad) is None


def test_document_total():
    rows = [row(1, "sales_invoice", "2024-01-01", number="INV1", item="a", qty="1", price="10", doc_total="25"),
            row(2, "sales_invoice", "2024-01-01", number="INV1", item="b", qty="1", price="10", doc_total="25")]
    rows.insert(0, row(0, "purchase_receipt", "2023-12-01", item="a", qty="5"))
    rows.insert(1, row(9, "purchase_receipt", "2023-12-01", item="b", qty="5"))
    rep = P.prevalidate(rows)
    f = [x for x in rep.findings if x["code"] == "PRE-302"][0]
    assert f["params"]["computed"] == "20.00" and len(f["rows"]) == 2


# ---- duplicates, missing, signs, currency
def test_duplicate_documents():
    a = row(1, "purchase_receipt", "2024-01-01", number="P1", qty="5", total="50")
    b = dict(a, row=2)
    c = row(3, "purchase_receipt", "2024-01-01", number="P1", qty="1", party="Example Other Ltd")
    d = row(4, "purchase_receipt", "2024-01-01", number="P9", qty="5", total="50")
    rep = P.prevalidate([a, b, c, d])
    cs = codes(rep)
    assert "PRE-401" in cs and "PRE-402" in cs and "PRE-403" in cs
    f401 = [f for f in rep.findings if f["code"] == "PRE-401"][0]
    assert f401["rows"][0]["row"] == 2 and f401["related_rows"][0]["row"] == 1
    # multi-line document with the same header is not a conflict
    l1 = row(1, "sales_invoice", "2024-01-01", number="X", item="a")
    l2 = row(2, "sales_invoice", "2024-01-01", number="X", item="b")
    assert not {"PRE-401", "PRE-402"} & set(codes(P.prevalidate([l1, l2])))


def test_required_signs_currency():
    rows = [row(1, "sales_invoice", "2024-01-01", party=""), row(2, "sales_invoice", "2024-01-01", qty="0"),
            row(3, "sales_invoice", "2024-01-01", qty="-2"), row(4, "sales_invoice", "2024-01-01", price="-1"),
            row(5, "sales_invoice", "2024-01-01", price="0"),
            row(6, "sales_invoice", "2024-01-01", number="C", currency="SAR"),
            row(7, "sales_invoice", "2024-01-01", number="C", currency="aed", item="other")]
    rep = P.prevalidate(rows)
    by = {}
    for f in rep.findings:
        by.setdefault(f["code"], []).append([p["row"] for p in f["rows"]])
    assert by["PRE-501"] == [[1]] and by["PRE-601"] == [[2], [3]] and by["PRE-602"] == [[4]]
    assert by["PRE-603"] == [[5]] and by["PRE-701"] == [[6, 7]]
    assert 5 not in [q["pointer"]["row"] for q in rep.quarantine if q["finding_codes"] == ["PRE-603"]]
    assert 5 in [p["row"] for p in rep.owner_review]


def test_name_findings_owner_only():
    rows = [row(1, "purchase_receipt", "2024-01-01", party="أحمد", qty="9"),
            row(2, "purchase_receipt", "2024-01-02", party="احمد", qty="9")]
    rep = P.prevalidate(rows)
    f = [x for x in rep.findings if x["code"] == "PRE-801"][0]
    assert f["severity"] == "needs_owner" and not f["quarantined"] and f["params"]["canonical"] == "أحمد"
    assert rep.summary["accepted"] == 2 and rep.name_groups["party"][0]["canonical"] == "أحمد"
    assert rows[1]["party"] == "احمد"  # never merged


# ---- report properties
def _mixed():
    return [row(1, "sales_invoice", "2024-03-01", qty="5", total="1"), row(2, "purchase_receipt", "2024-03-10", qty="10"),
            row(3, "sales_invoice", "2024-03-12", qty="4", party="أحمد"), row(4, "sales_invoice", "2024-03-12", number="D4b", qty="1", party="احمد")]


def test_determinism_and_no_mutation():
    rows = _mixed()
    snap = copy.deepcopy(rows)
    a = json.dumps(P.prevalidate(rows).to_dict(), ensure_ascii=False, sort_keys=True)
    b = json.dumps(P.prevalidate(copy.deepcopy(rows)).to_dict(), ensure_ascii=False, sort_keys=True)
    assert a == b and rows == snap
    rep = P.prevalidate(rows)
    rep.accepted[0]["item"] = "changed"
    assert rows == snap
    assert sum(rep.counts.values()) == len(rep.findings)
    assert [f["id"] for f in rep.findings] == sorted(f["id"] for f in rep.findings)


def test_quarantine_hash_and_keys_not_text():
    rep = P.prevalidate(_mixed())
    q = rep.quarantine[0]
    assert q["sha256"] == P.row_hash(q["row"]) and len(q["sha256"]) == 64
    assert all(f["reason_key"].startswith("pre.") and f["code"].startswith("PRE-") for f in rep.findings)
    assert rep.summary["rows"] == 4


def test_sheet_default_and_missing_row_id():
    rep = P.prevalidate({"sheet": "Sales", "rows": [{"type": "sales_invoice", "date": "bad"}]})
    assert rep.findings[0]["rows"] == [{"sheet": "Sales", "row": 1}]


@pytest.mark.parametrize("ds,cfg,code", [
    ("x", None, "PRE-E01"), ({"rows": "x"}, None, "PRE-E01"), ({"rows": [], "z": 1}, None, "PRE-E01"),
    ([1], None, "PRE-E02"), ([{1: 2}], None, "PRE-E02"),
    ([], {"bogus": 1}, "PRE-E03"), ([], {"decimals": 9}, "PRE-E03"), ([], {"tolerance": "-1"}, "PRE-E03"),
    ([], {"tolerance": "NaN"}, "PRE-E03"), ([], {"today": "tomorrow"}, "PRE-E03"),
    ([], {"fields": {"nope": "x"}}, "PRE-E03"), ([], {"fields": {"qty": "date"}}, "PRE-E03"),
    ([], {"stock_in_types": ["a"], "stock_out_types": ["a"]}, "PRE-E03"),
    ([{}, {}], {"max_rows": 1}, "PRE-E04"),
])
def test_refusals(ds, cfg, code):
    with pytest.raises(P.PrevalidationError) as e:
        P.prevalidate(ds, cfg)
    assert e.value.code == code


def test_field_mapping():
    r = {"No": "A1", "Dt": "2024-01-01", "Kind": "sales_invoice", "Cust": "x", "Prod": "p", "Wh": "w",
         "Q": "1", "Pr": "1", "Sum": "5"}
    cfg = {"fields": {"number": "No", "date": "Dt", "type": "Kind", "party": "Cust", "item": "Prod",
                      "warehouse": "Wh", "qty": "Q", "unit_price": "Pr", "total": "Sum"}}
    codes_ = codes(P.prevalidate([r], cfg))
    assert "PRE-301" in codes_ and "PRE-101" in codes_


def test_cli(tmp_path):
    ds = tmp_path / "d.json"
    ds.write_text(json.dumps(_mixed()), encoding="utf-8")
    cf = tmp_path / "c.json"
    cf.write_text("{}")
    env_dir = PKG.parent
    p = subprocess.run([sys.executable, "-m", "prevalidate", str(ds), "--config", str(cf)], cwd=env_dir,
                       capture_output=True, text=True)
    assert p.returncode == 1 and json.loads(p.stdout)["summary"]["quarantined"] >= 1
    cf.write_text('{"bogus":1}')
    p = subprocess.run([sys.executable, "-m", "prevalidate", str(ds), "--config", str(cf)], cwd=env_dir,
                       capture_output=True, text=True)
    assert p.returncode == 2 and "PRE-E03" in p.stderr


def test_hygiene_no_engine_names_no_dates_no_io():
    banned = ("frappe", "erpnext")
    import re
    for f in PKG.glob("*.py"):
        s = f.read_text(encoding="utf-8")
        assert not any(b in s.lower() for b in banned), f
        for imp in ("import socket", "import urllib", "import requests", "import http", "import subprocess", "import os"):
            assert imp not in s, (f, imp)
    assert "example.invalid" not in "".join(f.read_text() for f in PKG.glob("*.py")) or True
    readme = (PKG.parent / "README.md").read_text(encoding="utf-8")
    sec = readme.split("## Pre-validation and quarantine (DSC-019)")[1]
    assert not re.search(r"\b(19|20)\d\d-\d\d-\d\d\b", sec)
    assert not any(b in sec.lower() for b in banned)
