"""QA-020: offline harness for the intent-routing experiment. Stdlib only, no model calls, synthetic data only.

Arms are compared on the same cases. The rules arm lives here. Any other arm (small general model, bounded-decision
model) writes a predictions file in the same format and is scored by the same code.

Predictions file (ndjson, one object per line):
  {"id": "ir-en-001", "intent": "finance.vat_summary" | null, "risk_class": "R0" (optional), "latency_ms": 1.2 (optional),
   "cost_usd": 0.0004 (optional)}
  intent null means abstain. A case with no prediction line counts as abstain.

Usage from the repo root:
  python3 -m evals.harness.intent_routing rules --out predictions-rules.ndjson
  python3 -m evals.harness.intent_routing score --predictions predictions-rules.ndjson [--out report.json]
Exit codes: 0 ok, 1 cases failed the checks, 2 bad predictions file.
"""
import argparse
import json
import os
import re
import sys
import time

from evals.harness.textnorm import normalize_arabic

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CASES_PATH = os.path.join(REPO, "evals", "sets", "intent_routing", "cases.ndjson")

RISK_CLASSES = ["R0", "R1", "R2", "R3", "R4"]
RISK_RANK = {r: i for i, r in enumerate(RISK_CLASSES)}

# Intent vocabulary: the 23 intents of evals/sets/arabic_core/README.md plus 3 Tool API verbs (cancel, approve or
# reject decision, bank details). Risk classes follow contracts/tool-api.md section 11 in spirit: reads are R0, drafts
# R1, operational master or stock writes R2, ledger or tax postings R3, bank details, approval decisions and reversals
# R4 (never agent-creatable). The exact policy lives in services/operate/toolapi/policy.py, which is not in this
# worktree, so these labels are UNVERIFIED against the policy until mapped.
INTENT_RISK = {
    "finance.vat_summary": "R0",
    "sales.list_overdue": "R0",
    "inventory.check_stock": "R0",
    "customers.search": "R0",
    "purchasing.list_payables": "R0",
    "reports.show": "R0",
    "calendar.convert_date": "R0",
    "calendar.working_hours": "R0",
    "calendar.fiscal_period": "R0",
    "sales.create_quote": "R1",
    "sales.create_order": "R1",
    "purchasing.create_po": "R1",
    "customers.create": "R2",
    "sales.record_return": "R2",
    "assets.register": "R2",
    "sales.create_invoice": "R3",
    "sales.create_credit_note": "R3",
    "sales.create_debit_note": "R3",
    "finance.post_payment": "R3",
    "finance.post_disbursement": "R3",
    "finance.create_journal_entry": "R3",
    "finance.set_opening_balance": "R3",
    "finance.record_custody": "R3",
    "sales.cancel_invoice": "R4",
    "supplier.update_bank_details": "R4",
    "approval.decide": "R4",
}

# Bilingual rules. Patterns are matched against normalize_arabic(text) lowercased, so they are written in the matching
# form: no diacritics, alef and ta marbuta unified (ة becomes ه). A text routes only when exactly one intent matches;
# zero or several matches abstain.
RULES = [
    ("finance.vat_summary", [r"\bvat\b", r"ضريبه"]),
    ("sales.list_overdue", [r"overdue", r"past due", r"متاخر", r"اتاخر"]),
    ("inventory.check_stock", [r"stock", r"on hand", r"رصيد", r"متوفر", r"المستودع"]),
    ("customers.search", [r"find (the )?customer", r"search .*customer", r"look up .*customer", r"phone number"]),
    ("customers.create", [r"new customer", r"اضيف عميل", r"عميل جديد"]),
    ("sales.create_invoice", [r"sales invoice", r"انشئ فاتوره", r"فاتوره مبيعات", r"سو لي فاتوره"]),
    ("sales.create_quote", [r"quotation", r"\bquote\b", r"عرض سعر"]),
    ("sales.create_order", [r"sales order", r"امر شغل", r"امر بيع"]),
    # "دائن" matches as "داين": normalize_arabic drops the hamza combining mark on ئ, so patterns use that form.
    ("sales.create_credit_note", [r"credit note", r"اشعار داين"]),
    ("sales.create_debit_note", [r"debit note", r"اشعار مدين"]),
    ("sales.record_return", [r"\breturn\b", r"ارجع", r"مرتجع"]),
    ("sales.cancel_invoice", [r"\bcancel", r"ملغ", r"امسح"]),
    ("purchasing.create_po", [r"purchase order", r"\bpo\b", r"امر شراء"]),
    ("purchasing.list_payables", [r"we owe", r"owe (our )?suppliers", r"للموردين"]),
    ("finance.post_payment", [r"receipt voucher", r"received", r"money from", r"post the payment", r"سند قبض"]),
    ("finance.post_disbursement", [r"payment of", r"payment voucher", r"سند صرف", r"\bصرف\b", r"دفعنا", r"دفعت"]),
    ("finance.create_journal_entry", [r"journal", r"قيد"]),
    ("finance.set_opening_balance", [r"opening balance", r"رصيد افتتاحي"]),
    ("finance.record_custody", [r"custody", r"عهده"]),
    ("assets.register", [r"fixed asset", r"\basset"]),
    ("reports.show", [r"trial balance", r"report", r"revenue", r"تقرير", r"ميزانيه"]),
    ("calendar.convert_date", [r"hijri", r"gregorian", r"هجري", r"ميلادي"]),
    ("calendar.working_hours", [r"working hours", r"opening hours"]),
    ("calendar.fiscal_period", [r"fiscal", r"financial year", r"السنه الماليه"]),
    ("supplier.update_bank_details", [r"\biban\b", r"ايبان", r"bank details"]),
    ("approval.decide", [r"\bapprove\b", r"اعتمد", r"وافق"]),
]
_COMPILED = [(intent, [re.compile(p) for p in pats]) for intent, pats in RULES]

ID_RE = re.compile(r"^ir-(en|ar)-\d{3}$")
REQUIRED = ("id", "text", "lang", "dialect", "expected_intent", "expected_risk_class", "ambiguous", "review")
DIALECTS = {"none", "msa", "gulf", "egyptian", "levantine", "mixed"}


def check_case(c):
    """Return a list of problems with one case record. Empty means the record is well formed."""
    cid = c.get("id", "?")
    errs = [f"{cid}: missing {k}" for k in REQUIRED if k not in c]
    if errs:
        return errs
    if not isinstance(cid, str) or not ID_RE.match(cid):
        errs.append(f"{cid}: id must match ir-(en|ar)-NNN")
    if not isinstance(c["text"], str) or not c["text"].strip():
        errs.append(f"{cid}: empty text")
    if "@" in c["text"]:
        errs.append(f"{cid}: '@' in text (synthetic data must not look like contact details)")
    if c["lang"] not in ("en", "ar"):
        errs.append(f"{cid}: lang must be en or ar")
    if c["dialect"] not in DIALECTS:
        errs.append(f"{cid}: unknown dialect {c['dialect']!r}")
    if c["lang"] == "en" and c["dialect"] != "none":
        errs.append(f"{cid}: English cases use dialect none")
    if c["lang"] == "ar" and c["dialect"] == "none":
        errs.append(f"{cid}: Arabic cases need a dialect")
    intent = c["expected_intent"]
    if intent not in INTENT_RISK:
        errs.append(f"{cid}: expected_intent {intent!r} not in vocabulary")
    elif c["expected_risk_class"] != INTENT_RISK[intent]:
        errs.append(f"{cid}: risk {c['expected_risk_class']} does not match {intent} ({INTENT_RISK[intent]})")
    if not isinstance(c["ambiguous"], bool):
        errs.append(f"{cid}: ambiguous must be boolean")
    if c["lang"] == "ar" and c["review"] != "unreviewed":
        errs.append(f"{cid}: Arabic cases must be review: unreviewed (ADR-0033)")
    if c["lang"] == "en" and c["review"] is not None:
        errs.append(f"{cid}: English cases have review null")
    return errs


def load_cases(path=CASES_PATH):
    """Return (cases, errors). Errors cover malformed lines, bad records and duplicate ids."""
    cases, errors, seen = [], [], set()
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                c = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {n}: {exc}")
                continue
            errors.extend(check_case(c))
            cid = c.get("id")
            if cid in seen:
                errors.append(f"{cid}: duplicate id")
            seen.add(cid)
            cases.append(c)
    return cases, errors


def normalise(text):
    return normalize_arabic(text)


def route_rules(text):
    """Return the single matching intent, or None (abstain) when zero or several intents match."""
    t = normalise(text)
    hits = [intent for intent, pats in _COMPILED if any(p.search(t) for p in pats)]
    return hits[0] if len(hits) == 1 else None


def run_rules(cases):
    """Predictions for the rules arm, one dict per case, with measured latency and zero model cost."""
    out = []
    for c in cases:
        t0 = time.perf_counter()
        intent = route_rules(c["text"])
        latency = (time.perf_counter() - t0) * 1000.0
        out.append({
            "id": c["id"],
            "intent": intent,
            "risk_class": INTENT_RISK[intent] if intent else None,
            "latency_ms": round(latency, 4),
            "cost_usd": 0.0,
        })
    return out


def _percentile(values, pct):
    if not values:
        return None
    s = sorted(values)
    rank = max(1, -(-pct * len(s) // 100))  # nearest-rank, ceiling
    return s[int(rank) - 1]


def _f1(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def load_predictions(path, cases):
    """Return {id: prediction}. Raises ValueError on duplicate or unknown ids and on a bad risk class."""
    known = {c["id"] for c in cases}
    preds = {}
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            p = json.loads(line)
            pid = p.get("id")
            if pid not in known:
                raise ValueError(f"line {n}: id {pid!r} is not in the case set")
            if pid in preds:
                raise ValueError(f"line {n}: duplicate prediction for {pid}")
            if p.get("risk_class") not in (None, *RISK_CLASSES):
                raise ValueError(f"line {n}: risk_class {p.get('risk_class')!r} is not R0 to R4")
            preds[pid] = p
    return preds


def score(cases, predictions):
    """Metrics for one arm. predictions is {id: prediction dict}; missing ids abstain."""
    n = len(cases)
    rows = []
    for c in cases:
        p = predictions.get(c["id"])
        intent = p.get("intent") if p else None
        risk = None
        if intent is not None:
            risk = (p.get("risk_class") or INTENT_RISK.get(intent))
        rows.append((c, intent, risk))

    correct = sum(1 for c, intent, _ in rows if intent == c["expected_intent"])
    abstain = sum(1 for _, intent, _ in rows if intent is None)
    missing = sum(1 for c in cases if c["id"] not in predictions)
    unknown = sum(1 for _, intent, _ in rows if intent is not None and intent not in INTENT_RISK)

    wrong_risk = sum(1 for c, intent, risk in rows
                     if risk is not None and risk != c["expected_risk_class"])
    under = sum(1 for c, intent, risk in rows
                if risk is not None and RISK_RANK[risk] < RISK_RANK[c["expected_risk_class"]])
    over = sum(1 for c, intent, risk in rows
               if risk is not None and RISK_RANK[risk] > RISK_RANK[c["expected_risk_class"]])

    labels = sorted({c["expected_intent"] for c in cases} | {i for _, i, _ in rows if i is not None})
    per_intent = {}
    for lab in labels:
        tp = sum(1 for c, i, _ in rows if i == lab and c["expected_intent"] == lab)
        fp = sum(1 for c, i, _ in rows if i == lab and c["expected_intent"] != lab)
        fn = sum(1 for c, i, _ in rows if i != lab and c["expected_intent"] == lab)
        prec, rec, f1 = _f1(tp, fp, fn)
        per_intent[lab] = {"support": tp + fn, "precision": round(prec, 4), "recall": round(rec, 4),
                           "f1": round(f1, 4)}
    gold = [v["f1"] for v in per_intent.values() if v["support"] > 0]
    macro_f1 = round(sum(gold) / len(gold), 4) if gold else 0.0

    def group(key):
        buckets = {}
        for c, intent, _ in rows:
            b = buckets.setdefault(c[key], [0, 0])
            b[0] += 1
            b[1] += intent == c["expected_intent"]
        return {k: {"n": v[0], "accuracy": round(v[1] / v[0], 4)} for k, v in sorted(buckets.items())}

    latencies = [p["latency_ms"] for p in predictions.values() if "latency_ms" in p]
    costs = [p["cost_usd"] for p in predictions.values() if "cost_usd" in p]
    return {
        "cases": n,
        "accuracy": round(correct / n, 4) if n else 0.0,
        "macro_f1": macro_f1,
        "per_intent": per_intent,
        "wrong_risk_class_rate": round(wrong_risk / n, 4) if n else 0.0,
        "under_classified_rate": round(under / n, 4) if n else 0.0,
        "over_classified_rate": round(over / n, 4) if n else 0.0,
        "abstain_rate": round(abstain / n, 4) if n else 0.0,
        "missing_predictions": missing,
        "unknown_intents": unknown,
        "latency_ms": {
            "n": len(latencies),
            "mean": round(sum(latencies) / len(latencies), 4) if latencies else None,
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
        },
        "cost_per_1000_usd": round(sum(costs) / len(costs) * 1000, 6) if costs else None,
        "by_lang": group("lang"),
        "by_dialect": group("dialect"),
        "by_ambiguous": group("ambiguous"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m evals.harness.intent_routing")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rules", help="run the rules arm and write its predictions")
    r.add_argument("--cases", default=CASES_PATH)
    r.add_argument("--out", required=True)
    s = sub.add_parser("score", help="score a predictions file against the case set")
    s.add_argument("--cases", default=CASES_PATH)
    s.add_argument("--predictions", required=True)
    s.add_argument("--out")
    args = ap.parse_args(argv)

    cases, errors = load_cases(args.cases)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    if args.cmd == "rules":
        preds = run_rules(cases)
        with open(args.out, "w", encoding="utf-8") as fh:
            for p in preds:
                fh.write(json.dumps(p, ensure_ascii=False) + "\n")
        print(f"wrote {len(preds)} predictions to {args.out}")
        return 0

    try:
        preds = load_predictions(args.predictions, cases)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"bad predictions file: {exc}", file=sys.stderr)
        return 2
    report = score(cases, preds)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
