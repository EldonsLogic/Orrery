"""Adversarial PR #202 regressions against real validation and SQLite transactions."""
import copy
from concurrent.futures import ThreadPoolExecutor

import pytest

from change_engine.importer import ImportFailure, OpeningImporter, SQLiteImportBackend
from change_engine.tests.test_erp_013_opening_importer import apply, backend, batch, refuses


def forged_clean(source):
    """Forge an internally consistent DSC-019 report, without running its checks."""
    rows = [r for dataset in source["datasets"].values() for r in dataset]
    source["prevalidation"] = {
        "version": 1, "accepted": copy.deepcopy(rows), "quarantine": [], "owner_review": [],
        "findings": [], "counts": {}, "name_groups": {"party": [], "item": []},
        "summary": {"rows": len(rows), "accepted": len(rows), "quarantined": 0,
                    "owner_review": 0, "findings": 0}}
    return source


@pytest.mark.parametrize("entity,field", [("Customer", "customer_name"), ("Supplier", "supplier_name"),
                                         ("Item", "item_name")])
def test_forged_clean_report_cannot_hide_arabic_near_duplicates(backend, entity, field):
    rows = [{field: "مؤسسة النور"}, {field: "النور مؤسسة"}]
    if entity == "Item":
        for i, row in enumerate(rows):
            row["item_code"] = f"I{i}"
    source = forged_clean(batch({entity: rows}))
    refuses(OpeningImporter(backend), source, "IMP-REPORT")
    assert backend.records("tenant-a", "Synthetic Trading") == []


def test_forged_clean_report_cannot_hide_hijri_or_invalid_dates(backend):
    source = forged_clean(batch({"Customer": [{"customer_name": "Buyer"}]}, posting_date="1447-01-01"))
    refuses(OpeningImporter(backend), source, "IMP-REPORT")
    source["posting_date"] = "2026-02-30"
    refuses(OpeningImporter(backend), source, "IMP-SCHEMA")


def test_second_batch_id_cannot_post_company_opening_again(backend):
    importer = OpeningImporter(backend)
    apply(importer, batch())
    before = backend.records("tenant-a", "Synthetic Trading")
    with pytest.raises(ImportFailure, match="IMP-OPENING-CONFLICT"):
        apply(importer, batch(batch_id="retry-new-id"))
    assert backend.records("tenant-a", "Synthetic Trading") == before
    assert backend.journal("tenant-a", "retry-new-id") is None


def test_different_batch_ids_compete_for_one_company_opening(tmp_path):
    session = lambda: {"user_id": "reviewer", "human": True, "tenant_id": "tenant-a",
                       "companies": ["Synthetic Trading"], "roles": ["Accounts Manager"]}
    path = str(tmp_path / "opening.db")
    with SQLiteImportBackend(path, session=session):
        pass

    def post(i):
        with SQLiteImportBackend(path, session=session) as store:
            try:
                return apply(OpeningImporter(store), batch(batch_id=f"opening-{i}"))["status"]
            except ImportFailure as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(post, range(2))) == ["IMP-OPENING-CONFLICT", "applied"]
    with SQLiteImportBackend(path, session=session) as store:
        assert len([r for r in store.records("tenant-a", "Synthetic Trading") if r["entity"] == "TrialBalance"]) == 3


def test_master_updates_show_count_and_keep_verbatim_prior_values(backend):
    old = {"customer_code": "C1", "customer_name": "  Before  ", "tax_id": "synthetic-old"}
    new = {"customer_code": "C1", "customer_name": "After", "tax_id": "synthetic-new"}
    importer = OpeningImporter(backend)
    apply(importer, batch({"Customer": [old]}))
    source = batch({"Customer": [new]}, batch_id="update")
    assert importer.preview(source)["master_updates"] == 1
    apply(importer, source)
    assert backend.journal("tenant-a", "update")["master_changes"] == [
        {"entity": "Customer", "key": '["customer_code","C1"]', "before": old, "after": new}]


def test_failed_master_update_restores_values_and_discards_audit(backend):
    old = {"customer_code": "C1", "customer_name": "  Before  ", "tax_id": "synthetic-old"}
    importer = OpeningImporter(backend)
    apply(importer, batch({"Customer": [old]}))
    before = backend.records("tenant-a", "Synthetic Trading")
    write = backend.write

    def fail_after_second_row(*args):
        write(*args)
        if args[2] == "Supplier":
            raise RuntimeError("later row failed")

    backend.write = fail_after_second_row
    source = batch({"Customer": [{"customer_code": "C1", "customer_name": "After"}],
                    "Supplier": [{"supplier_name": "Vendor"}]}, batch_id="failed-update")
    with pytest.raises(ImportFailure, match="IMP-WRITE"):
        apply(importer, source)
    assert backend.records("tenant-a", "Synthetic Trading") == before
    assert backend.journal("tenant-a", "failed-update") is None
    assert backend.conn.execute("SELECT count(*) FROM import_master_changes WHERE batch_id='failed-update'").fetchone()[0] == 0


def test_master_change_between_preview_and_apply_requires_new_approval(backend):
    importer = OpeningImporter(backend)
    source = batch({"Customer": [{"customer_code": "C1", "customer_name": "Proposed"}]})
    preview = importer.preview(source)
    apply(importer, batch({"Customer": [{"customer_code": "C1", "customer_name": "Concurrent"}]}, batch_id="other"))
    with pytest.raises(ImportFailure, match="IMP-CONFIRM"):
        importer.apply(source, confirmed_by="reviewer", plan_hash=preview["plan_hash"])
    assert backend.records("tenant-a", "Synthetic Trading")[0]["row"]["customer_name"] == "Concurrent"


@pytest.mark.parametrize("kind", ["AR", "AP", "Stock"])
def test_control_without_subledger_or_subledger_without_control_is_rejected(backend, kind):
    source = batch()
    if kind != "AR":
        source["datasets"][kind] = ([{"supplier": "S1", "amount": "0.3"}] if kind == "AP" else
                                    [{"item_code": "I1", "warehouse": "W1", "qty": "1", "valuation_rate": "0.3"}])
        source["datasets"]["Supplier"] = [{"supplier_code": "S1", "supplier_name": "Vendor"}]
        source["datasets"]["Item"] = [{"item_code": "I1"}]
        source["datasets"]["Warehouse"] = [{"warehouse_name": "W1"}]
        for row in source["datasets"]["TrialBalance"]:
            if row["account"] == "1100":
                row["account_type"] = "Payable" if kind == "AP" else "Stock"
                if kind == "AP":
                    row["debit"], row["credit"] = row["credit"], row["debit"]
            elif kind == "AP":
                row["debit"], row["credit"] = row["credit"], row["debit"]
        source["datasets"].pop("AR")
        source["datasets"]["Account"][0]["account_type"] = "Payable" if kind == "AP" else "Stock"
    no_details = copy.deepcopy(source)
    no_details["datasets"].pop(kind)
    for candidate in (no_details, dict(source, datasets={k: v for k, v in source["datasets"].items() if k != "TrialBalance"})):
        forged_clean(candidate)
        refuses(OpeningImporter(backend), candidate, "IMP-RECONCILE")


@pytest.mark.parametrize("entity,field", [("TrialBalance", "account"), ("AR", "customer"),
                                         ("AP", "supplier"), ("Stock", "item_code"), ("Stock", "warehouse")])
def test_unknown_detail_master_reference_fails_closed(backend, entity, field):
    source = batch()
    if entity == "AP":
        source["datasets"].update(Supplier=[{"supplier_code": "S1"}], AP=[{"supplier": "S1", "amount": "0"}])
    if entity == "Stock":
        source["datasets"].update(Item=[{"item_code": "I1"}], Warehouse=[{"warehouse_name": "W1"}],
                                  Stock=[{"item_code": "I1", "warehouse": "W1", "qty": "1", "valuation_rate": "0"}])
    source["datasets"][entity][0][field] = "GHOST"
    forged_clean(source)
    refuses(OpeningImporter(backend), source, "IMP-REFERENCE")


def test_existing_master_links_are_scoped_and_control_type_cannot_be_forged(backend):
    importer = OpeningImporter(backend)
    source = batch()
    masters = {k: source["datasets"].pop(k) for k in ("Account", "Customer")}
    apply(importer, batch(masters, batch_id="masters"))
    forged_clean(source)
    assert importer.preview(source)["ok"]
    for row in source["datasets"]["TrialBalance"]:
        row["account_type"] = "Other"
    source["datasets"].pop("AR")
    forged_clean(source)
    refuses(importer, source, "IMP-REFERENCE")
    backend._session = lambda: {"user_id": "reviewer", "human": True, "tenant_id": "tenant-a",
                               "companies": ["Other"], "roles": ["Accounts Manager"]}
    refuses(importer, dict(source, company="Other"), "IMP-REFERENCE")


@pytest.mark.parametrize("prefix", ["\u200b", "\ufeff", "\u200f", "\u202e", "\x7f", " \u200b  ", " "])
def test_unicode_formula_prefixes_are_blocked(backend, prefix):
    refuses(OpeningImporter(backend), batch({"Customer": [{"customer_name": prefix + "=CMD|payload"}]}), "IMP-FORMULA")


def test_fullwidth_formula_and_embedded_format_controls_are_rejected(backend):
    refuses(OpeningImporter(backend), batch({"Customer": [{"customer_name": "＝1+1"}]}), "IMP-FORMULA")
    refuses(OpeningImporter(backend), batch({"Customer": [{"customer_name": "Buyer\u200bhidden"}]}), "IMP-FORMULA")


def test_errors_fail_fast_with_truncation_indicator_and_no_cell_echo(backend):
    source = batch({"Customer": [{"customer_name": f"=private-{i}"} for i in range(5000)]}, prevalidation={})
    result = OpeningImporter(backend).validate(source)
    assert result["ok"] is False and len(result["errors"]) == 1
    assert result["errors_truncated"] is True
    assert "private" not in str(result)


@pytest.mark.parametrize("session", [None, {"user_id": "reviewer", "human": True, "tenant_id": "other",
    "companies": ["Synthetic Trading"], "roles": ["Accounts Manager"]}])
def test_all_stages_authenticate_before_reading_payload(session):
    class Unreadable(dict):
        def items(self):
            raise AssertionError("payload traversed before authorization")

    with SQLiteImportBackend(session=lambda: session) as store:
        source = Unreadable(batch())
        refuses(OpeningImporter(store), source, "IMP-AUTH")
        assert store.failures("tenant-a") == []


def test_failure_audit_is_bounded_per_tenant(backend):
    for i in range(300):
        backend.record_failure("tenant-a", f"failure-{i}", "0" * 64, "IMP-WRITE")
    assert len(backend.failures("tenant-a")) <= 256
    assert backend.failures("tenant-a")[-1]["batch_id"] == "failure-299"


def test_unknown_currency_is_rejected_and_configured_iso_subset_is_allowed(backend):
    refuses(OpeningImporter(backend), batch(currency="ZZZ"), "IMP-SCHEMA")
    for code in ("SAR", "AED", "EGP", "QAR", "USD", "EUR", "GBP"):
        source = batch({"Customer": [{"customer_name": "Buyer"}]}, currency=code)
        assert OpeningImporter(backend).preview(source)["ok"]


def test_generic_backend_import_capability_is_not_an_engine_role(backend):
    backend._session = lambda: {"user_id": "reviewer", "human": True, "tenant_id": "tenant-a",
                               "companies": ["Synthetic Trading"], "capabilities": ["opening_import"]}
    assert apply(OpeningImporter(backend), batch())["status"] == "applied"


def test_existing_control_master_cannot_be_reclassified_to_bypass_reconciliation(backend):
    source = batch()
    importer = OpeningImporter(backend)
    apply(importer, batch({"Account": source["datasets"]["Account"]}, batch_id="chart"))
    for row in source["datasets"]["TrialBalance"]:
        row["account_type"] = "Other"
    source["datasets"]["Account"][0]["account_type"] = "Other"
    source["datasets"].pop("AR")
    refuses(importer, forged_clean(source), "IMP-REFERENCE")


def test_offsetting_nonzero_control_lines_still_require_details(backend):
    source = batch({"Account": [{"account_number": "1100", "account_type": "Receivable"}],
                    "TrialBalance": [{"account": "1100", "account_type": "Receivable", "debit": "1", "credit": "0"},
                                     {"account": "1100", "account_type": "Receivable", "debit": "0", "credit": "1"}]})
    refuses(OpeningImporter(backend), source, "IMP-RECONCILE")


def test_upstream_findings_are_bounded_before_calling_accumulating_api(backend):
    source = batch({"Customer": [{"customer_code": f"C{i}"} for i in range(251)]})
    refuses(OpeningImporter(backend), source, "IMP-LIMIT")


def test_failed_opening_releases_claim_and_audit_for_retry(backend):
    commit = backend.commit_batch

    def fail_after_journal(*args):
        commit(*args)
        raise RuntimeError("after journal")

    backend.commit_batch = fail_after_journal
    importer, source = OpeningImporter(backend), batch()
    with pytest.raises(ImportFailure, match="IMP-WRITE"):
        apply(importer, source)
    assert backend.conn.execute("SELECT count(*) FROM import_master_changes").fetchone()[0] == 0
    assert backend.conn.execute("SELECT count(*) FROM import_openings").fetchone()[0] == 0
    backend.commit_batch = commit
    assert apply(importer, source)["status"] == "applied"


def test_legacy_opening_records_block_new_batch_even_without_claim(backend):
    with backend.transaction():
        backend.write("tenant-a", "Synthetic Trading", "TrialBalance", "legacy", {"account": "old"})
    with pytest.raises(ImportFailure, match="IMP-OPENING-CONFLICT"):
        apply(OpeningImporter(backend), batch())
    assert backend.journal("tenant-a", "opening-1") is None


def test_opening_guard_is_independent_per_tenant_and_company(backend):
    importer, source = OpeningImporter(backend), batch()
    apply(importer, source)
    backend._session = lambda: {"user_id": "reviewer", "human": True, "tenant_id": "tenant-b",
                               "companies": ["Synthetic Trading", "Other"], "roles": ["Accounts Manager"]}
    apply(importer, dict(source, tenant_id="tenant-b"))
    apply(importer, dict(source, tenant_id="tenant-b", company="Other", batch_id="other-company"))
    assert backend.conn.execute("SELECT count(*) FROM import_openings").fetchone()[0] == 3


def test_backend_read_failure_is_sanitized_and_fails_closed(backend):
    backend.close()
    refuses(OpeningImporter(backend), batch(), "IMP-WRITE")


def test_long_name_comparison_work_is_bounded_before_upstream(backend):
    source = batch({"Customer": [{"customer_name": "X" * 1020 + suffix} for suffix in ("a", "b", "c")]})
    refuses(OpeningImporter(backend), forged_clean(source), "IMP-LIMIT")
