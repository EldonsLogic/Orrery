"""In-memory simulated tenant behind the EnginePort interface (CI stand-in; no real tenant is reachable in CI).

It behaves like the Tool API gateway in front of a tenant, as far as the simulator can observe: tool set
lookup, role pre-check, R3 and R4 parked (`pending_approval`), idempotency (same key and arguments: stored
result, `replayed: true`; other arguments: `idempotency_conflict`), documents in draft or posted state, line
tax from the tenant's tax rates rounded per line, moving-average stock valuation on posting, aging on posted
documents. It models behaviour only; nothing here is evidence about the real engine (UNVERIFIED until the
gateway-backed port runs against a real tenant). Fault hooks let the tests prove the runner fails closed.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from .aging import BUCKETS, aging_bucket
from .money import MoneyError, in_context, minor_to_str, parse_decimal, round_half_up, to_minor
from .plan import AUTO_RUN, MONEY_FIELDS, RISKS, sha256
from .runner import ToolCall
from .valuation import StockBook


def _err(code: str) -> dict:
    return {"status": "error", "error": {"code": code, "message_key": f"errors.{code}", "retryable": False,
                                         "details": {}}}


class SimulatedPort:
    def __init__(self, tool_set: dict, mapping: dict, *, tax_rates=None, default_tax_code=None,
                 base_currency: str = "SAR", fail_on=None, fail_totals=None):
        self.tools = {t["name"]: t for t in tool_set["tools"]}
        self.mapping = mapping
        self.tax_rates = {k: parse_decimal(v) for k, v in (tax_rates or {}).items()}
        self.default_tax_code = default_tax_code or {}
        self.base_currency = base_currency
        self.fail_on = fail_on  # {"tool", "nth", "mode": error|raise|malformed}
        self.fail_totals = fail_totals  # None | raise | malformed
        self.calls = []  # every call received, with the risk class the port resolved
        self.docs = {}
        self.post_order = []
        self._idem = {}
        self._seen = {}

    # ---- helpers ------------------------------------------------------------------------------------------------
    def _risk_roles(self, tool: dict, args: dict):
        risk, roles = tool.get("risk_class"), (tool.get("requires") or {}).get("roles") or []
        if tool["name"].endswith(".transition"):
            tr = [t for t in tool.get("transitions") or [] if t.get("id") == args.get("transition_id")]
            if len(tr) != 1:
                return None, []
            risk, roles = tr[0].get("risk_class"), tr[0].get("allowed_roles") or []
        return (risk if risk in RISKS else "R4"), roles

    def _kind(self, entity: str, args: dict):
        for kind, m in sorted(self.mapping.items()):
            if m["entity"] == entity and all(args.get(k) == v for k, v in (m.get("constants") or {}).items()):
                return kind, m
        return None, None

    def _num(self, v):
        return parse_decimal(v["value"] if isinstance(v, dict) else v)

    def _create(self, kind: str, m: dict, args: dict) -> dict:
        rev = {t: s for s, t in (m.get("header") or {}).items() if t}
        lrev = {t: s for s, t in (m.get("line") or {}).items() if t}
        head = {rev[k]: v for k, v in args.items() if k in rev}
        raw_lines = args.get(m["lines"], []) if m.get("lines") else [{k: v for k, v in args.items() if k in lrev}]
        currency = self.base_currency
        lines = []
        for raw in raw_lines:
            ln = {}
            for k, v in raw.items():
                src = lrev.get(k)
                if src is None:
                    continue
                if isinstance(v, dict) and "currency" in v:
                    currency = v["currency"]
                ln[src] = self._num(v) if src in MONEY_FIELDS or src == "qty" else v
            code = ln.get("tax_code") or self.default_tax_code.get(kind)
            if code is not None and code not in self.tax_rates:
                raise MoneyError("tax_code")
            rate = self.tax_rates.get(code, Decimal(0))
            if "qty" in ln and "unit_price" in ln:
                net = to_minor(ln["qty"] * ln["unit_price"], currency)
                ln["net_minor"] = net  # line tax rounded per line, in minor units
                ln["tax_minor"] = round_half_up(Decimal(net) * rate)
            lines.append(ln)
        if kind in ("payment_in", "payment_out") and head.get("against") is not None:
            ref = self.docs.get(head["against"]) if isinstance(head["against"], str) else None
            if ref is None or ref["kind"] != ("sales_invoice" if kind == "payment_in" else "purchase_invoice"):
                return _err("unknown_reference")  # like the gateway: a link must be an engine record id
        doc_id = f"SIM-{kind.upper()}-{len(self.docs) + 1:05d}"
        self.docs[doc_id] = {"id": doc_id, "kind": kind, "status": "draft", "currency": currency, "lines": lines,
                             "number": head.get("number"), "against": head.get("against"),
                             "date": dt.date.fromisoformat(head["date"]) if head.get("date") else None,
                             "due": dt.date.fromisoformat(head["due_date"]) if head.get("due_date") else None}
        return {"status": "ok", "result": {"id": doc_id, "state": "draft"}}

    def _post(self, args: dict) -> dict:
        doc = self.docs.get(args.get("id"))
        if doc is None:
            return _err("not_found")
        if doc["status"] != "draft":
            return _err("conflict")
        doc["status"] = "posted"
        self.post_order.append(doc["id"])
        return {"status": "ok", "result": {"id": doc["id"], "state": "posted"}}

    def _fault(self, call: ToolCall):
        f = self.fail_on
        if not f or f.get("tool") != call.tool:
            return None
        self._seen[call.tool] = self._seen.get(call.tool, 0) + 1
        if self._seen[call.tool] != f.get("nth", 1):
            return None
        if f["mode"] == "raise":
            raise RuntimeError("simulated port failure")
        return _err("engine_error") if f["mode"] == "error" else {"status": "ok", "result": {}}

    # ---- EnginePort ---------------------------------------------------------------------------------------------
    @in_context
    def execute(self, call: ToolCall) -> dict:
        tool = self.tools.get(call.tool)
        risk, roles = self._risk_roles(tool, call.arguments) if tool else (None, [])
        self.calls.append({"tool": call.tool, "risk_class": risk, "key": call.idempotency_key,
                           "transition_id": call.arguments.get("transition_id")})
        fault = self._fault(call)
        if fault is not None:
            return fault
        if tool is None or risk is None:
            return _err("unknown_tool")
        if not set(call.caller.get("role_ids") or []) & set(roles):
            return _err("permission_denied")
        if risk not in AUTO_RUN:
            return {"status": "pending_approval", "approval": {"status": "pending"}}
        key = (call.tenant_id, call.tool, call.idempotency_key)
        h = sha256(call.arguments)
        if key in self._idem:
            stored_hash, resp = self._idem[key]
            return dict(resp, replayed=True) if stored_hash == h else _err("idempotency_conflict")
        entity, verb = call.tool.split(".", 1)
        try:
            if verb == "create":
                kind, m = self._kind(entity, call.arguments)
                resp = self._create(kind, m, call.arguments) if kind else _err("unknown_tool")
            elif verb in ("submit", "transition"):
                resp = self._post(call.arguments)
            else:
                resp = _err("unknown_tool")
        except (MoneyError, ValueError, KeyError, TypeError):
            resp = _err("invalid_arguments")
        if resp["status"] == "ok":
            self._idem[key] = (h, resp)
        return resp

    @in_context
    def report_totals(self, tenant_id: str, caller: dict, period: tuple) -> dict:
        if self.fail_totals == "raise":
            raise RuntimeError("simulated totals failure")
        if self.fail_totals == "malformed":
            return {"sales_net": {"SAR": 1}}
        end = dt.date.fromisoformat(period[1])
        acc = {}  # every metric this tenant can report, zero in the base currency when it has no documents
        for m in ("sales_net", "vat_output", "purchases_net", "vat_input", "stock_value", "payroll_gross",
                  "payroll_deductions", "payroll_net") + tuple(f"{f}_{b}" for f in ("receivables", "payables")
                                                               for b in BUCKETS):
            acc[m] = {self.base_currency: 0}

        def add(metric, ccy, minor):
            acc.setdefault(metric, {}).setdefault(ccy, 0)
            acc[metric][ccy] += minor

        docs = sorted(self.docs.values(), key=lambda d: d["id"])
        paid = {}
        for d in docs:
            if d["kind"] in ("payment_in", "payment_out") and d["status"] == "posted":
                target = "sales_invoice" if d["kind"] == "payment_in" else "purchase_invoice"
                amt = sum(to_minor(ln.get("total", Decimal(0)), d["currency"]) for ln in d["lines"])
                k2 = (target, d["against"], d["currency"])  # engine record id of the invoice
                paid[k2] = paid.get(k2, 0) + amt
        for d in docs:
            c, k = d["currency"], d["kind"]
            if k in ("sales_invoice", "purchase_invoice"):
                net = sum(ln.get("net_minor", 0) for ln in d["lines"])
                tax = sum(ln.get("tax_minor", 0) for ln in d["lines"])
                sales = k == "sales_invoice"
                add("sales_net" if sales else "purchases_net", c, net)
                add("vat_output" if sales else "vat_input", c, tax)
                if d["status"] == "posted":
                    open_minor = net + tax - paid.get((k, d["id"], c), 0)
                    if open_minor:
                        age = (end - (d["due"] or d["date"])).days
                        add(f"{'receivables' if sales else 'payables'}_{aging_bucket(age)}", c, open_minor)
            elif k == "payroll_run":
                gross = sum((ln.get("gross", Decimal(0)) for ln in d["lines"]), Decimal(0))
                ded = sum((ln.get("deductions", Decimal(0)) for ln in d["lines"]), Decimal(0))
                add("payroll_gross", c, to_minor(gross, c))
                add("payroll_deductions", c, to_minor(ded, c))
                add("payroll_net", c, to_minor(gross - ded, c))
        book = StockBook()
        for doc_id in self.post_order:
            d = self.docs[doc_id]
            if d["kind"] not in ("stock_in", "stock_out"):
                continue
            for ln in d["lines"]:
                key = (ln.get("item"), ln.get("warehouse"), d["currency"])
                if d["kind"] == "stock_in":
                    book.receive(key, ln["qty"], ln["unit_price"])
                else:
                    book.issue(key, ln["qty"])
        for c, value in book.totals().items():
            add("stock_value", c, to_minor(value, c))
        return {m: {c: minor_to_str(v, c) for c, v in sorted(by.items())} for m, by in sorted(acc.items())}
