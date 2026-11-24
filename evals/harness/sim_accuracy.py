"""QA-011: accuracy of the month simulator (BPL-018, BPL-019) against known outcomes. Offline, deterministic, no model.

Clean months are fictional (Arabic names and descriptions, SAR and 3-decimal KWD) with expected totals written by
hand as integer minor units. Each runs through `simulate` with the fake engine adapter (`SimulatedPort`) and the
review layer; rows, anomaly codes and verdict must match exactly. Seeded faults tamper the fake engine's documents
or reported totals after the replay (drift of one minor unit, missing or duplicated documents, VAT mis-rounding,
a flipped sign, a lost bucket) and each must be flagged. The scorer reports the detection rate on faults and the
false-positive rate on clean months as integer permille (no floats). The fake engine is no evidence about the
real one (Q-242); this measures the simulator's comparison and review rules, not an engine.

  python3 -m evals.harness.sim_accuracy        # prints the score as JSON; exit 1 unless 100% and 0 false positives
"""
import copy
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BP = os.path.join(REPO, "services", "blueprint")
if _BP not in sys.path:
    sys.path.insert(0, _BP)

from simulator import SimulatedPort, review, simulate  # noqa: E402
from simulator.money import exact_minor, minor_to_str  # noqa: E402

PERIOD = ("2026-03-01", "2026-03-31")
TENANT = "t_qa011_demo"
CALLER = {"user_id": "u_replay", "role_ids": ["accountant", "warehouse_keeper"]}
TAX_RATES = {"VAT15": "0.15", "ZERO": "0"}


def _tool(name, risk, roles):
    return {"name": name, "kind": "write", "risk_class": risk, "requires": {"roles": roles},
            "input_schema": {"type": "object"}, "idempotency": "required"}


def tool_set():
    """Generated shape (contract 3). Posting is R2 so aging is compared; the held-for-approval path is BPL-018's own tests."""
    acc, wh, tools = ["accountant"], ["warehouse_keeper"], []
    for ent, roles in (("sales_invoice", acc), ("purchase_invoice", acc), ("payment", acc), ("payroll_entry", acc),
                       ("purchase_receipt", wh), ("delivery_note", wh)):
        tools += [_tool(f"{ent}.create", "R1", roles), _tool(f"{ent}.submit", "R2", roles), _tool(f"{ent}.list", "R0", roles)]
    return {"toolApiVersion": "0.2.0", "blueprintRevision": 3, "contentHash": "sha256:synthetic-tool-set", "tools": tools}


_INV = {"lines": "lines", "post": {"verb": "submit"},
        "line": {"item": "item", "qty": "quantity", "unit_price": "rate", "tax_code": "tax_code"}}
MAPPING = {
    "sales_invoice": dict(_INV, entity="sales_invoice", header={"party": "customer", "date": "posting_date",
                                                                "due_date": "due_date", "number": "reference"}),
    "purchase_invoice": dict(_INV, entity="purchase_invoice", header={"party": "supplier", "date": "posting_date",
                                                                      "due_date": "due_date", "number": "reference"}),
    "payment_in": {"entity": "payment", "constants": {"direction": "receive"}, "post": {"verb": "submit"},
                   "header": {"party": "party", "date": "posting_date", "against": "against"}, "line": {"total": "amount"}},
    "payment_out": {"entity": "payment", "constants": {"direction": "pay"}, "post": {"verb": "submit"},
                    "header": {"party": "party", "date": "posting_date", "against": "against"}, "line": {"total": "amount"}},
    "stock_in": {"entity": "purchase_receipt", "lines": "lines", "post": {"verb": "submit"}, "header": {"date": "posting_date"},
                 "line": {"item": "item", "warehouse": "warehouse", "qty": "quantity", "unit_price": "unit_cost"}},
    "stock_out": {"entity": "delivery_note", "lines": "lines", "post": {"verb": "submit"}, "header": {"date": "posting_date"},
                  "line": {"item": "item", "warehouse": "warehouse", "qty": "quantity"}},
    "payroll_run": {"entity": "payroll_entry", "lines": "employees", "post": {"verb": "submit"}, "header": {"date": "posting_date"},
                    "line": {"employee": "employee", "gross": "gross", "deductions": "deductions"}},
}


def _r(n, type_, number, date, desc, ccy="SAR", **kw):
    return dict({"sheet": "الشهر", "row": n, "type": type_, "number": number, "date": date, "currency": ccy,
                 "description": desc}, **kw)


# ---- clean months. Every expected value below is worked out by hand (minor units) ----
# SAR month. Purchases: 10 x 20.00 = 200.00, VAT 30.00. Sales: SI-1 3 x 40.00 + 2 x 25.00 = 170.00, VAT 25.50;
# SI-2 4 x 12.50 = 50.00, VAT 7.50; SI-3 1 x 0.30, VAT 0.045 -> 0.05 half up (a rounding case). Stock: 10 in, 3 out
# at 20.00 = 140.00. Payroll 8000 + 6000 gross, 800 + 600 deducted. Receivables at 31 March: SI-1 195.50 less 50.00
# paid, 11 days overdue (0_30); SI-2 57.50, due 20 January, 70 days (61_90); SI-3 0.35 not due. Payables: 230.00
# less 100.00 paid, due 1 April (not due).
SAR_ROWS = [
    _r(1, "stock_in", "GRN-1", "2026-03-02", "استلام بن عربي من المورد", item="بن-عربي", warehouse="مستودع-الرياض", qty="10", unit_price="20.00"),
    _r(2, "purchase_invoice", "PI-1", "2026-03-02", "فاتورة شراء بن", party="مورد-1", item="بن-عربي", qty="10", unit_price="20.00", vat="30.00", tax_code="VAT15", due_date="2026-04-01"),
    _r(3, "sales_invoice", "SI-1", "2026-03-05", "فاتورة مبيعات", party="عميل-1", item="بن-عربي", qty="3", unit_price="40.00", vat="18.00", tax_code="VAT15", due_date="2026-03-20"),
    _r(4, "sales_invoice", "SI-1", "2026-03-05", "فاتورة مبيعات", party="عميل-1", item="شاي-أخضر", qty="2", unit_price="25.00", vat="7.50", tax_code="VAT15", due_date="2026-03-20"),
    _r(5, "stock_out", "DN-1", "2026-03-05", "تسليم بضاعة للعميل", item="بن-عربي", warehouse="مستودع-الرياض", qty="3"),
    _r(6, "payment_in", "RC-1", "2026-03-20", "سند قبض دفعة", party="عميل-1", total="50.00", against="SI-1"),
    _r(7, "sales_invoice", "SI-2", "2026-03-10", "فاتورة مبيعات متأخرة", party="عميل-2", item="شاي-أخضر", qty="4", unit_price="12.50", vat="7.50", tax_code="VAT15", due_date="2026-01-20"),
    _r(8, "sales_invoice", "SI-3", "2026-03-15", "فاتورة صغيرة", party="عميل-4", item="سكر", qty="1", unit_price="0.30", vat="0.045", tax_code="VAT15", due_date="2026-04-15"),
    _r(9, "payment_out", "PO-1", "2026-03-25", "سند صرف للمورد", party="مورد-1", total="100.00", against="PI-1"),
    _r(10, "payroll_run", "PAY-2026-03", "2026-03-31", "مسير رواتب مارس", employee="موظف-1", gross="8000.00", deductions="800.00"),
    _r(11, "payroll_run", "PAY-2026-03", "2026-03-31", "مسير رواتب مارس", employee="موظف-2", gross="6000.00", deductions="600.00"),
]
SAR_EXPECTED = {
    ("purchases_net", "SAR"): 20000, ("vat_input", "SAR"): 3000, ("payables_not_due", "SAR"): 13000,
    ("sales_net", "SAR"): 22030, ("vat_output", "SAR"): 3305,
    ("receivables_0_30", "SAR"): 14550, ("receivables_61_90", "SAR"): 5750, ("receivables_not_due", "SAR"): 35,
    ("stock_value", "SAR"): 14000,
    ("payroll_gross", "SAR"): 1400000, ("payroll_deductions", "SAR"): 140000, ("payroll_net", "SAR"): 1260000,
}
# KWD month (3 decimals, no VAT). Stock: 3 x 1.001 + 2 x 1.004 = 5.011, issue 1 at the average 1.0022 -> 4.0088 -> 4.009.
# SI-K1 3 x 12.345 = 37.035; SI-K2 3 x 0.3335 = 1.0005 -> 1.001 half up. K1 due 31 March (not due), K2 due 10 March (21 days).
# Payroll 1250.500 gross, 125.050 deducted, 1125.450 net.
KWD_ROWS = [
    _r(1, "stock_in", "GRN-K1", "2026-03-03", "استلام عسل سدر", "KWD", item="عسل-سدر", warehouse="مخزن-الكويت", qty="3", unit_price="1.001"),
    _r(2, "stock_in", "GRN-K2", "2026-03-04", "استلام عسل سدر دفعة ثانية", "KWD", item="عسل-سدر", warehouse="مخزن-الكويت", qty="2", unit_price="1.004"),
    _r(3, "stock_out", "DN-K1", "2026-03-06", "تسليم عسل", "KWD", item="عسل-سدر", warehouse="مخزن-الكويت", qty="1"),
    _r(4, "sales_invoice", "SI-K1", "2026-03-06", "فاتورة عسل", "KWD", party="عميل-ك1", item="عسل-سدر", qty="3", unit_price="12.345", vat="0", tax_code="ZERO", due_date="2026-03-31"),
    _r(5, "sales_invoice", "SI-K2", "2026-03-09", "فاتورة عسل صغيرة", "KWD", party="عميل-ك2", item="عسل-سدر", qty="3", unit_price="0.3335", vat="0", tax_code="ZERO", due_date="2026-03-10"),
    _r(6, "payroll_run", "PAY-K-2026-03", "2026-03-31", "رواتب الكويت", "KWD", employee="موظف-ك1", gross="1250.500", deductions="125.050"),
]
KWD_EXPECTED = {
    ("sales_net", "KWD"): 38036, ("vat_output", "KWD"): 0, ("receivables_not_due", "KWD"): 37035,
    ("receivables_0_30", "KWD"): 1001, ("stock_value", "KWD"): 4009,
    ("payroll_gross", "KWD"): 1250500, ("payroll_deductions", "KWD"): 125050, ("payroll_net", "KWD"): 1125450,
}
# Two identical invoices under different numbers on one day: a source-data warning (SIM-106), tenant honest.
DUP_ROWS = [
    _r(1, "sales_invoice", "SI-D1", "2026-03-08", "فاتورة خبز", party="عميل-3", item="خبز", qty="2", unit_price="5.00", vat="1.50", tax_code="VAT15", due_date="2026-03-08"),
    _r(2, "sales_invoice", "SI-D2", "2026-03-08", "فاتورة خبز", party="عميل-3", item="خبز", qty="2", unit_price="5.00", vat="1.50", tax_code="VAT15", due_date="2026-03-08"),
]
DUP_EXPECTED = {("sales_net", "SAR"): 2000, ("vat_output", "SAR"): 300, ("receivables_0_30", "SAR"): 2300}

CLEAN_MONTHS = [
    {"id": "sar-trading", "rows": SAR_ROWS, "expected_rows": SAR_EXPECTED, "expected_codes": [], "expected_verdict": "pass"},
    {"id": "kwd-three-decimals", "base_currency": "KWD", "rows": KWD_ROWS, "expected_rows": KWD_EXPECTED,
     "expected_codes": [], "expected_verdict": "pass"},
    # The fake engine books a stock issue in its base currency (Q-360), so the mixed month leaves the KWD issue out
    # (stock stays at 5.011) rather than hide that behind a wrong expectation.
    {"id": "mixed-sar-kwd", "rows": SAR_ROWS + [dict(r, row=r["row"] + 100) for r in KWD_ROWS if r["number"] != "DN-K1"],
     "expected_rows": {**SAR_EXPECTED, **KWD_EXPECTED, ("stock_value", "KWD"): 5011}, "expected_codes": [],
     "expected_verdict": "pass"},
    {"id": "possible-duplicate-source", "rows": DUP_ROWS, "expected_rows": DUP_EXPECTED, "expected_codes": ["SIM-106"],
     "expected_verdict": "pass_with_warnings"},
]


# ---- seeded faults: (op, ...) tuples applied to the fake engine after the replay ----
def _f(fid, month, tamper, rows, codes, verdict="blocked"):
    return {"id": fid, "month": month, "tamper": tamper, "expect_rows": rows, "expect_codes": codes, "expect_verdict": verdict}


FAULTS = [
    _f("drift-plus1-sales-net", "sar-trading", ("shift", "sales_net", "SAR", 1), {("sales_net", "SAR"): 1}, ["SIM-121"]),
    _f("drift-minus1-vat-output", "sar-trading", ("shift", "vat_output", "SAR", -1), {("vat_output", "SAR"): -1}, ["SIM-121"]),
    _f("drift-plus1-stock-value-kwd", "kwd-three-decimals", ("shift", "stock_value", "KWD", 1), {("stock_value", "KWD"): 1}, ["SIM-121"]),
    _f("drift-minus1-payroll-net-kwd", "mixed-sar-kwd", ("shift", "payroll_net", "KWD", -1), {("payroll_net", "KWD"): -1}, ["SIM-121"]),
    _f("missing-sales-invoice", "sar-trading", ("delete", "sales_invoice", "SI-2"),
       {("sales_net", "SAR"): -5000, ("vat_output", "SAR"): -750, ("receivables_61_90", "SAR"): -5750},
       ["SIM-121", "SIM-133", "SIM-136"]),
    _f("missing-metric-not-reported", "sar-trading", ("drop_metric", "vat_output"), {("vat_output", "SAR"): "not_compared"},
       ["SIM-122"], "pass_with_warnings"),
    _f("duplicate-sales-invoice", "sar-trading", ("duplicate", "sales_invoice", "SI-1"),
       {("sales_net", "SAR"): 17000, ("vat_output", "SAR"): 2550, ("receivables_0_30", "SAR"): 19550}, ["SIM-121", "SIM-136"]),
    _f("duplicate-stock-receipt-kwd", "kwd-three-decimals", ("duplicate", "stock_in", "2026-03-04"),
       {("stock_value", "KWD"): 2008}, ["SIM-121", "SIM-136"]),
    _f("duplicate-receipt-payment", "sar-trading", ("duplicate", "payment_in", None),
       {("receivables_0_30", "SAR"): -5000}, ["SIM-121", "SIM-136"]),
    _f("missing-payment", "sar-trading", ("delete", "payment_in", None),
       {("receivables_0_30", "SAR"): 5000}, ["SIM-121", "SIM-136"]),
    _f("vat-misrounding-half-down", "sar-trading", ("tax_minor", "SI-3", 4),
       {("vat_output", "SAR"): -1, ("receivables_not_due", "SAR"): -1}, ["SIM-121"]),
    _f("sign-flipped-vat", "sar-trading", ("negate", "vat_output", "SAR"), {("vat_output", "SAR"): -6610}, ["SIM-121", "SIM-132"]),
    _f("excess-precision-amount", "sar-trading", ("set", "sales_net", "SAR", "220.301"),
       {("sales_net", "SAR"): "invalid_actual"}, ["SIM-123"]),
    _f("aging-bucket-misplaced", "sar-trading", ("move", "receivables_61_90", "receivables_0_30", "SAR"),
       {("receivables_61_90", "SAR"): -5750, ("receivables_0_30", "SAR"): 5750}, ["SIM-121", "SIM-133", "SIM-136"]),
]


# ---- the tampering adapter ----
class TamperPort:
    """Wraps the fake engine. Never touches the pre-run read (the runner refuses a tenant that already holds data);
    after the replay it mutates stored documents or the reported totals."""

    def __init__(self, inner, tamper):
        self.inner, self.tamper = inner, tamper

    def execute(self, call):
        return self.inner.execute(call)

    def report_totals(self, tenant_id, caller, period):
        op = self.tamper
        if self.inner.calls and op[0] in ("delete", "duplicate", "tax_minor"):
            self._docs(op)
        totals = self.inner.report_totals(tenant_id, caller, period)
        return self._totals(op, totals) if self.inner.calls else totals

    def _find(self, kind, key):
        docs = [d for d in self.inner.docs.values() if d["kind"] == kind and d["status"] == "posted"]
        if key is not None:
            docs = [d for d in docs if key in (d["number"], d["date"].isoformat() if d["date"] else None)]
        if not docs:
            raise LookupError(f"tamper target not found: {kind} {key}")
        return docs[0]

    def _docs(self, op):
        eng = self.inner
        if op[0] == "delete":
            del eng.docs[self._find(op[1], op[2])["id"]]
            eng.post_order = [i for i in eng.post_order if i in eng.docs]
        elif op[0] == "duplicate":
            d = copy.deepcopy(self._find(op[1], op[2]))
            d["id"] = f"SIM-DUP-{len(eng.docs) + 1:05d}"
            eng.docs[d["id"]] = d
            eng.post_order.append(d["id"])
        else:  # tax_minor: one line's tax set to a different rounding of the same net
            self._find("sales_invoice", op[1])["lines"][0]["tax_minor"] = op[2]

    def _totals(self, op, totals):
        t = copy.deepcopy(totals)
        if op[0] == "shift":
            _, m, c, delta = op
            t[m][c] = minor_to_str(exact_minor(t[m][c], c) + delta, c)
        elif op[0] == "drop_metric":
            del t[op[1]]
        elif op[0] == "set":
            t[op[1]][op[2]] = op[3]
        elif op[0] == "negate":
            t[op[1]][op[2]] = minor_to_str(-exact_minor(t[op[1]][op[2]], op[2]), op[2])
        elif op[0] == "move":
            _, src, dst, c = op
            moved = exact_minor(t[src][c], c)
            t[src][c] = minor_to_str(0, c)
            t[dst][c] = minor_to_str(exact_minor(t[dst][c], c) + moved, c)
        return t


# ---- run and observe ----
def run_month(month, fault=None, tolerances=None):
    ts = tool_set()
    port = SimulatedPort(ts, copy.deepcopy(MAPPING), tax_rates=TAX_RATES, base_currency=month.get("base_currency", "SAR"))
    if fault is not None and fault["tamper"][0] != "noop":
        port = TamperPort(port, fault["tamper"])
    return simulate(copy.deepcopy(month["rows"]), tenant_id=TENANT, period=PERIOD, tool_set=ts,
                    mapping=copy.deepcopy(MAPPING), caller=dict(CALLER), port=port, tolerances=tolerances)


def observe(report):
    """What the owner would see: rows, the union of simulation and review anomaly codes, the recomputed verdict."""
    view = review.build_view(report)
    return {"status": report["status"], "verdict": view["verdict"],
            "codes": sorted({a["code"] for a in view["anomalies"]}),
            "rows": {(r["metric"], r["currency"]): r for r in report["comparison"]}}


def _flagged(f, obs):
    bad = {k: (v["differenceMinor"] if v["status"] == "mismatch" else v["status"])
           for k, v in obs["rows"].items() if v["status"] not in ("match", "within_tolerance")}
    return obs["verdict"] != "pass" and obs["verdict"] == f["expect_verdict"] \
        and obs["codes"] == sorted(f["expect_codes"]) and bad == f["expect_rows"]


def _clean_ok(m, obs):
    rows = {k: (v["expectedMinor"], v["actualMinor"], v["status"]) for k, v in obs["rows"].items()}
    return (obs["status"] == "completed" and obs["verdict"] == m["expected_verdict"]
            and obs["codes"] == sorted(m["expected_codes"])
            and rows == {k: (v, v, "match") for k, v in m["expected_rows"].items()})


def _permille(n, d):
    return 0 if d == 0 else n * 1000 // d


def score(months=None, faults=None):
    months = CLEAN_MONTHS if months is None else months
    faults = FAULTS if faults is None else faults
    by_id = {m["id"]: m for m in CLEAN_MONTHS}
    fp = [m["id"] for m in months if not _clean_ok(m, observe(run_month(m)))]
    missed = [f["id"] for f in faults if not _flagged(f, observe(run_month(by_id[f["month"]], f)))]
    detected = len(faults) - len(missed)
    ok = not fp and not missed
    return {"clean": {"months": len(months), "falsePositives": len(fp), "falsePositivePermille": _permille(len(fp), len(months)),
                      "falsePositiveMonths": fp},
            "faults": {"total": len(faults), "detected": detected, "detectionPermille": _permille(detected, len(faults)),
                       "undetected": missed},
            "gate": "pass" if ok else "fail"}


def main(argv=None) -> int:
    s = score()
    print(json.dumps(s, indent=2, sort_keys=True))
    return 0 if s["gate"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
