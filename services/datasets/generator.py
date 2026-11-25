"""Deterministic generator for the synthetic trading and distribution datasets. Stdlib only.

Everything is invented. Amounts are strings with two decimals; the `expected` blocks are synthetic test
expectations computed with Decimal (see money.py), never tax authority output.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from decimal import Decimal

from . import DEFAULT_SEED, GENERATOR_VERSION
from .money import ROUNDING, compute_totals, d, q, s
from .names import ACTIVITIES, ITEM_GROUPS, ITEMS, MARKETS, ROLES, STEMS, UNITS, USER_NAMES
from .rng import Rng, ranked

BASE_DATE = dt.date(2026, 10, 4)
CLASSIFICATION = "C1"
NOTICE = ("Synthetic data (class C1). Names, identifiers, phones and emails are invented. Amounts under `expected` are "
          "synthetic test expectations computed with Decimal, not tax authority output.")
FAKE_MARKER = "99999"
BIDI_CHARS = re.compile("[​-‏‪-‮⁠-⁩﻿]")


def dumps(obj) -> str:
    """Stable JSON: sorted keys, 2-space indent, UTF-8 text, format characters written as \\u escapes."""
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    return BIDI_CHARS.sub(lambda m: "\\u%04x" % ord(m.group(0)), text)


def _dt(days: int) -> str:
    return (BASE_DATE + dt.timedelta(days=days)).isoformat()


class _Ids:
    """Unique fake serials per market."""

    def __init__(self, rng: Rng):
        self.rng, self.seen = rng, set()

    def serial(self, digits: int) -> int:
        while True:
            n = self.rng.int(10 ** (digits - 1), 10 ** digits - 1)
            if (digits, n) not in self.seen:
                self.seen.add((digits, n))
                return n


def fake_vat(code: str, serial: int) -> str:
    if code == "SA":  # 15 digits, first and last 3 (BR-KSA-40 shape), reserved-looking middle block
        return f"3{FAKE_MARKER}{serial:04d}9999" + "3"
    if code == "AE":  # 15 digits starting 100
        return f"100{FAKE_MARKER}{serial:04d}999"
    if code == "EG":  # 9 digits
        return f"999{serial % 1000:03d}999"
    return f"{FAKE_MARKER}{serial:04d}9"  # QA: 10 digits (format itself is invented)


def fake_cr(code: str, serial: int) -> str:
    if code == "SA":
        return f"{FAKE_MARKER}{serial % 100000:05d}"
    return f"{'TL' if code == 'AE' else 'CR'}-{FAKE_MARKER}-{serial:04d}"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _party(code, cfg, ids, rng, kind, idx, name_ar, name_en, city, extra):
    slug = f"{_slug(name_en)[:40].rstrip('-')}-{idx}"
    tld = "com" if rng.int(0, 1) == 0 else "org"
    n = ids.serial(4)
    rec = {
        "name_ar": name_ar, "name_en": name_en, "city_ar": city[0], "city_en": city[1],
        "vat_number": fake_vat(code, n), "cr_number": fake_cr(code, ids.serial(4)),
        "email": f"accounts@{slug}.example.{tld}", "phone": f"+{cfg['cc']} 000 000 0{idx:03d}",
        "synthetic": True, "disabled": False, "edge_cases": [],
    }
    rec.update(extra)
    return rec


def _tenant(code, cfg, seed, ids, stems):
    rng = Rng(seed, code + "|tenant")
    if cfg["tenant"]:
        lar, len_, tar, ten, slug = cfg["tenant"]
    else:
        sar, sen = stems.pop(0)
        lar, len_ = cfg["legal_ar"].format(f"{sar} للتجارة"), cfg["legal_en"].format(f"{sen} Trading")
        tar, ten, slug = sar, sen, _slug(sen)
    return {
        "legal_name_ar": lar, "legal_name_en": len_, "trade_name_ar": tar, "trade_name_en": ten,
        "country": code, "currency": cfg["currency"], "timezone": cfg["tz"],
        "vat_number": fake_vat(code, 1), "cr_number": fake_cr(code, 1),
        "email": f"finance@{slug}.example.com", "phone": f"+{cfg['cc']} 000 000 0001",
        "language_primary": "ar", "language_secondary": ["en"], "synthetic": True,
        "id": "TENANT-" + code,
    }


def _long(text: str) -> str:
    return (text * 3)[:140].rstrip()


def _customers(code, cfg, seed, ids, stems, cities):
    rng = Rng(seed, code + "|cust")
    scale = d(cfg["scale"])
    limit = s(Decimal("50000") * scale)
    out = []

    def add(idx, nar, nen, ctype, group, city, extra=None, **over):
        rec = _party(code, cfg, ids, rng, "customer", idx + 10, nar, nen, city, {
            "code": f"CUST-{idx:03d}", "customer_type": ctype, "customer_group": group,
            "payment_terms_days": rng.int(1, 3) * 15, "credit_limit": limit,
        })
        rec.update(extra or {})
        rec.update(over)
        out.append(rec)

    acts = ranked(seed, code + "|cact", [str(i) for i in range(len(ACTIVITIES))])
    for i in range(1, 5):
        sar, sen = stems.pop(0)
        aar, aen = ACTIVITIES[int(acts[i])]
        add(i, cfg["legal_ar"].format(f"{sar} {aar}"), cfg["legal_en"].format(f"{sen} {aen}"), "company",
            "key_account" if i == 4 else "wholesale", cities[i % 3])
    iar, ien = cfg["individual"]
    add(5, iar, ien, "individual", "retail", cities[0], vat_number=None, cr_number=None)
    base_en = "Synthetic Long Name Test Trading and Distribution of Dry Foodstuff Beverages Cleaning and Packaging Supplies "
    base_ar = "اسم طويل تجريبي للتجارة والتوزيع للمواد الغذائية الجافة والمشروبات والمنظفات ومستلزمات التغليف والتعبئة "
    add(6, _long(base_ar), _long(base_en), "company", "wholesale", cities[1], edge_cases=["long_name"])
    add(7, "مؤسسة «أبو المعالي» وأولاده", "Abu Al-Ma'ali & Sons' Trading Est. (Ma’ali’s)", "company", "wholesale",
        cities[2], edge_cases=["apostrophes"], credit_limit=s(Decimal("500") * scale))
    add(8, "تجربة ثنائية الاتجاه ‏(Bidi)‏ للتجارة", "Bidi Edge ⁧تجربة⁩ Trading", "company",
        "wholesale", cities[0], edge_cases=["bidi_control_characters"],
        bidi_controls=["U+200F", "U+2067", "U+2069"])
    add(9, "متجر رقم ٧ للتجارة ١٢٣", "Store No. 7 Trading 123", "company", "wholesale", cities[1],
        edge_cases=["arabic_indic_digits"])
    for c in out:
        c["price_list"] = "PL-RETAIL" if c["customer_group"] == "retail" else "PL-WHOLESALE"
    return out


def _suppliers(code, cfg, seed, ids, stems, cities):
    rng = Rng(seed, code + "|sup")
    out = []
    kinds = [("local", ("للتوزيع", "Distribution")), ("importer", ("للاستيراد", "Imports")),
             ("manufacturer", ("للصناعات الغذائية", "Food Industries")), ("importer", ("للتغليف", "Packaging"))]
    for i, (stype, (aar, aen)) in enumerate(kinds, 1):
        sar, sen = stems.pop(0)
        out.append(_party(code, cfg, ids, rng, "supplier", 50 + i, cfg["legal_ar"].format(f"{sar} {aar}"),
                          cfg["legal_en"].format(f"{sen} {aen}"), cities[i % 3], {
                              "code": f"SUP-{i:03d}", "supplier_type": stype, "payment_terms_days": rng.int(2, 4) * 15}))
    return out


def _items(code, cfg, seed):
    rng = Rng(seed, code + "|items")
    scale = d(cfg["scale"])
    items, rates = [], {}
    for n, (icode, iar, ien, grp, unit, cost, price) in enumerate(ITEMS):
        if icode == "ITEM-001":  # golden path: cost 10.00, price 15.00 in every market
            c, p = d(cost), d(price)
        elif price is None:
            c, p = d(cost), d(cfg["probe"])
        else:
            jitter = Decimal(100 + rng.int(-5, 5)) / 100
            c, p = q(d(cost) * scale * jitter), q(d(price) * scale * jitter)
        rates[icode] = (c, p)
        items.append({"code": icode, "name_ar": iar, "name_en": ien, "item_group": grp, "unit": unit,
                      "is_stock_item": True, "cost_price": s(c), "vat_rate_percent": cfg["vat_rate"],
                      "barcode": f"9990000{n + 1:06d}", "reorder_level": 20, "synthetic": True})
    return items, rates


def _price_lists(rates):
    wh = {k: p for k, (c, p) in rates.items()}
    return [
        {"code": "PL-WHOLESALE", "name_ar": "قائمة أسعار الجملة", "name_en": "Wholesale price list",
         "customer_groups": ["wholesale", "key_account"], "is_default": True,
         "rates": {k: s(v) for k, v in sorted(wh.items())}},
        {"code": "PL-RETAIL", "name_ar": "قائمة أسعار التجزئة", "name_en": "Retail price list",
         "customer_groups": ["retail"], "is_default": False,
         "rates": {k: s(v if k in ("ITEM-001", "ITEM-013") else v * Decimal("1.10")) for k, v in sorted(wh.items())}},
    ]


def _opening(code, seed, rates):
    rng = Rng(seed, code + "|stock")
    rows = []
    for icode, _a, _b, _g, unit, _c, _p in ITEMS:
        for wh in ("W1", "W2"):
            if icode == "ITEM-001":
                if wh == "W2":
                    continue
                qty = 100  # golden path opening balance
            elif unit == "pallet":
                qty = rng.int(20, 40)
            else:
                qty = rng.int(150, 400)
            rows.append({"warehouse": wh, "item": icode, "quantity": qty, "valuation_rate": s(rates[icode][0])})
    return rows


# (order, customer no, warehouse, discount %, [(item no, qty or None, line discount %)], status, delivered, paid, note)
SCENARIO = [
    ("SO-0001", 1, "W1", "0", [(1, 10, "0")], "invoiced", "full", None, "golden"),
    ("SO-0002", 1, "W1", "10", [(1, 10, "0")], "invoiced", "full", None, "golden_discount"),
    ("SO-0003", 2, "W1", "0", [(2, None, "0"), (3, None, "5"), (4, None, "0")], "invoiced", "full", "60", "part_paid"),
    ("SO-0004", 3, "W2", "5", [(5, None, "0"), (6, None, "10"), (7, None, "0")], "invoiced", "full", "100", "paid"),
    ("SO-0005", 4, "W1", "0", [(2, 20, "0")], "approved", "12", None, "partial_delivery"),
    ("SO-0006", 5, "W1", "0", [(8, None, "0"), (9, None, "0"), (10, None, "0")], "invoiced", "full", None, "credit_note"),
    ("SO-0007", 2, "W1", "0", [(13, 1, "0")], "invoiced", "full", None, "rounding_probe"),
    ("SO-0008", 6, "W1", "0", [(11, None, "0"), (12, 2, "0")], "approved", None, None, "long_name_open"),
    ("SO-0009", 7, "W1", "0", [(12, 1, "0")], "pending_approval", None, None, "credit_limit_exceeded"),
    ("SO-0010", 8, "W1", "0", [(4, None, "0")], "draft", None, None, "bidi_draft"),
    ("SO-0011", 9, "W1", "0", [(8, None, "0")], "approved", None, None, "arabic_indic_open"),
]


def _qty(rng, unit):
    return rng.int(1, 3) if unit == "pallet" else rng.int(5, 30)


def _documents(code, cfg, seed, customers, rates, price_lists):
    rng = Rng(seed, code + "|docs")
    rate = cfg["vat_rate"]
    by_unit = {i[0]: i[4] for i in ITEMS}
    cust = {c["code"]: c for c in customers}
    pl = {p["code"]: p["rates"] for p in price_lists}
    orders, dns, invs, cns, pays = [], [], [], [], []
    for n, (oid, cno, wh, disc, lines, status, delivered, paid, note) in enumerate(SCENARIO):
        c = cust[f"CUST-{cno:03d}"]
        olines = []
        for ino, qty, ld in lines:
            icode = f"ITEM-{ino:03d}"
            olines.append({"item": icode, "quantity": qty if qty is not None else _qty(rng, by_unit[icode]),
                           "unit_price": pl[c["price_list"]][icode], "discount_percent": ld})
        day = n * 2
        exp = compute_totals([(l["quantity"], l["unit_price"], l["discount_percent"]) for l in olines], disc, rate)
        for l, net in zip(olines, exp["line_nets"]):
            l["line_net"] = net
        limit, hold = d(c["credit_limit"]), None
        if d(exp["total"]) > limit:
            hold = "credit_limit_exceeded"
        orders.append({
            "id": oid, "customer": c["code"], "warehouse": wh, "price_list": c["price_list"], "order_date": _dt(day),
            "delivery_date": _dt(day + 2), "discount_percent": disc, "status": status, "scenario": note,
            "hold_reason": hold, "lines": olines, "expected": exp,
            "notes_ar": "تسليم ١٠ قطع" if oid == "SO-0001" else "", "notes_en": "Deliver 10 pieces" if oid == "SO-0001" else "",
        })
        if delivered is None:
            continue
        dq = {l["item"]: (l["quantity"] if delivered == "full" else int(delivered)) for l in olines}
        dn_id, inv_id = f"DN-{len(dns) + 1:04d}", f"INV-{len(invs) + 1:04d}"
        cogs = sum(d(dq[l["item"]]) * d(rates[l["item"]][0]) for l in olines)
        dns.append({"id": dn_id, "sales_order": oid, "customer": c["code"], "warehouse": wh, "delivery_date": _dt(day + 2),
                    "lines": [{"item": l["item"], "quantity": dq[l["item"]]} for l in olines],
                    "expected": {"cost_of_goods_sold": s(cogs), "valuation": "moving_average (single cost, no receipts)"}})
        ilines = [{"item": l["item"], "quantity": dq[l["item"]], "unit_price": l["unit_price"],
                   "discount_percent": l["discount_percent"]} for l in olines]
        iexp = compute_totals([(l["quantity"], l["unit_price"], l["discount_percent"]) for l in ilines], disc, rate)
        for l, net in zip(ilines, iexp["line_nets"]):
            l["line_net"] = net
        credit = Decimal("0")
        cn_id = None
        if note == "credit_note":
            cn_id = f"CN-{len(cns) + 1:04d}"
            cl = [{"item": "ITEM-008", "quantity": 2, "unit_price": s(Decimal("0.25") * d(cfg["scale"])), "discount_percent": "0"}]
            cexp = compute_totals([(x["quantity"], x["unit_price"], x["discount_percent"]) for x in cl], "0", rate)
            cl[0]["line_net"] = cexp["line_nets"][0]
            credit = d(cexp["total"])
            cns.append({"id": cn_id, "sales_invoice": inv_id, "customer": c["code"], "credit_date": _dt(day + 6),
                        "reason": "price_correction", "returns_to_stock": False, "lines": cl, "expected": cexp})
        paid_amt = q(d(iexp["total"]) * d(paid) / 100) if paid else Decimal("0")
        if paid:
            pid = f"PAY-{len(pays) + 1:04d}"
            pays.append({"id": pid, "payment_type": "receive", "customer": c["code"], "sales_invoice": inv_id,
                         "posting_date": _dt(day + 8), "amount": s(paid_amt), "method": "bank_transfer" if len(pays) % 2 == 0 else "mada",
                         "bank_reference": f"SYN-{code}-{len(pays) + 1:04d}"})
        invs.append({"id": inv_id, "sales_order": oid, "delivery_note": dn_id, "customer": c["code"],
                     "invoice_date": _dt(day + 2), "due_date": _dt(day + 2 + c["payment_terms_days"]),
                     "discount_percent": disc, "lines": ilines, "expected": iexp, "paid_amount": s(paid_amt),
                     "credit_note": cn_id, "credited_amount": s(credit),
                     "outstanding_amount": s(d(iexp["total"]) - paid_amt - credit),
                     "zatca_status": "not_sent" if code == "SA" else None})
        if delivered == "full":
            orders[-1]["status"] = "invoiced"
    return orders, dns, invs, cns, pays


def _expected_balances(opening, dns, rates):
    bal = {(r["warehouse"], r["item"]): r["quantity"] for r in opening}
    for dn in dns:
        for l in dn["lines"]:
            bal[(dn["warehouse"], l["item"])] -= l["quantity"]
    return [{"warehouse": w, "item": i, "quantity": qy, "valuation_rate": s(rates[i][0]), "stock_value": s(d(qy) * rates[i][0])}
            for (w, i), qy in sorted(bal.items())]


def build_market(code: str, seed: int) -> dict:
    cfg = MARKETS[code]
    stems = [(a, e) for a, e in ranked(seed, code + "|stems", STEMS) if e != "Al Waha"]
    ids = _Ids(Rng(seed, code + "|ids"))
    tenant = _tenant(code, cfg, seed, ids, stems)
    cities = cfg["cities"]
    customers = _customers(code, cfg, seed, ids, stems, cities)
    suppliers = _suppliers(code, cfg, seed, ids, stems, cities)
    items, rates = _items(code, cfg, seed)
    plists = _price_lists(rates)
    opening = _opening(code, seed, rates)
    orders, dns, invs, cns, pays = _documents(code, cfg, seed, customers, rates, plists)
    users = []
    for (rid, rar, ren), (uar, uen) in zip(ROLES, ranked(seed, code + "|un", USER_NAMES)):
        users.append({"id": f"user-{rid}", "role": rid, "name_ar": f"{uar} التجريبي", "name_en": f"{uen} Sample",
                      "email": f"{rid.replace('_', '.')}@{tenant['id'].lower()}.example.com", "synthetic": True})
    outstanding = {}
    for inv in invs:
        outstanding[inv["customer"]] = outstanding.get(inv["customer"], Decimal("0")) + d(inv["outstanding_amount"])
    return {
        "meta": {
            "market": code, "country_en": cfg["country_en"], "country_ar": cfg["country_ar"], "currency": cfg["currency"],
            "classification": CLASSIFICATION, "synthetic": True, "notice": NOTICE, "base_date": BASE_DATE.isoformat(),
            "seed": seed, "generator_version": GENERATOR_VERSION,
            "blueprint_fixture": "services/blueprint/fixtures/trading-distribution.blueprint.json",
            "golden_path": "docs/specs/golden-path-trading-sale.md (ITEM-001, W1, CUST-001 and SO-0001 / SO-0002 follow it; "
                           "here VAT is applied at the configured rate, the golden path itself has no tax)",
        },
        "config": {
            "vat": {"rate_percent": cfg["vat_rate"], "source": "synthetic test configuration for this dataset; not tax logic, "
                    "not verified against any authority (UNVERIFIED)", "prices_include_vat": False},
            "rounding": {"mode": ROUNDING, "decimals": 2, "note": "half away from zero; VAT rounded once per document on the net total"},
            "valuation": "moving_average",
        },
        "tenant": tenant,
        "warehouses": [
            {"code": "W1", "name_ar": f"مستودع {cities[0][0]}", "name_en": f"{cities[0][1]} warehouse", "city_en": cities[0][1],
             "location_id": "wh_" + _slug(cities[0][1]).replace("-", "_")},
            {"code": "W2", "name_ar": f"مستودع {cities[1][0]}", "name_en": f"{cities[1][1]} warehouse", "city_en": cities[1][1],
             "location_id": "wh_" + _slug(cities[1][1]).replace("-", "_")},
        ],
        "roles": [{"id": r, "name_ar": a, "name_en": e} for r, a, e in ROLES],
        "users": users,
        "item_groups": [{"code": c, "name_ar": a, "name_en": e} for c, a, e in ITEM_GROUPS],
        "units": [{"code": c, "name_ar": a, "name_en": e} for c, a, e in UNITS],
        "items": items,
        "price_lists": plists,
        "customers": customers,
        "suppliers": suppliers,
        "opening_stock": opening,
        "sales_orders": orders,
        "delivery_notes": dns,
        "sales_invoices": invs,
        "credit_notes": cns,
        "payments": pays,
        "expected": {
            "label": "synthetic test expectations, not tax authority output",
            "stock_balances": _expected_balances(opening, dns, rates),
            "receivables_by_customer": {k: s(v) for k, v in sorted(outstanding.items())},
            "receivables_total": s(sum(outstanding.values(), Decimal("0"))),
        },
    }


def generate(seed: int = DEFAULT_SEED) -> dict:
    """Return {relative path: bytes} for every output file, manifest last."""
    files = {}
    for code in sorted(MARKETS):
        files[MARKETS[code]["file"]] = dumps(build_market(code, seed)).encode("utf-8")
    entries = []
    for name, data in sorted(files.items()):
        doc = json.loads(data)
        entries.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "market": doc["meta"]["market"],
                        "counts": {k: len(doc[k]) for k in ("customers", "suppliers", "items", "warehouses", "price_lists", "opening_stock",
                                                            "sales_orders", "delivery_notes", "sales_invoices", "credit_notes", "payments")}})
    manifest = {"dataset": "seshna-synthetic-trading-distribution", "generator_version": GENERATOR_VERSION, "seed": seed,
                "classification": CLASSIFICATION, "synthetic": True, "base_date": BASE_DATE.isoformat(),
                "total_bytes": sum(e["bytes"] for e in entries), "files": entries}
    files["manifest.json"] = dumps(manifest).encode("utf-8")
    return files
