"""Anomaly detection on source data: every SIM code the intake side can raise."""
import sim_helpers as h


def _codes(rows, **kw):
    report, _ = h.run(rows=rows, **kw)
    return report, h.codes(report)


def test_clean_month_has_no_source_anomalies():
    report, codes = _codes(h.month_rows())
    assert not {"SIM-101", "SIM-103", "SIM-104", "SIM-105", "SIM-106", "SIM-107", "SIM-113", "SIM-114"} & set(codes)
    assert report["excluded"] == []


def test_date_outside_month_excluded():
    rows = h.month_rows()
    rows[5]["date"] = rows[6]["date"] = rows[7]["date"] = "2026-04-01"
    report, codes = _codes(rows)
    assert "SIM-107" in codes and report["excluded"] == ["intake:sales_invoice:SI-2"]
    assert all("SI-2" not in s["sourceId"] for s in report["steps"])


def test_missing_and_unknown_tax_code():
    rows = h.month_rows()
    rows[2]["tax_code"] = None
    rows[5]["tax_code"] = "VAT99"
    report, codes = _codes(rows, tax_codes={"VAT15", "ZERO"})
    found = [a for a in report["anomalies"] if a["code"] == "SIM-103"]
    assert {tuple(a["sourceIds"]) for a in found} == {("intake:sales_invoice:SI-1",), ("intake:sales_invoice:SI-2",)}


def test_unmapped_account_only_when_chart_given():
    rows = h.month_rows()
    rows[1]["account"] = "5999"
    _, codes = _codes(rows)
    assert "SIM-101" not in codes
    report, codes = _codes(rows, accounts={"5000", "4000"})
    assert next(a for a in report["anomalies"] if a["code"] == "SIM-101")["params"] == {"accounts": ["5999"]}


def test_negative_stock():
    rows = h.month_rows()
    rows[4]["qty"] = "12"
    report, codes = _codes(rows)
    a = next(a for a in report["anomalies"] if a["code"] == "SIM-104")
    assert a["sourceIds"] == ["intake:stock_out:DN-1"] and a["params"]["balance"] == "-2"


def test_duplicate_number_across_sheets_excluded():
    rows = h.month_rows() + [h.row(sheet="second", row=1, type="sales_invoice", number="SI-1",
                                   date="2026-03-06", party="CUS-1", item="ITM-A", qty="1", unit_price="5.00",
                                   tax_code="VAT15", vat="0.75")]
    report, codes = _codes(rows)
    assert "SIM-105" in codes and "intake:sales_invoice:SI-1" in report["excluded"]


def test_possible_duplicate_flagged_not_excluded():
    rows = h.month_rows()
    dup = [dict(r, row=100 + i, number="SI-1B") for i, r in enumerate(rows[2:4])]
    report, codes = _codes(rows + dup)
    a = next(a for a in report["anomalies"] if a["code"] == "SIM-106")
    assert a["sourceIds"] == ["intake:sales_invoice:SI-1", "intake:sales_invoice:SI-1B"]
    assert "intake:sales_invoice:SI-1B" not in report["excluded"]


def test_floats_and_bad_values_refused():
    rows = h.month_rows()
    rows[0]["qty"] = 10.0
    rows[8]["currency"] = "XYZ"
    rows[9]["date"] = "31/03/2026"
    report, codes = _codes(rows)
    bad = {s for a in report["anomalies"] if a["code"] == "SIM-114" for s in a["sourceIds"]}
    assert bad == {"intake:stock_in:GRN-1", "intake:payment_in:RC-1", "intake:payroll_run:PAY-2026-03"}
    assert bad <= set(report["excluded"])


def test_inconsistent_header_and_unknown_kind():
    rows = h.month_rows()
    rows[3]["party"] = "CUS-9"
    rows.append(h.row(row=50, type="loyalty_points", date="2026-03-03"))
    report, codes = _codes(rows)
    assert "SIM-115" in codes and "SIM-116" in codes
    assert "intake:sales_invoice:SI-1" in report["excluded"]


def test_unallocated_payment():
    rows = h.month_rows()
    rows[8]["against"] = "SI-404"
    _, codes = _codes(rows)
    assert "SIM-113" in codes


def test_document_total_rounding_flag():
    rows = h.month_rows()
    for r in rows[5:8]:
        r["doc_total"] = "0.36"  # owner's document total 0.36 against 0.30 + 0.05
    report, codes = _codes(rows)
    a = next(a for a in report["anomalies"] if a["code"] == "SIM-102" and a["params"].get("where"))
    assert a["params"]["differenceMinor"] == 1


def test_intake_quality_flags_carried():
    findings = [{"code": "PRE-603", "rows": [{"sheet": "month", "row": 3}]}]
    report, codes = _codes(h.month_rows(), findings=findings)
    a = next(a for a in report["anomalies"] if a["code"] == "SIM-112")
    assert a["sourceIds"] == ["intake:sales_invoice:SI-1"] and a["params"] == {"codes": ["PRE-603"]}
    step = next(s for s in report["steps"] if s["sourceId"] == "intake:sales_invoice:SI-1")
    assert [p["row"] for p in step["provenance"]] == ["3", "4"]
