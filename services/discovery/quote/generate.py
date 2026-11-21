"""Deterministic quote from a Blueprint, its gap analysis and a price book (DSC-008).

No model calls, no network, no randomness, no file writes; the clock is the caller's `now`. Every amount is an
integer in minor units; the only rounding is `money.mul_bp` (half up, Decimal) for tax and discount. The result is
a DRAFT: `status` is "draft", `binding` is False and `requires_human_approval` is True. Nothing here sends or
accepts a quote (DSC-009 and the owner or founder do that).
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .errors import QuoteError
from .money import checked, is_int, money, mul_bp, percent_text
from .pricebook import MAX_VALIDITY_DAYS, canonical, digest, validate_price_book

SCHEMA_VERSION = "1"
GAP_SCHEMA = "1"
MAX_LINES = 2000
MAX_REQUESTS = 5000
_LABELS = json.loads(Path(__file__).with_name("labels.json").read_text(encoding="utf-8"))
_PH = re.compile(r"\{([a-z_]+)\}")
_ID_LIKE = re.compile(r"^[A-Za-z0-9._:/#\[\]-]{1,200}$")
_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


def _vkey(v: Any) -> tuple:
    """Semver precedence key (10.0.0 > 9.0.0; a release beats its pre-release). Invalid version: QTE-GAP-001."""
    m = _SEMVER.fullmatch(v) if isinstance(v, str) and len(v) <= 64 else None
    if not m:
        raise QuoteError("QTE-GAP-001", "component version")
    pre = m.group(4)
    ids = () if pre is None else tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), pre is None, ids)


def _id(v: Any, what: str) -> str:
    if not isinstance(v, str) or not _ID_LIKE.fullmatch(v):
        raise QuoteError("QTE-GAP-001", f"{what} is not a safe identifier")
    return v


def _count(v: Any, what: str) -> int:
    if not is_int(v) or v < 0:
        raise QuoteError("QTE-GAP-001", what)
    return v


def render(key: str, params: dict | None = None, locale: str = "en") -> str:
    """Label for an i18n key, single pass (a parameter value is never re-expanded). Unknown: the key itself."""
    text = _LABELS.get(locale, {}).get(key)
    if text is None:
        return key
    p = params or {}
    return _PH.sub(lambda m: str(p[m.group(1)]) if m.group(1) in p else m.group(0), text)


def _lab(key: str, params: dict | None = None) -> dict:
    return {"ar": render(key, params, "ar"), "en": render(key, params, "en")}


def _clean(s: Any, cap: int = 120) -> str:
    """Untrusted text for a label parameter: control, format (bidi) and separator characters removed, length capped."""
    if not isinstance(s, str):
        return ""
    return "".join(c for c in s if c == " " or unicodedata.category(c)[0] not in "CZ")[:cap]


def _utc(now: Any) -> datetime:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise QuoteError("QTE-CLOCK-001", "now must be a timezone-aware datetime")
    return now.astimezone(timezone.utc).replace(microsecond=0)


def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: Any) -> datetime:
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        raise QuoteError("QTE-QUOTE-001", "timestamp") from None


def _line(lid: str, section: str, kind: str, key: str, params: dict, unit: int, qty: int, cur: str, sources: list) -> dict:
    total = checked(unit * qty)
    return {"id": lid, "section": section, "kind": kind, "label_key": key, "params": params, "labels": _lab(key, params),
            "quantity": qty, "unit": money(unit, cur), "total": money(total, cur), "requirements": sources}


def _check_gap(gap: Any, blueprint: dict) -> bool:
    """Validate the gap report against the Blueprint. Returns True when it is bound by content digest."""
    bp_id, bp_rev = blueprint["meta"].get("id"), blueprint["meta"].get("revision")
    if not isinstance(gap, dict) or gap.get("schema") != GAP_SCHEMA:
        raise QuoteError("QTE-GAP-001", "gap analysis schema")
    ref = gap.get("blueprint")
    if (not isinstance(ref, dict) or not isinstance(bp_id, str) or ref.get("id") != bp_id
            or type(bp_rev) is not int or type(ref.get("revision")) is not int or ref["revision"] != bp_rev):
        raise QuoteError("QTE-GAP-002", "gap analysis was made for a different Blueprint or revision")
    bound = "digest" in ref
    if bound and ref["digest"] != digest(blueprint):
        raise QuoteError("QTE-GAP-002", "gap analysis was made for different Blueprint content")
    if not isinstance(gap.get("requirements"), list) or not isinstance(gap.get("component_requests"), list):
        raise QuoteError("QTE-GAP-001", "gap analysis shape")
    if len(gap["requirements"]) > MAX_REQUESTS * 4 or len(gap["component_requests"]) > MAX_REQUESTS:
        raise QuoteError("QTE-RANGE-002", "too many requirements")
    s = gap.get("summary")
    if not isinstance(s, dict) or not isinstance(gap.get("environment"), str):
        raise QuoteError("QTE-GAP-001", "summary")
    _count(s.get("malformed_blueprint_items"), "malformed_blueprint_items")
    _count(s.get("library_entries_rejected"), "library_entries_rejected")
    counts = {k: sum(1 for r in gap["requirements"] if isinstance(r, dict) and r.get("status") == k)
              for k in ("covered", "partial", "uncovered")}
    if any(s.get(k) != v for k, v in counts.items()) or s.get("total") != len(gap["requirements"]):
        raise QuoteError("QTE-GAP-003", "summary does not match the requirements (tampered or inconsistent)")
    return bound


def generate_quote(blueprint: Any, gap_report: Any, price_book: Any, *, now: datetime,
                   validity_days: int | None = None, discount_bp: int = 0,
                   expected_price_book_digest: str | None = None) -> dict:
    """Build a draft quote. Raises QuoteError (never returns a partial quote) on any invalid or inconsistent input.

    `validity_days` may shorten the price book's validity, never extend it. `discount_bp` (0..10000) is a
    one-off discount a person chose, applied before tax and shown as its own negative line.
    """
    issued = _utc(now)
    pb = validate_price_book(price_book)
    pb_digest = digest(pb)
    if expected_price_book_digest is not None and expected_price_book_digest != pb_digest:
        raise QuoteError("QTE-PB-002", "price book digest differs from the pinned one")
    if not isinstance(blueprint, dict) or not isinstance(blueprint.get("meta"), dict) or not isinstance(blueprint.get("company"), dict):
        raise QuoteError("QTE-BP-001", "blueprint shape")
    country = blueprint["company"].get("country")
    market = pb["markets"].get(country) if isinstance(country, str) else None
    if market is None:
        raise QuoteError("QTE-BP-002", "no price book market for the company's country")
    cur = market["currency"]
    prices = pb["currencies"][cur]
    bp_meta = blueprint["meta"]
    bound = _check_gap(gap_report, blueprint)
    if not is_int(discount_bp) or not 0 <= discount_bp <= 10000:
        raise QuoteError("QTE-ARG-001", "discount_bp")
    days = pb["validity_days"]
    if validity_days is not None:
        if not is_int(validity_days) or not 1 <= validity_days <= MAX_VALIDITY_DAYS:
            raise QuoteError("QTE-ARG-002", "validity_days")
        days = min(days, validity_days)

    recurring = [_line("base_platform", "recurring", "base_platform", "quote.line.base_platform", {}, prices["base_platform_monthly"], 1, cur, [])]
    one_off: list[dict] = []
    unpriced: list[dict] = []

    # covered and partial requirements: one recurring module line per distinct component (several requirements share one)
    modules: dict[str, dict] = {}
    eligible: list[bool] = []
    uncovered_open = {}
    for r in gap_report["requirements"]:
        if not isinstance(r, dict) or r.get("status") not in ("covered", "partial", "uncovered"):
            raise QuoteError("QTE-GAP-001", "requirement")
        rid = _id(r.get("id"), "requirement id")
        if r["status"] == "uncovered":
            if r.get("kind") != "component":
                uncovered_open[rid] = r
            continue
        m = r.get("match")
        cid = m.get("component") if isinstance(m, dict) else None
        if not isinstance(cid, str) or not isinstance(m.get("version"), str):
            raise QuoteError("QTE-GAP-001", "covered requirement without a match")
        _id(cid, "component id")
        _vkey(m["version"])
        eligible.append(m.get("production_eligible") is True)
        e = modules.setdefault(cid, {"version": m["version"], "reqs": [], "partial": False})
        e["reqs"].append(rid)
        e["partial"] = e["partial"] or r["status"] == "partial"
        if _vkey(m["version"]) > _vkey(e["version"]):
            e["version"] = m["version"]  # semver precedence, deterministic when two requirements disagree
    for cid in sorted(modules):
        e = modules[cid]
        params = {"component": _clean(cid), "version": _clean(e["version"], 40)}
        unit = prices["components"].get(cid, prices["module_default_monthly"])
        recurring.append(_line(f"module:{cid}", "recurring", "module", "quote.line.module", params, unit, 1, cur, sorted(e["reqs"])))
        if e["partial"]:
            one_off.append(_line(f"configuration:{cid}", "one_off", "configuration", "quote.line.configuration",
                                 {"component": params["component"]}, prices["configuration_one_off"], 1, cur, sorted(e["reqs"])))
    # uncovered: one build line per component request, and only for an uncovered requirement of this very gap report.
    # A request for a covered or unknown requirement, or a second request for the same one, would add a charge the
    # gap analysis does not support: refused. An uncovered requirement without a request is listed for manual pricing.
    requested: set[str] = set()
    for q in gap_report["component_requests"]:
        if not isinstance(q, dict) or q.get("kind_hint") not in ("rigid", "configurable"):
            raise QuoteError("QTE-GAP-001", "component request")
        key = _id(q.get("request_key"), "request key")
        rid = q.get("requirement_id")
        if not isinstance(rid, str) or rid not in uncovered_open or rid in requested:
            raise QuoteError("QTE-GAP-003", "component request does not match exactly one uncovered requirement")
        requested.add(rid)
        kind = q["kind_hint"]
        params = {"ref": _clean(uncovered_open[rid].get("ref"))}
        one_off.append(_line(f"build:{key}", "one_off", f"build_{kind}", f"quote.line.build.{kind}", params,
                             prices["build_one_off"][kind], 1, cur, [rid]))
    for rid in sorted(uncovered_open):
        if rid not in requested:
            ref = _clean(uncovered_open[rid].get("ref"))
            unpriced.append({"requirement": rid, "label_key": "quote.unpriced.requirement", "params": {"ref": ref},
                             "labels": _lab("quote.unpriced.requirement", {"ref": ref})})
    for r in gap_report["requirements"]:   # an uncovered component binding has no request by design (Q-403)
        if r["status"] == "uncovered" and r.get("kind") == "component":
            ref = _clean(r.get("ref"))
            unpriced.append({"requirement": r["id"], "label_key": "quote.unpriced.requirement", "params": {"ref": ref},
                             "labels": _lab("quote.unpriced.requirement", {"ref": ref})})
    if len(recurring) + len(one_off) > MAX_LINES:
        raise QuoteError("QTE-RANGE-002", "too many lines")

    ids = [x["id"] for x in recurring + one_off]
    if len(ids) != len(set(ids)):
        raise QuoteError("QTE-GAP-001", "duplicate line id")
    rec_sub = checked(sum(x["total"]["minor"] for x in recurring))
    one_sub = checked(sum(x["total"]["minor"] for x in one_off))
    if discount_bp and one_sub:
        d = mul_bp(one_sub, discount_bp)
        pct = percent_text(discount_bp)
        one_off.append({"id": "discount", "section": "one_off", "kind": "discount", "label_key": "quote.line.discount",
                        "params": {"rate": pct}, "labels": _lab("quote.line.discount", {"rate": pct}), "quantity": 1,
                        "unit": money(-d, cur), "total": money(-d, cur), "requirements": []})
        one_sub -= d
    rate = market["tax"]["rate_bp"]
    rate_txt = percent_text(rate)
    rec_tax = mul_bp(rec_sub, rate)
    one_tax = mul_bp(one_sub, rate)

    def tax_key(which: str) -> str:
        return f"quote.tax.{which}" if rate else f"quote.tax.{which}_none"

    def section(sub: int, tax: int, which: str) -> dict:
        return {"subtotal": money(sub, cur), "tax": {"rate_bp": rate, "label_key": tax_key(which),
                                                    "params": {"rate": rate_txt},
                                                    "labels": _lab(tax_key(which), {"rate": rate_txt}),
                                                    "amount": money(checked(tax), cur)},
                "total": money(checked(sub + tax), cur)}

    gsum = gap_report["summary"]
    incomplete = (["unpriced_items"] if unpriced else []) + (["malformed_blueprint_items"] if gsum["malformed_blueprint_items"] else []) \
        + (["library_entries_rejected"] if gsum["library_entries_rejected"] else [])
    prod_ok = gap_report["environment"] == "production" and all(eligible)
    warnings = ["quote.warning.draft_not_binding"]
    if not prod_ok:
        warnings.append("quote.warning.not_production_eligible")
    if not bound:
        warnings.append("quote.warning.gap_not_content_bound")
    if gsum["malformed_blueprint_items"] or gsum["library_entries_rejected"]:
        warnings.append("quote.warning.malformed_inputs")
    if pb["status"] != "approved":
        warnings.append("quote.warning.placeholder_prices")
    if unpriced:
        warnings.append("quote.warning.unpriced_items")
    a = prices["allowances"]
    body = {
        "schema": SCHEMA_VERSION, "status": "draft", "binding": False, "requires_human_approval": True,
        "complete": not incomplete, "incomplete_reasons": incomplete, "production_eligible": prod_ok, "tenant_blueprint": {"id": bp_meta.get("id"), "revision": bp_meta.get("revision")},
        "market": country, "currency": cur,
        "issued_at": _iso(issued), "valid_until": _iso(issued + timedelta(days=days)), "validity_days": days,
        "price_book": {"id": pb["id"], "status": pb["status"], "digest": pb_digest},
        "inputs": {"blueprint_digest": digest(blueprint), "gap_report_digest": digest(gap_report), "environment": gap_report["environment"],
                   "gap_bound_by": "content_digest" if bound else "id_and_revision"},
        "rounding": "half_up_minor_units",
        "lines": {"recurring": recurring, "one_off": one_off}, "unpriced": unpriced,
        "totals": {"recurring": section(rec_sub, rec_tax, "recurring"), "one_off": section(one_sub, one_tax, "one_off")},
        "allowances": {"ai_actions_monthly": {"quantity": a["ai_actions_monthly"], "label_key": "quote.allowance.ai_actions",
                                              "labels": _lab("quote.allowance.ai_actions")},
                       "overage_pack": {"size": a["overage_pack_size"], "price": money(a["overage_pack_price"], cur),
                                        "label_key": "quote.allowance.overage_pack", "params": {"size": a["overage_pack_size"]},
                                        "labels": _lab("quote.allowance.overage_pack", {"size": a["overage_pack_size"]})}},
        "warnings": [{"key": k, "labels": _lab(k)} for k in warnings],
        "labels": {"title": _lab("quote.title"), "status": _lab("quote.status.draft"),
                   "recurring": _lab("quote.section.recurring"), "one_off": _lab("quote.section.one_off")},
    }
    d = digest(body)
    return {**body, "quote_id": "QTE-" + d[:16].upper(), "digest": d}


def verify_quote(quote: Any) -> bool:
    """True when the stored digest matches the content and the quote id matches the digest. This detects edits to a
    stored quote; it is not a signature (anyone can recompute it), so DSC-009 must sign at approval (Q-401)."""
    if not isinstance(quote, dict) or not isinstance(quote.get("digest"), str):
        return False
    body = {k: v for k, v in quote.items() if k not in ("digest", "quote_id")}
    try:
        d = digest(body)
    except (TypeError, ValueError, RecursionError, QuoteError):
        return False
    return d == quote["digest"] and quote.get("quote_id") == "QTE-" + d[:16].upper()


def quote_state(quote: Any, now: datetime) -> str:
    """'valid' while issued_at <= now < valid_until, else 'expired' or 'not_yet_valid'. A quote whose digest does not
    verify raises QTE-TAMPER-001: never trust the dates of an edited quote."""
    if not verify_quote(quote):
        raise QuoteError("QTE-TAMPER-001", "digest mismatch")
    t = _utc(now)
    if t < _parse_iso(quote["issued_at"]):
        return "not_yet_valid"
    return "valid" if t < _parse_iso(quote["valid_until"]) else "expired"
