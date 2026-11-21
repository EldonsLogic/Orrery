"""Round 6 PR #202 review regressions: strict key/link/metadata text hygiene (ERP-013, Tier 3)."""
import copy

import pytest

from change_engine.importer import OpeningImporter, SQLiteImportBackend
from change_engine.tests.test_erp_013_opening_importer import apply, backend, batch, refuses
from change_engine.tests.test_erp_013_review_fixes import opening_details


def _probe_value(base: str, kind: str) -> str:
    if kind == "trailing_space":
        return f"{base} "
    if kind == "leading_space":
        return f" {base}"
    if kind == "nbsp":
        return f"{base}\u00a0"
    if kind == "internal_nbsp":
        return f"{base[0]}\u00a0{base[1:]}"
    if kind == "cgj":
        return f"{base}\u034f"
    if kind == "vs16":
        return f"{base}\ufe0f"
    if kind == "hangul_filler":
        return f"{base}\u3164"
    if kind == "fullwidth":
        return "".join(chr(ord(ch) + 0xFEE0) if 0x21 <= ord(ch) <= 0x7E else ch for ch in base)
    raise ValueError(kind)


PROBES = (
    "trailing_space",
    "leading_space",
    "nbsp",
    "internal_nbsp",
    "cgj",
    "vs16",
    "hangul_filler",
    "fullwidth",
)


@pytest.mark.parametrize("probe", PROBES)
def test_customer_code_refuses_whitespace_ignorable_and_non_nfkc(backend, probe):
    importer = OpeningImporter(backend)
    twin = _probe_value("C1", probe)
    datasets = {
        "Account": [
            {"account_number": "1100", "account_type": "Receivable"},
            {"account_number": "3000", "account_type": "Other"},
        ],
        "TrialBalance": [
            {"account": "1100", "account_type": "Receivable", "debit": "100.00", "credit": "0"},
            {"account": "3000", "account_type": "Other", "debit": "0", "credit": "100.00"},
        ],
        "Customer": [
            {"customer_code": "C1", "customer_name": "Alpha"},
            {"customer_code": twin, "customer_name": "Beta"},
        ],
        "AR": [
            {"customer": "C1", "account": "1100", "amount": "40.00"},
            {"customer": twin, "account": "1100", "amount": "60.00"},
        ],
    }
    refuses(importer, batch(datasets), "IMP-SCHEMA")
    assert backend.records("tenant-a", "Synthetic Trading") == []


@pytest.mark.parametrize("probe", PROBES)
def test_account_number_refuses_whitespace_ignorable_and_non_nfkc(backend, probe):
    importer = OpeningImporter(backend)
    twin = _probe_value("1100", probe)
    datasets = {
        "Account": [
            {"account_number": "1100", "account_type": "Other"},
            {"account_number": twin, "account_type": "Other"},
        ],
        "TrialBalance": [
            {"account": "1100", "account_type": "Other", "debit": "10.00", "credit": "0"},
            {"account": twin, "account_type": "Other", "debit": "0", "credit": "10.00"},
        ],
    }
    refuses(importer, batch(datasets), "IMP-SCHEMA")
    assert backend.records("tenant-a", "Synthetic Trading") == []


@pytest.mark.parametrize("probe", PROBES)
@pytest.mark.parametrize("entity,field,base", [
    ("TrialBalance", "account", "ar"),
    ("AR", "customer", "C1"),
    ("AR", "account", "ar"),
    ("AP", "supplier", "S1"),
    ("Stock", "item_code", "I1"),
    ("Stock", "warehouse", "W1"),
])
def test_opening_link_fields_refuse_whitespace_ignorable_and_non_nfkc(backend, probe, entity, field, base):
    importer = OpeningImporter(backend)
    datasets = opening_details()
    datasets[entity][0][field] = _probe_value(base, probe)
    refuses(importer, batch(datasets), "IMP-SCHEMA")


@pytest.mark.parametrize("probe", PROBES)
def test_batch_id_refuses_whitespace_ignorable_and_non_nfkc(backend, probe):
    importer = OpeningImporter(backend)
    refuses(importer, batch(batch_id=_probe_value("opening-1", probe)), "IMP-SCHEMA")


@pytest.mark.parametrize("probe", ("trailing_space", "leading_space", "nbsp", "cgj", "vs16", "hangul_filler", "fullwidth"))
def test_company_and_currency_metadata_refuse_strict_probes(monkeypatch, probe):
    monkeypatch.setenv("CHANGE_ENGINE_ENV", "test")
    bad_company = _probe_value("Synthetic Trading", probe)
    session = lambda: {
        "user_id": "reviewer", "human": True, "tenant_id": "tenant-a",
        "companies": ["Synthetic Trading", bad_company], "roles": ["Accounts Manager"],
    }
    with SQLiteImportBackend(
        session=session,
        company_currencies={
            ("tenant-a", "Synthetic Trading"): "SAR",
            ("tenant-a", bad_company): "SAR",
        },
    ) as store:
        importer = OpeningImporter(store)
        refuses(importer, batch(company=bad_company), "IMP-SCHEMA")
        refuses(importer, batch(currency=_probe_value("SAR", probe)), "IMP-SCHEMA")


@pytest.mark.parametrize("entity,row_base,field,base", [
    ("Customer", {"customer_code": "C1"}, "customer_group", "Commercial"),
    ("Customer", {"customer_code": "C1"}, "territory", "Riyadh"),
    ("Supplier", {"supplier_code": "S1"}, "supplier_group", "Local"),
    ("Item", {"item_code": "I1"}, "item_group", "Products"),
    ("Item", {"item_code": "I1"}, "stock_uom", "Nos"),
    ("Warehouse", {"warehouse_name": "W1"}, "parent_warehouse", "All"),
    ("Account", {"account_number": "1100", "account_type": "Other"}, "parent_account", "Assets"),
])
@pytest.mark.parametrize("probe", (*PROBES, "rlm", "lrm", "alm"))
def test_master_link_fields_refuse_format_marks_whitespace_ignorable_and_non_nfkc(
    backend, entity, row_base, field, base, probe
):
    importer = OpeningImporter(backend)
    if probe in ("rlm", "lrm", "alm"):
        bad = base + {"rlm": "\u200f", "lrm": "\u200e", "alm": "\u061c"}[probe]
    else:
        bad = _probe_value(base, probe)
    row = dict(row_base, **{field: bad})
    refuses(importer, batch({entity: [row]}), "IMP-SCHEMA")


def test_ordinary_ascii_codes_clean_links_and_arabic_names_still_pass(backend):
    importer = OpeningImporter(backend)
    datasets = {
        "Customer": [{
            "customer_code": "CUST-01",
            "customer_name": "\u200fشركة النور\u200e للتجارة",
            "customer_group": "All Customer Groups",
            "territory": "الرياض",
        }],
        "Supplier": [{
            "supplier_code": "SUP-01",
            "supplier_name": "\u061cمورد الخليج",
            "supplier_group": "موردون محليون",
        }],
        "Item": [{
            "item_code": "SKU-100",
            "item_name": "صنف\u200c قياسي",
            "item_group": "البضائع",
            "stock_uom": "Nos",
        }],
        "Warehouse": [{"warehouse_name": "المستودع الرئيسي"}],
        "Account": [
            {"account_number": "1100", "account_name": "الذمم المدينة", "account_type": "Receivable"},
            {"account_number": "3000", "account_name": "رأس المال", "account_type": "Other"},
        ],
        "TrialBalance": [
            {"account": "1100", "account_type": "Receivable", "debit": "100.00", "credit": "0"},
            {"account": "3000", "account_type": "Other", "debit": "0", "credit": "100.00"},
        ],
        "AR": [{"customer": "CUST-01", "account": "1100", "amount": "100.00"}],
    }
    source = batch(datasets)
    assert apply(importer, source)["status"] == "applied"
    stored = {r["entity"]: r["row"] for r in backend.records("tenant-a", "Synthetic Trading")
              if r["entity"] in ("Customer", "Supplier", "Item")}
    assert stored["Customer"]["customer_name"] == "\u200fشركة النور\u200e للتجارة"
    assert stored["Customer"]["territory"] == "الرياض"
    assert stored["Supplier"]["supplier_name"] == "\u061cمورد الخليج"
    assert stored["Item"]["item_name"] == "صنف\u200c قياسي"
    # Formula prefixes on strict fields still return IMP-FORMULA, not IMP-SCHEMA.
    refuses(importer, batch({"Customer": [{"customer_code": " =SUM(1)"}]}), "IMP-FORMULA")
    refuses(importer, batch({"Customer": [{"customer_code": "＝1+1"}]}), "IMP-FORMULA")
    # Name-only masters differing only by a format mark still collide as IMP-DUPLICATE.
    refuses(importer, batch({"Customer": [
        {"customer_name": "شركة الفجر"},
        {"customer_name": "شركة الفجر\u200f"},
    ]}), "IMP-DUPLICATE")


@pytest.mark.parametrize("twin", [
    "W1 ",
    "W1\u00a0",
    "W1\u3164",
    "\uff37\uff11",
    "W1\u034f",
])
def test_warehouse_name_refuses_whitespace_ignorable_and_non_nfkc_twins(backend, twin):
    importer = OpeningImporter(backend)
    datasets = {
        "Warehouse": [
            {"warehouse_name": "W1"},
            {"warehouse_name": twin},
        ],
    }
    refuses(importer, batch(datasets), "IMP-SCHEMA")
    assert backend.records("tenant-a", "Synthetic Trading") == []


@pytest.mark.parametrize("warehouse_name", [
    "Main Warehouse 01",
    "المستودع الرئيسي",
])
def test_warehouse_name_accepts_ordinary_ascii_and_clean_arabic(backend, warehouse_name):
    importer = OpeningImporter(backend)
    datasets = {
        "Account": [
            {"account_number": "1300", "account_type": "Stock"},
            {"account_number": "3000", "account_type": "Other"},
        ],
        "TrialBalance": [
            {"account": "1300", "account_type": "Stock", "debit": "100.00", "credit": "0"},
            {"account": "3000", "account_type": "Other", "debit": "0", "credit": "100.00"},
        ],
        "Item": [{"item_code": "I1"}],
        "Warehouse": [{"warehouse_name": warehouse_name}],
        "Stock": [{"item_code": "I1", "warehouse": warehouse_name, "qty": "1", "valuation_rate": "100.00"}],
    }
    source = batch(datasets)
    assert importer.preview(source)["ok"]
    assert apply(importer, source)["status"] == "applied"
    stored = [r["row"] for r in backend.records("tenant-a", "Synthetic Trading") if r["entity"] == "Warehouse"]
    assert stored == [{"warehouse_name": warehouse_name}]
