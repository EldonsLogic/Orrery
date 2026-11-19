"""PR #191 review fixes: engine record ids, in-doubt, sanitising, tolerance, Decimal, stock, aging, verdict."""
import datetime as dt
import json
from decimal import Decimal
from fractions import Fraction

import pytest

import sim_helpers as h
from simulator import SimulatorError, validate_report
from simulator.aging import aging_bucket
from simulator.compare import ToleranceError, allowed_minor, check_tolerances, expected_totals
from simulator.anomalies import replay_order
from simulator.model import normalise
from simulator.money import MoneyError, fmt, parse_decimal, to_minor
from simulator.plan import _value
from simulator.runner import ToolCall
from simulator.valuation import StockBook

POSTING = dict(ts=None)


def _post_ts():
    return h.tool_set(ledger_post="R2")


# ---- MED 1: payments reference the engine record id -------------------------------------------------------------
def test_payment_against_is_engine_record_id():
    report, port = h.run(ts=_post_ts())
    pay = next(d for d in port.docs.values() if d["kind"] == "payment_in")
    si1 = next(s for s in report["steps"] if s["stepId"] == "intake:sales_invoice:SI-1#create")
    assert pay["against"] == si1["recordId"] and pay["against"] != "SI-1"
    assert h.metric(report, "receivables_0_30")["status"] == "within_tolerance"


def test_port_rejects_unknown_reference():
    p = h.port()
    r = p.execute(ToolCall(h.TENANT, dict(h.CALLER), "payment.create",
                           {"direction": "receive", "against": "SI-1", "amount": {"currency": "SAR", "value": "1.00"}},
                           "k1"))
    assert r["status"] == "error" and r["error"]["code"] == "unknown_reference"


def test_payment_before_invoice_is_flagged_and_unallocated():
    rows = h.month_rows()
    rows[8]["date"] = "2026-03-04"  # SI-1 is dated 2026-03-05
    report, _ = h.run(rows=rows, ts=_post_ts())
    assert "SIM-127" in h.codes(report) and report["status"] == "completed"
    pay = next(s for s in report["steps"] if s["kind"] == "payment_in" and s["stage"] == "create")
    assert pay["outcome"] == "ok"


def test_payment_blocked_when_invoice_is_parked():
    class Park:
        def __init__(self, inner):
            self.inner = inner

        def execute(self, call):
            if call.tool == "sales_invoice.create":
                return {"status": "pending_approval", "approval": {"status": "pending"}}
            return self.inner.execute(call)

        def report_totals(self, *a):
            return self.inner.report_totals(*a)

    report, _ = h.run(p=Park(h.port(ts=_post_ts())), ts=_post_ts())
    pay = [s for s in report["steps"] if s["kind"] == "payment_in"]
    assert report["status"] == "completed" and [s["outcome"] for s in pay] == ["not_run", "not_run"]


# ---- MED 2: in doubt, rerun converges, fresh epoch refused ------------------------------------------------------
def test_exception_is_in_doubt_and_rerun_converges():
    port = h.port(fail_on={"tool": "sales_invoice.create", "nth": 1, "mode": "raise"})
    first, _ = h.run(p=port)
    step = next(s for s in first["steps"] if s["outcome"] == "in_doubt")
    assert first["status"] == "aborted" and first["verdict"] == "aborted"
    assert first["inDoubt"] == [step["sourceId"]] and first["summary"]["inDoubt"] == 1
    assert "SIM-128" in h.codes(first) and validate_report(first) == []
    second, _ = h.run(p=port, on_existing="resume")
    clean, cport = h.run()
    assert second["status"] == "completed" and second["inDoubt"] == []
    assert len(port.docs) == len(cport.docs)


def test_fresh_epoch_on_used_tenant_is_refused_unless_allowed():
    port = h.port()
    h.run(p=port)
    n, calls = len(port.docs), len(port.calls)
    refused, _ = h.run(p=port, run_epoch=1)
    assert refused["status"] == "aborted" and "SIM-129" in h.codes(refused)
    assert len(port.calls) == calls and len(port.docs) == n
    allowed, _ = h.run(p=port, run_epoch=1, on_existing="allow")
    assert allowed["status"] == "completed" and "SIM-130" in h.codes(allowed) and len(port.docs) > n
    with pytest.raises(SimulatorError):
        h.run(on_existing="maybe")


# ---- MED 3: untrusted strings ----------------------------------------------------------------------------------
class Hostile:
    def __init__(self, inner, rid="OK-1", code="<script>x", extra=True):
        self.inner, self.rid, self.code, self.extra, self.reads = inner, rid, code, extra, 0

    def execute(self, call):
        if self.code and call.tool == "purchase_receipt.create":
            return {"status": "error", "error": {"code": self.code}}
        return self.inner.execute(call)

    def report_totals(self, *a):
        t = self.inner.report_totals(*a)
        self.reads += 1
        if self.extra and self.reads > 1:  # the first read is the empty-tenant pre-read
            t["evil‮<b>"] = {"SAR": "1.00"}
            t["sales_net"]["<x>"] = "1.00"
        return t


def test_hostile_port_strings_never_reach_report():
    report, _ = h.run(p=Hostile(h.port()))
    assert report["steps"][0]["errorCode"] == "unknown_error"
    report, _ = h.run(p=Hostile(h.port(), code=None))  # totals: unknown metric and currency dropped
    blob = json.dumps(report, ensure_ascii=False)
    assert "evil" not in blob and "<x>" not in blob and "‮" not in blob
    assert any(a["code"] == "SIM-122" and a["params"] == {"reason": "unknown_metric_or_currency"}
               for a in report["anomalies"])


def test_hostile_record_id_aborts():
    class BadId:
        def __init__(self, inner):
            self.inner = inner

        def execute(self, call):
            return {"status": "ok", "result": {"id": "a‮b<"}}

        def report_totals(self, *a):
            return self.inner.report_totals(*a)

    report, _ = h.run(p=BadId(h.port()))
    assert report["status"] == "aborted" and report["steps"][0]["recordId"] is None


def test_source_text_is_cleaned_and_capped():
    rows = h.month_rows()
    rows[4]["warehouse"] = "W‮" + "x" * 500
    rows[0]["warehouse"] = rows[4]["warehouse"]
    rows[4]["qty"] = "12"
    rows.append(h.row(row=50, type="‮<b>bold\x00" + "y" * 200, date="2026-03-03"))
    report, _ = h.run(rows=rows)
    blob = json.dumps(report, ensure_ascii=False)
    assert "‮" not in blob and "\x00" not in blob
    a = next(a for a in report["anomalies"] if a["code"] == "SIM-104")
    assert len(a["params"]["warehouse"]) <= 128
    assert len(next(a for a in report["anomalies"] if a["code"] == "SIM-116")["params"]["type"]) <= 64


def test_simulate_validates_its_own_output(monkeypatch):
    import simulator.report as rep
    monkeypatch.setattr(rep, "validate_report", lambda r: ["/x"])
    with pytest.raises(SimulatorError) as e:
        h.run()
    assert e.value.code == "SIM-E06"


# ---- MED 4: tolerance -----------------------------------------------------------------------------------------
def _ten_lines():
    return [h.row(row=i, type="sales_invoice", number="BIG", date="2026-03-10", party="C", item=f"I{i}", qty="1",
                  unit_price="0.10", vat="0.015", tax_code="VAT15") for i in range(1, 11)]


def test_tolerance_counts_lines_not_documents():
    ok, _ = h.run(rows=_ten_lines(), tolerances={"vat_output": {"per_line_minor": 1}})
    row = h.metric(ok, "vat_output")
    assert row["differenceMinor"] == 5 and row["lines"] == 10 and row["toleranceMinor"] == 10
    assert row["status"] == "within_tolerance"
    bad, _ = h.run(rows=_ten_lines(), tolerances={"vat_output": {"per_document_minor": 1}})
    assert h.metric(bad, "vat_output")["status"] == "mismatch" and bad["verdict"] == "blocked"


def test_tolerance_rule_lookup_and_caps():
    assert allowed_minor({"sales_net": {}, "default": {"abs_minor": 5}}, "sales_net", 1) == 0  # no `or` fallthrough
    for bad in ({"sales_net": {}}, {"default": {"abs_minor": 10 ** 7}}):
        with pytest.raises(ToleranceError):
            check_tolerances(bad)


def test_header_fields_on_one_line_only_and_conflicts():
    rows = h.month_rows()
    rows[3]["due_date"] = None
    rows[2]["doc_total"] = "126.50"
    report, codes = h.run(rows=rows), None
    assert "SIM-115" not in h.codes(report[0])
    rows[3]["due_date"] = "2026-03-25"
    assert "SIM-115" in h.codes(h.run(rows=rows)[0])


def test_doc_total_label_rounding_vs_mismatch():
    rows = h.month_rows()
    for r in rows[5:8]:
        r["doc_total"] = "100.00"
    report, _ = h.run(rows=rows)
    assert "SIM-131" in h.codes(report) and "SIM-102" not in [
        a["code"] for a in report["anomalies"] if a["params"].get("where")]


# ---- MED 5: Decimal --------------------------------------------------------------------------------------------
def test_large_amounts_exact_and_too_large_refused():
    rows = [h.row(row=1, type="sales_invoice", number="B", date="2026-03-02", party="C", item="I",
                  qty="999999999999999999", unit_price="999999999999999999.999999999", tax_code="VAT15", vat="0")]
    report, _ = h.run(rows=rows)
    assert validate_report(report) == []
    import decimal
    with decimal.localcontext(decimal.Context(prec=80)):
        exp = (Decimal("999999999999999999") * Decimal("999999999999999999.999999999")).quantize(Decimal("0.01"))
        assert h.metric(report, "sales_net")["expectedMinor"] == int(exp * 100)
    rows[0]["qty"] = "1" * 19
    assert "SIM-114" in h.codes(h.run(rows=rows)[0])
    with pytest.raises(MoneyError):
        parse_decimal(Decimal("1E+30"))


@pytest.mark.parametrize("raw", ["0.0000001", "0.000000001", "0.00000012"])
def test_arguments_never_scientific(raw):
    d = Decimal(raw)
    assert "E" not in fmt(d) and _value("unit_price", d, "SAR", "string") == raw
    assert _value("qty", d, "SAR", "object") == raw
    assert _value("unit_price", Decimal("1E-7"), "SAR", "string") == "0.0000001"


def _stock(*moves):
    b = StockBook()
    for kind, qty, price in moves:
        key = ("X", "W", "SAR")
        b.receive(key, Decimal(qty), Decimal(price)) if kind == "in" else b.issue(key, Decimal(qty))
    return b


def test_stock_average_exact_no_dust():
    b = _stock(("in", "2", "10"), ("in", "1", "11"), ("out", "1", "0"))
    assert b.totals() == {"SAR": Fraction(62, 3)} and to_minor(b.totals()["SAR"], "SAR") == 2067
    b = _stock(("in", "2", "10"), ("in", "1", "11"), ("out", "1", "0"), ("out", "2", "0"))
    assert b.totals() == {"SAR": Fraction(0)}  # quantity zero: value zero, no dust


def test_stock_oversell_zero_issue_and_receipt_after():
    assert _stock(("in", "1", "10"), ("out", "0", "0")).totals() == {"SAR": Fraction(10)}
    b = _stock(("in", "1", "10"), ("out", "2", "0"), ("in", "5", "10"))
    assert b.totals() == {} and b.invalid_currencies() == {"SAR"}


def test_oversell_metric_not_compared():
    rows = h.month_rows()
    rows[4]["qty"] = "12"
    report, _ = h.run(rows=rows)
    m = h.metric(report, "stock_value")
    assert m["status"] == "not_compared" and m["reason"] == "negative_stock"
    assert "SIM-104" in h.codes(report)


# ---- MED 6: aging, anomalies, verdict, schema -------------------------------------------------------------------
@pytest.mark.parametrize("age,bucket", [(-1, "not_due"), (0, "not_due"), (1, "0_30"), (30, "0_30"), (31, "31_60"),
                                        (60, "31_60"), (61, "61_90"), (90, "61_90"), (91, "over_90")])
def test_aging_boundaries(age, bucket):
    assert aging_bucket(age) == bucket


def test_aging_end_to_end_boundary_dates():
    def inv(n, due):
        return h.row(row=n, type="sales_invoice", number=f"A{n}", date="2026-03-01", party="C", item="I", qty="1",
                     unit_price="1.00", vat="0", tax_code="ZERO", due_date=due)
    rows = [inv(1, "2026-03-31"), inv(2, "2026-03-30")]  # due on period end (age 0) and one day overdue
    exp = expected_totals(replay_order(normalise(rows, connector_id="i").records), dt.date(2026, 3, 31))
    assert exp[("receivables_not_due", "SAR")]["minor"] == 100 and exp[("receivables_0_30", "SAR")]["minor"] == 100


def test_payment_anomalies():
    rows = h.month_rows()
    rows[8]["total"] = "500.00"
    assert "SIM-126" in h.codes(h.run(rows=rows)[0])
    rows[8]["total"], rows[8]["currency"] = "50.00", "USD"
    assert "SIM-125" in h.codes(h.run(rows=rows)[0])
    rows[8]["currency"], rows[8]["total"] = "SAR", "-5.00"
    a = next(a for a in h.run(rows=rows)[0]["anomalies"] if a["code"] == "SIM-124")
    assert a["params"] == {"fields": ["total"]}


def test_verdict_values():
    held, _ = h.run()
    assert held["verdict"] == "pass_with_warnings"
    clean, _ = h.run(rows=[r for r in h.month_rows() if r["type"] in ("stock_in", "payroll_run")], ts=_post_ts())
    assert clean["verdict"] == "pass"
    aborted, _ = h.run(p=h.port(fail_totals="raise"))
    assert aborted["verdict"] == "aborted"


def test_schema_negative():
    good, _ = h.run()
    for mut in (lambda r: r.update(extra=1), lambda r: r.update(verdict="fine"),
                lambda r: r["steps"][0].update(errorCode="<x>"), lambda r: r["steps"][0].update(outcome="maybe"),
                lambda r: r["comparison"][0].update(metric="Bad Metric"), lambda r: r.pop("inDoubt")):
        r = json.loads(json.dumps(good))
        mut(r)
        assert validate_report(r), mut
