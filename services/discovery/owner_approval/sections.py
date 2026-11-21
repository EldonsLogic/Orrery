"""The four things the owner reads before deciding, as data and i18n keys (no sentences from untrusted text).

Pure functions of the Blueprint, the quote draft (DSC-008) and the gap report (DSC-006). Money is shown from integer
minor units only, and every figure is re-derived here from the lines (principle 6): a quote whose own totals do not add
up is refused (OA-012). Blueprint and quote text is untrusted: cleaned, bounded and marked `untrustedText`."""
from __future__ import annotations

import json

from quote import digest as quote_digest, quote_state, verify_quote
from quote.money import EXPONENT, MAX_MINOR, money, mul_bp

from .errors import OwnerApprovalError
from .text import clean, clean_cut

MAX_ITEMS = 200     # per collection; anything past it is counted in moreItems and blocks approval (the screen is complete)
MAX_DETAIL = 64     # per list inside an item's details; overflow counts in moreItems too
DETAIL_FIELDS = ("admin", "chatActions", "permissions", "entity", "action", "selfApproval", "steps", "connector", "direction",
                 "roles", "tools", "scope", "conditional", "conditions", "timeoutHours", "escalateToRole", "confirm", "transitions")
COLLECTIONS = (("entities", "entity"), ("workflows", "workflow"), ("reports", "report"), ("roles", "role"), ("components", "component"),
               ("approvals", "approval"), ("integrations", "integration"), ("assistants", "assistant"), ("locations", "location"))
# Parts of the Blueprint that the approval digest covers but this screen does not list item by item (shown as a notice).
NOT_SHOWN = ("branding", "i18n")
GAP_KINDS = ("compliance", "component", "entity", "workflow", "report")
SIM_CHECKS = ("numbers", "tax", "approvals", "permissions", "reports", "month_end")


def _bad(detail="quote"):
    raise OwnerApprovalError("OA-012", detail)


def _int(v):
    if type(v) is not int or not -MAX_MINOR < v < MAX_MINOR:
        _bad("amount")
    return v


def _minor(obj):
    if type(obj) is not dict or "minor" not in obj:
        _bad("amount")
    return _int(obj["minor"])


def _labels(item) -> dict:
    lab = item.get("labels") if type(item) is dict else None
    lab = lab if type(lab) is dict else {}
    ar, c1 = clean_cut(lab.get("ar"), 80)
    en, c2 = clean_cut(lab.get("en"), 80)
    return {"ar": ar, "en": en, "cut": c1 or c2}


def _list(v):
    return v if type(v) is list else []


def _d(v):
    return v if type(v) is dict else {}


def _value(v):
    """A condition value as bounded plain text (None when the op takes none). (text, cut)."""
    if v is None:
        return None, False
    try:
        return clean_cut(v if type(v) is str else json.dumps(v, sort_keys=True, ensure_ascii=False), 120)
    except Exception:
        return "", True


def _details(kind, it):
    """What a role, approval rule, integration or assistant allows, and what narrows or widens it: ids, enums and bounded
    values only. (details, hidden); anything cut counts in `hidden`, so approval is blocked rather than shown short."""
    cut = lambda arr: (arr[:MAX_DETAIL], max(0, len(arr) - MAX_DETAIL))  # noqa: E731
    if kind == "role":
        perms, hidden = cut(_list(it.get("permissions")))
        rows = []
        for pm in perms:
            acts, h = cut(_list(_d(pm).get("actions")))
            hidden += h
            rows.append({"entity": clean(_d(pm).get("entity"), 80), "actions": [clean(a, 40) for a in acts]})
        sc = _d(it.get("scope"))
        vals, h = cut(_list(sc.get("values")))
        return {"admin": it.get("isAdmin") is True, "chatActions": it.get("canUseChatActions") is not False, "permissions": rows,
                "scope": {"type": clean(sc.get("type"), 40), "values": [clean(v, 80) for v in vals]}}, hidden + h
    if kind == "approval":
        steps, hidden = cut(_list(it.get("steps")))
        conds, h = cut(_list(it.get("conditions")))
        hidden += h
        rows = []
        for c in conds:
            val, was_cut = _value(_d(c).get("value"))
            hidden += was_cut
            rows.append({"field": clean(_d(c).get("field"), 80), "op": clean(_d(c).get("op"), 16), "value": val})
        num = lambda v: v if type(v) is int else None  # noqa: E731
        ap = _d(it.get("appliesTo"))
        return {"entity": clean(ap.get("entity"), 80), "action": clean(ap.get("action"), 40), "selfApproval": it.get("selfApproval") is True,
                "conditional": bool(rows) or bool(h), "conditions": rows,
                "steps": [{"order": num(_d(s).get("order")), "approverRole": clean(_d(s).get("approverRole"), 80), "mode": clean(_d(s).get("mode"), 40),
                           "timeoutHours": num(_d(s).get("timeoutHours")),
                           "escalateToRole": clean(_d(s).get("escalateToRole"), 80) or None} for s in steps]}, hidden
    if kind == "integration":
        return {"connector": clean(it.get("connector"), 120), "direction": clean(it.get("direction"), 8)}, 0
    if kind == "assistant":
        roles, hidden = cut(_list(it.get("roles")))
        tools, h = cut(_list(it.get("tools")))
        hidden += h
        rows = []
        for x in tools:
            tr, h = cut(_list(_d(x).get("transitions")))
            hidden += h
            rows.append({"tool": clean(_d(x).get("tool"), 130), "confirm": _d(x).get("confirm") is True, "transitions": [clean(v, 80) for v in tr]})
        return {"roles": [clean(r, 80) for r in roles], "tools": rows}, hidden
    return None, 0


def summary_section(content: dict) -> dict:
    counts, items, hidden = {}, [], 0
    for coll, kind in COLLECTIONS:
        arr = content.get(coll)
        arr = arr if type(arr) is list else []
        counts[kind] = len(arr)
        for it in arr[:MAX_ITEMS]:
            if type(it) is dict:
                row = {"kind": kind, "kindKey": f"oa.kind.{kind}", "id": clean(it.get("id"), 80), "labels": _labels(it), "untrustedText": True}
                det, h = _details(kind, it)
                if det is not None:
                    row["details"], hidden = det, hidden + h
                items.append(row)   # a non-dict item is not listed, so it counts in moreItems below
    company = content.get("company") if type(content.get("company")) is dict else {}
    comp = content.get("compliance") if type(content.get("compliance")) is dict else {}
    vat = comp.get("vat") if type(comp.get("vat")) is dict else {}
    einv = comp.get("eInvoicing") if type(comp.get("eInvoicing")) is dict else {}
    compliance = {"country": clean(comp.get("country"), 2), "vatRegistered": vat.get("registered") if type(vat.get("registered")) is bool else None,
                  "eInvoicingMode": clean(einv.get("mode"), 40), "untrustedText": True}
    return {"id": "summary", "labelKey": "oa.section.summary", "introKey": "oa.summary.intro", "counts": counts,
            "compliance": compliance, "notShown": [{"key": k, "labelKey": f"oa.summary.not_shown.{k}"} for k in NOT_SHOWN],
            "notShownNoticeKey": "oa.summary.not_shown",
            "company": {"labels": _labels(company), "country": clean(company.get("country"), 2), "untrustedText": True},
            "detailLabels": [{"key": f, "labelKey": f"oa.detail.{f}"} for f in DETAIL_FIELDS],
            "items": items, "moreItems": max(0, sum(counts.values()) - len(items)) + hidden}


def check_quote(quote, content: dict, gap: dict, bp_id: str, now_dt) -> str:
    """Raise OA-012 unless the quote is the draft for exactly this content and gap report; return its state."""
    try:
        if not verify_quote(quote):
            _bad("digest")
        meta = content["meta"]
        if quote["tenant_blueprint"] != {"id": bp_id, "revision": meta["revision"]} or quote.get("status") != "draft" \
                or quote.get("binding") is not False or quote["inputs"]["blueprint_digest"] != quote_digest(content) \
                or quote["inputs"]["gap_report_digest"] != quote_digest(gap):
            _bad("binding")
        return quote_state(quote, now_dt)
    except OwnerApprovalError:
        raise
    except Exception:
        raise OwnerApprovalError("OA-012", "shape") from None


def cost_section(quote: dict, state: str) -> dict:
    try:
        cur = quote["currency"]
        if cur not in EXPONENT or type(cur) is not str:
            _bad("currency")
        lines = {}
        for sec in ("recurring", "one_off"):
            rows = []
            for ln in quote["lines"][sec]:
                unit, total, qty = _minor(ln["unit"]), _minor(ln["total"]), ln["quantity"]
                if type(qty) is not int or qty < 0 or unit * qty != total:
                    _bad("line")
                params = {k: clean(v if type(v) is str else str(v), 120) for k, v in (ln.get("params") or {}).items() if type(k) is str and type(v) in (str, int)}
                rows.append({"id": clean(ln["id"], 80), "labelKey": clean(ln["label_key"], 80), "params": params, "untrustedText": True,
                             "quantity": qty, "unit": money(unit, cur), "total": money(total, cur), "_t": total})
            lines[sec] = rows
        totals = {}
        for sec in ("recurring", "one_off"):
            t = quote["totals"][sec]
            sub, rate = _minor(t["subtotal"]), t["tax"]["rate_bp"]
            if type(rate) is not int or not 0 <= rate <= 10000 or sub < 0 or sub != sum(r["_t"] for r in lines[sec]):
                _bad("subtotal")
            tax = mul_bp(sub, rate)
            if _minor(t["tax"]["amount"]) != tax or _minor(t["total"]) != sub + tax:
                _bad("total")
            totals[sec] = {"subtotal": money(sub, cur), "tax": money(tax, cur), "taxRateBp": rate, "total": money(sub + tax, cur)}
        for sec in lines:
            for r in lines[sec]:
                del r["_t"]
        unpriced = [{"requirement": clean(u.get("requirement"), 120), "untrustedText": True} for u in quote["unpriced"][:MAX_ITEMS]]
        return {"id": "cost", "labelKey": "oa.section.cost", "currency": cur, "lines": lines, "totals": totals,
                "unpriced": unpriced, "unpricedCount": len(quote["unpriced"]), "complete": quote["complete"] is True,
                "quoteState": state, "validUntil": clean(quote["valid_until"], 40), "noticeKey": "oa.cost.not_binding",
                "placeholderPrices": any(w.get("key") == "quote.warning.placeholder_prices" for w in quote["warnings"]),
                "notes": [k for k, on in (("oa.cost.unpriced", bool(quote["unpriced"])), ("oa.cost.incomplete", quote["complete"] is not True),
                                          ("oa.cost.placeholder", any(w.get("key") == "quote.warning.placeholder_prices" for w in quote["warnings"]))) if on]}
    except OwnerApprovalError:
        raise
    except Exception:
        raise OwnerApprovalError("OA-012", "shape") from None


def gaps_section(gap: dict) -> dict:
    try:
        reqs = gap["requirements"]
        counts = {k: sum(1 for r in reqs if r["status"] == k) for k in ("covered", "partial", "uncovered")}
        if sum(counts.values()) != len(reqs):
            raise OwnerApprovalError("OA-012", "gap")
        rows = []
        for r in reqs:
            if r["status"] != "covered" and len(rows) < MAX_ITEMS * 2:
                kind = r["kind"] if r["kind"] in GAP_KINDS else "other"
                rows.append({"kindKey": f"oa.gap.kind.{kind}", "status": r["status"], "statusKey": f"oa.gap.status.{r['status']}",
                             "ref": clean(r.get("ref"), 120), "untrustedText": True})
        return {"id": "gaps", "labelKey": "oa.section.gaps", "counts": counts, "items": rows,
                "moreItems": max(0, counts["partial"] + counts["uncovered"] - len(rows)),
                "noneKey": "oa.gaps.none" if not rows else None}
    except OwnerApprovalError:
        raise
    except Exception:
        raise OwnerApprovalError("OA-012", "gap") from None


def simulation_section() -> dict:
    return {"id": "simulation", "labelKey": "oa.section.simulation", "introKey": "oa.sim.intro",
            "checks": [{"key": c, "labelKey": f"oa.sim.check.{c}"} for c in SIM_CHECKS], "noticeKey": "oa.sim.notice"}
