"""Synthetic ERP-013 regressions; no official accounting-conformance claim.

Removing balance checks, report binding, role lookup, or the atomic journal must
make these behavioral tests fail. All source datasets are synthetic.
"""
import copy
import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, Inexact, localcontext

import pytest

from services.discovery.connectors.model import Budget
from services.discovery.connectors.tabular.connector import TabularConnector
from services.discovery.prevalidate import prevalidate
from change_engine.importer import ImportFailure, OpeningImporter, SQLiteImportBackend, from_tabular


def report(rows):
    """Use the real DSC-019 report producer with master-data required fields."""
    return prevalidate(rows, {"required": {"*": []}}).to_dict()


def batch(datasets=None, **changes):
    """Build a source-bound batch using the upstream prevalidation contract."""
    datasets = datasets if datasets is not None else {
        "Customer": [{"customer_code": "C1", "customer_name": "Synthetic buyer"}],
        "Account": [{"account_number": "1100", "account_type": "Receivable"},
                    {"account_number": "3000", "account_type": "Other"}],
        "TrialBalance": [
            {"account": "1100", "account_type": "Receivable", "debit": "0.1", "credit": "0"},
            {"account": "1100", "account_type": "Receivable", "debit": "0.2", "credit": "0"},
            {"account": "3000", "account_type": "Other", "debit": "0", "credit": "0.3"}],
        "AR": [{"customer": "C1", "amount": "0.3"}],
    }
    result = dict(tenant_id="tenant-a", company="Synthetic Trading", batch_id="opening-1",
                  posting_date="2026-01-01", currency="SAR", datasets=datasets,
                  prevalidation=report([r for rows in datasets.values() for r in rows]))
    result.update(changes)
    return result


@pytest.fixture
def backend():
    """Trusted server session; roles are never an importer request argument."""
    store = SQLiteImportBackend(session=lambda: {
        "user_id": "reviewer", "human": True, "tenant_id": "tenant-a",
        "companies": ["Synthetic Trading"], "roles": ["Accounts Manager"]})
    yield store
    store.close()


def apply(importer, source):
    preview = importer.preview(source)
    assert preview["ok"], preview
    return importer.apply(source, confirmed_by="reviewer", plan_hash=preview["plan_hash"])


def refuses(importer, source, code):
    validation = importer.validate(source)
    assert not validation["ok"]
    assert code in {e["code"] for e in validation["errors"]}
    assert not importer.preview(source)["ok"]
    with pytest.raises(ImportFailure) as exc:
        importer.apply(source, confirmed_by="reviewer", plan_hash="0" * 64)
    assert exc.value.code == code


def test_exact_balance_preview_and_idempotent_apply(backend):
    importer, source = OpeningImporter(backend), batch()
    preview = importer.preview(source)
    assert Decimal(preview["totals"]["debit"]) == Decimal("0.3")
    assert preview["totals"]["debit"] == preview["totals"]["credit"]
    assert preview["reconciliations"]["ar"] is True
    assert len(preview["plan_hash"]) == 64
    assert apply(importer, source)["status"] == "applied"
    before = backend.records("tenant-a", "Synthetic Trading")
    assert apply(OpeningImporter(backend), source)["status"] == "already_applied"
    assert backend.records("tenant-a", "Synthetic Trading") == before


@pytest.mark.parametrize("value", [0.1, True, "NaN", "Infinity", "-Infinity", "-0.01", "1e999999", "1_000"])
def test_invalid_amounts_fail_closed(backend, value):
    source = batch()
    source["datasets"]["TrialBalance"][0]["debit"] = value
    refuses(OpeningImporter(backend), source, "IMP-NUMBER")


def test_one_cent_imbalance_and_context_independent_decimal(backend):
    source = batch()
    source["datasets"]["TrialBalance"][2]["credit"] = "0.31"
    refuses(OpeningImporter(backend), source, "IMP-BALANCE")
    with localcontext() as ctx:
        ctx.prec = 2
        assert OpeningImporter(backend).preview(batch())["ok"]


@pytest.mark.parametrize("kind", ["AR", "AP", "Stock"])
def test_subledger_and_stock_reconciliation(backend, kind):
    field, control, amount = {"AR": ("customer", "Receivable", "1.01"),
                              "AP": ("supplier", "Payable", "1.01"),
                              "Stock": ("item_code", "Stock", "1.01")}[kind]
    side, other = ("credit", "debit") if kind == "AP" else ("debit", "credit")
    line = {field: "KEY", "amount": amount} if kind != "Stock" else {
        "item_code": "KEY", "warehouse": "W1", "qty": "1", "valuation_rate": "1.005"}
    source = batch({"TrialBalance": [dict(account="control", account_type=control, **{side: amount, other: "0"}),
                                    dict(account="offset", account_type="Other", **{side: "0", other: amount})],
                    kind: [line],
                    "Account": [{"account_number": "control", "account_type": control},
                                {"account_number": "offset", "account_type": "Other"}],
                    "Customer": [{"customer_code": "KEY"}], "Supplier": [{"supplier_code": "KEY"}],
                    "Item": [{"item_code": "KEY"}], "Warehouse": [{"warehouse_name": "W1"}]})
    importer = OpeningImporter(backend)
    assert importer.preview(source)["reconciliations"][kind.lower()] is True
    apply(importer, source)
    assert Decimal(importer.preview(source)["totals"][kind.lower()] ) == Decimal(amount)
    source["datasets"][kind][0]["amount" if kind != "Stock" else "valuation_rate"] = "1.02"
    refuses(importer, source, "IMP-RECONCILE")


@pytest.mark.parametrize("kind,field,value", [("Stock", "qty", "0"), ("Stock", "valuation_rate", "-1"),
                                               ("AR", "amount", "-1"), ("AP", "amount", "-1")])
def test_opening_signs(backend, kind, field, value):
    row = {"item_code": "I1", "warehouse": "W1", "qty": "1", "valuation_rate": "1"} if kind == "Stock" else {
        "customer" if kind == "AR" else "supplier": "P1", "amount": "1"}
    row[field] = value
    refuses(OpeningImporter(backend), batch({kind: [row]}), "IMP-NUMBER")


def test_quarantine_duplicate_owner_review_and_stale_report(backend):
    importer = OpeningImporter(backend)
    source = batch({"Customer": [{"customer_name": "Buyer"}, {"customer_name": "Buyer"}]})
    assert source["prevalidation"]["quarantine"]
    refuses(importer, source, "IMP-REPORT")
    source = batch({"Customer": [{"customer_name": "مؤسسة النور"}, {"customer_name": "النور مؤسسة"}]})
    source["prevalidation"] = prevalidate(source["datasets"]["Customer"], {
        "required": {"*": []}, "fields": {"party": "customer_name"}}).to_dict()
    assert source["prevalidation"]["name_groups"]["party"]
    refuses(importer, source, "IMP-REPORT")
    for bad_report in (None, {}, '{"version":1}', batch()["prevalidation"]):
        refuses(importer, batch({"Customer": [{"customer_name": "Different"}]}, prevalidation=bad_report), "IMP-REPORT")


@pytest.mark.parametrize("payload", ["=CMD|' /C calc'!A0", "+1+1", "-text", "@SUM(1)", "\ttext", "\rtext", "  =SUM(1)"])
def test_formula_text_rejected_without_echo(backend, payload):
    source = batch({"Customer": [{"customer_name": payload}]})
    refuses(OpeningImporter(backend), source, "IMP-FORMULA")
    assert payload not in json.dumps(OpeningImporter(backend).preview(source))


def test_default_deny_caps_dates_currency_and_duplicate_keys(backend):
    importer = OpeningImporter(backend)
    refuses(importer, batch({"Customer": [{"customer_name": "Buyer", "roles": "System Manager"}]}), "IMP-SCHEMA")
    refuses(OpeningImporter(backend, max_rows=1), batch(), "IMP-LIMIT")
    refuses(importer, batch({"Customer": [{"customer_name": "x" * 1025}]}), "IMP-LIMIT")
    refuses(importer, batch(posting_date="2026-02-30"), "IMP-SCHEMA")
    source = batch()
    source["datasets"]["AR"][0]["currency"] = "USD"
    refuses(importer, source, "IMP-SCHEMA")
    source = batch({"Customer": [{"customer_code": "C1", "customer_name": "One"},
                                 {"customer_code": "C1", "customer_name": "Two"}]})
    refuses(importer, source, "IMP-DUPLICATE")


@pytest.mark.parametrize("session", [None, {"roles": ["System Manager"]},
    {"user_id": "reviewer", "human": False, "tenant_id": "tenant-a", "companies": ["Synthetic Trading"], "roles": ["System Manager"]},
    *[{"user_id": "reviewer", "human": True, "tenant_id": "tenant-a", "companies": ["Synthetic Trading"], "roles": [r]}
      for r in ("HR", "Sales", "Guest")],
    {"user_id": "reviewer", "human": True, "tenant_id": "tenant-b", "companies": ["Synthetic Trading"], "roles": ["System Manager"]}])
def test_backend_authentication_and_tenant_scope(session):
    with SQLiteImportBackend(session=lambda: session) as store:
        importer, source = OpeningImporter(store), batch()
        with pytest.raises(ImportFailure, match="IMP-AUTH"):
            importer.apply(source, confirmed_by="reviewer", plan_hash="0" * 64)
        assert store.records("tenant-a", "Synthetic Trading") == []


def test_confirmation_hash_binding_conflict_and_master_upsert(backend):
    importer, source = OpeningImporter(backend), batch({"Customer": [{"customer_code": "C1", "customer_name": "One"}]})
    preview = importer.preview(source)
    for confirmation in ({}, {"confirmed_by": "other", "plan_hash": preview["plan_hash"]},
                         {"confirmed_by": "reviewer", "plan_hash": "0" * 64}):
        with pytest.raises(ImportFailure, match="IMP-CONFIRM"):
            importer.apply(source, **confirmation)
    for key, val in (("tenant_id", "tenant-b"), ("company", "Other")):
        refuses(importer, dict(source, **{key: val}), "IMP-AUTH")
    for key, val in (("batch_id", "other"), ("posting_date", "2026-01-02"), ("currency_precision", 3)):
        assert importer.preview(dict(source, **{key: val}))["plan_hash"] != preview["plan_hash"]
    apply(importer, source)
    mutated = batch({"Customer": [{"customer_code": "C1", "customer_name": "Two"}]})
    with pytest.raises(ImportFailure, match="IMP-CONFLICT"):
        apply(importer, mutated)
    mutated["batch_id"] = "opening-2"
    apply(importer, mutated)
    records = backend.records("tenant-a", "Synthetic Trading")
    assert len(records) == 1 and records[0]["row"]["customer_name"] == "Two"


def test_rollback_preserves_prior_records_and_retry(backend):
    importer = OpeningImporter(backend)
    apply(importer, batch({"Customer": [{"customer_code": "C1", "customer_name": "Before"}]}))
    before = backend.records("tenant-a", "Synthetic Trading")
    source = batch({"Customer": [{"customer_code": "C1", "customer_name": "After"}],
                    "Supplier": [{"supplier_name": "Synthetic vendor"}]}, batch_id="failure")
    original = backend.write
    writes = []

    def failing_write(*args):
        original(*args)
        writes.append(args)
        if len(writes) == 2:
            raise RuntimeError("private backend failure")

    backend.write = failing_write
    with pytest.raises(ImportFailure, match="IMP-WRITE"):
        apply(importer, source)
    assert backend.records("tenant-a", "Synthetic Trading") == before
    assert backend.journal("tenant-a", "failure") is None
    assert backend.failures("tenant-a")[0]["code"] == "IMP-WRITE"
    backend.write = original
    assert apply(importer, source)["status"] == "applied"


def test_durable_journal_restart_and_competing_connections(tmp_path):
    path = str(tmp_path / "import.db")
    session = lambda: {"user_id": "reviewer", "human": True, "tenant_id": "tenant-a",
                       "companies": ["Synthetic Trading"], "roles": ["System Manager"]}
    with SQLiteImportBackend(path, session=session) as store:
        apply(OpeningImporter(store), batch())
    with SQLiteImportBackend(path, session=session) as store:
        assert apply(OpeningImporter(store), batch())["status"] == "already_applied"
    source = batch({"Customer": [{"customer_code": "C2", "customer_name": "Different buyer"}]}, batch_id="competing")

    def competing(_):
        with SQLiteImportBackend(path, session=session) as store:
            return apply(OpeningImporter(store), source)["status"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(competing, range(2))) == ["already_applied", "applied"]


def test_all_masters_and_scope_isolation(backend):
    data = {"Customer": [{"customer_name": "Buyer"}], "Supplier": [{"supplier_name": "Vendor"}],
            "Item": [{"item_code": "I1", "item_name": "Item"}], "Warehouse": [{"warehouse_name": "W1"}],
            "Account": [{"account_number": "1000", "account_name": "Cash", "account_type": "Other"}]}
    importer = OpeningImporter(backend)
    apply(importer, batch(data))
    apply(importer, batch(data, batch_id="again"))
    assert len(backend.records("tenant-a", "Synthetic Trading")) == 5
    assert backend.records("tenant-b", "Synthetic Trading") == []
    assert backend.records("tenant-a", "Other") == []


def test_real_csv_and_xlsx_connector_output_and_report_json(backend):
    connector = TabularConnector()
    csv = b"customer_code,customer_name\nC1,Synthetic buyer\n"
    sheets = [connector.extract(csv, Budget(10000))[0]]
    # Minimal actual OOXML workbook; the real DSC-011 parser reads this ZIP.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Master" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>customer_code</t></is></c><c r="B1" t="inlineStr"><is><t>customer_name</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>C1</t></is></c><c r="B2" t="inlineStr"><is><t>Synthetic buyer</t></is></c></row></sheetData></worksheet>')
    sheets.append(next(s for s in connector.extract(buf.getvalue(), Budget(10000)) if s["type"] == "sheet"))
    for i, sheet in enumerate(sheets):
        rows = from_tabular(sheet, {"customer_code": "customer_code", "customer_name": "customer_name"})
        assert rows == [{"customer_code": "C1", "customer_name": "Synthetic buyer"}]
        source = batch({"Customer": rows}, batch_id=f"tabular-{i}")
        source["prevalidation"] = json.dumps(source["prevalidation"])
        apply(OpeningImporter(backend), source)
        bad = copy.deepcopy(sheet)
        bad["cells"][-1]["formula"] = True
        with pytest.raises(ImportFailure, match="IMP-FORMULA"):
            from_tabular(bad, {"customer_code": "customer_code", "customer_name": "customer_name"})
        with pytest.raises(ImportFailure, match="IMP-SCHEMA"):
            from_tabular(sheet, {"customer_code": "customer_code"})


def test_engine_invisibility_in_every_emitted_error_and_report(backend):
    from change_engine.importer.errors import MESSAGES
    for code in MESSAGES:
        payload = ImportFailure(code).to_dict()
        assert payload["ar_review"] == "unreviewed_arabic"
        assert payload["messages"]["ar"] and payload["messages"]["en"]
        assert not any(name in json.dumps(payload).lower() for name in ("frappe", "erpnext"))
    source = batch({"Customer": [{"customer_name": "Frappe ERPNext"}]})
    assert not any(name in json.dumps(OpeningImporter(backend).preview(source)).lower() for name in ("frappe", "erpnext"))


@pytest.mark.parametrize("hash_value", [None, "", "ع" * 64, "Z" * 64, 7])
def test_malformed_confirmation_hash_is_a_domain_error(backend, hash_value):
    with pytest.raises(ImportFailure, match="IMP-CONFIRM"):
        OpeningImporter(backend).apply(batch(), confirmed_by="reviewer", plan_hash=hash_value)


@pytest.mark.parametrize("change", [
    lambda r: r.update(version=2),
    lambda r: r.update(errors=["failed"]),
    lambda r: r["summary"].update(quarantined=1),
    lambda r: r["summary"].update(rows=True),
    lambda r: r.update(owner_review=[{"sheet": None, "row": 1}]),
    lambda r: r.update(findings=[{"code": "PRE-801", "severity": "info", "quarantined": False}]),
    lambda r: r.update(name_groups={"party": [{"confirmed": True}], "item": []}),
])
def test_malformed_or_forged_report_cannot_enable_apply(backend, change):
    source = batch()
    change(source["prevalidation"])
    refuses(OpeningImporter(backend), source, "IMP-REPORT")


def test_report_is_bound_to_plan_and_wrapped_datasets(backend):
    source = batch({"Customer": [{"customer_name": "Synthetic buyer"}]})
    importer = OpeningImporter(backend)
    before = copy.deepcopy(source)
    result = importer.preview(source)
    assert source == before
    source["datasets"]["Customer"] = {"rows": source["datasets"]["Customer"], "sheet": "csv"}
    assert importer.preview(source)["plan_hash"] == result["plan_hash"]
    apply(importer, source)


def test_separate_tenants_and_companies_have_independent_masters(tmp_path):
    session = {"user_id": "reviewer", "human": True, "tenant_id": "tenant-a",
               "companies": ["Synthetic Trading"], "roles": ["System Manager"]}
    with SQLiteImportBackend(str(tmp_path / "scope.db"), session=lambda: session) as store:
        importer = OpeningImporter(store)
        source = batch({"Customer": [{"customer_name": "Buyer"}]})
        apply(importer, source)
        session["tenant_id"] = "tenant-b"
        apply(importer, dict(source, tenant_id="tenant-b"))
        session["companies"] = ["Other"]
        apply(importer, dict(source, tenant_id="tenant-b", company="Other", batch_id="other-company"))
        for tenant, company in (("tenant-a", "Synthetic Trading"), ("tenant-b", "Synthetic Trading"), ("tenant-b", "Other")):
            assert len(store.records(tenant, company)) == 1


def test_failure_after_journal_insert_rolls_back_everything(backend):
    original = backend.commit_batch

    def failure_after_insert(*args):
        original(*args)
        raise RuntimeError("private engine error")

    backend.commit_batch = failure_after_insert
    with pytest.raises(ImportFailure, match="IMP-WRITE"):
        apply(OpeningImporter(backend), batch())
    assert backend.records("tenant-a", "Synthetic Trading") == []
    assert backend.journal("tenant-a", "opening-1") is None
    assert len(backend.failures("tenant-a")) == 1


def test_auth_lookup_failure_and_company_scope_fail_closed(backend):
    def broken_session():
        raise RuntimeError("private session failure")

    backend._session = broken_session
    refuses(OpeningImporter(backend), batch(), "IMP-AUTH")
    backend._session = lambda: {"user_id": "reviewer", "human": True, "tenant_id": "tenant-a",
                                "companies": ["Different"], "roles": ["System Manager"]}
    refuses(OpeningImporter(backend), batch(), "IMP-AUTH")


def test_multicurrency_and_inconsistent_control_classification_rejected(backend):
    source = batch()
    source["datasets"]["TrialBalance"][1]["currency"] = "USD"
    refuses(OpeningImporter(backend), source, "IMP-SCHEMA")
    source = batch()
    source["datasets"]["TrialBalance"][1]["account_type"] = "Other"
    refuses(OpeningImporter(backend), source, "IMP-REFERENCE")


def test_large_exact_arithmetic_and_rounding_at_configured_precision(backend):
    source = batch({"TrialBalance": [
        {"account": "1", "account_type": "Other", "debit": "12345678901234567890.123456789", "credit": "0"},
        {"account": "2", "account_type": "Other", "debit": "0", "credit": "12345678901234567890.123456789"}],
        "Stock": [{"item_code": "I1", "warehouse": "W1", "qty": "3", "valuation_rate": "0.0005"}],
        "Account": [{"account_number": "1", "account_type": "Other"}, {"account_number": "2", "account_type": "Other"},
                    {"account_number": "stock", "account_type": "Stock"}, {"account_number": "offset", "account_type": "Other"}],
        "Item": [{"item_code": "I1"}], "Warehouse": [{"warehouse_name": "W1"}]}, currency_precision=3)
    source["datasets"]["TrialBalance"] += [
        {"account": "stock", "account_type": "Stock", "debit": "0.002", "credit": "0"},
        {"account": "offset", "account_type": "Other", "debit": "0", "credit": "0.002"}]
    source["prevalidation"] = report([r for rows in source["datasets"].values() for r in rows])
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.Emax = 2
        ctx.traps[Inexact] = True
        result = OpeningImporter(backend).preview(source)
    assert result["ok"]
    assert result["totals"]["debit"] == "12345678901234567890.125456789"
    assert result["totals"]["stock"] == "0.002"


def test_forged_information_finding_cannot_downgrade_upstream_blocker(backend):
    source = batch()
    source["prevalidation"]["findings"] = [{"code": "PRE-801", "severity": "info", "quarantined": False}]
    source["prevalidation"]["counts"] = {"PRE-801": 1}
    source["prevalidation"]["summary"]["findings"] = 1
    refuses(OpeningImporter(backend), source, "IMP-REPORT")


def test_malformed_group_collections_are_not_clean_reports(backend):
    source = batch()
    source["prevalidation"]["name_groups"] = {"party": None, "item": 0}
    refuses(OpeningImporter(backend), source, "IMP-REPORT")


def test_report_blocker_counts_are_visible_without_source_text(backend):
    source = batch({"Customer": [{"customer_name": "Buyer"}, {"customer_name": "Buyer"}]})
    error = OpeningImporter(backend).preview(source)["errors"][0]
    assert error["report_counts"]["quarantined"] == 1
    assert "Buyer" not in json.dumps(error)


def test_master_writes_precede_opening_details(backend):
    order, original = [], backend.write

    def capture_order(*args):
        order.append(args[2])
        original(*args)

    backend.write = capture_order
    apply(OpeningImporter(backend), batch())
    assert order.index("Customer") < order.index("AR")
    assert order.index("Customer") < order.index("TrialBalance")
