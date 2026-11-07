"""Rule 1 (locale) and rule 2 (country consistency)."""
from __future__ import annotations

from datetime import date

from .defaults import resolve_locale
from .report import Report, ValidationContext, as_dict, items, ptr, sid

LOC = ("company", "locale")



def _check_hours(rep: Report, hours, path) -> None:
    h = as_dict(hours)
    f, t = h.get("from"), h.get("to")
    if isinstance(f, str) and isinstance(t, str) and not f < t:
        rep.error("BP-LOC-003", ptr(*path), f"hours.from ({f}) must be earlier than hours.to ({t})")


def _day(s):
    try:
        return date.fromisoformat(s) if isinstance(s, str) else None
    except ValueError:
        return None


def rule_locale(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    """Rule 1. Works on the resolved locale so pack defaults are checked against explicit values."""
    loc = resolve_locale(bp, ctx)
    week = as_dict(loc.get("week"))
    wt = as_dict(loc.get("workingTime"))
    weekend = set(x for x in week.get("weekendDays", []) if isinstance(x, str)) if isinstance(week.get("weekendDays"), list) else set()
    work = wt.get("workDays")
    if isinstance(work, list):
        both = sorted(d for d in set(work) if isinstance(d, str) and d in weekend)
        if both:
            rep.error("BP-LOC-001", ptr(*LOC, "workingTime", "workDays"),
                      f"workDays contains weekend day(s): {', '.join(both)}")
    if "hours" in wt:
        _check_hours(rep, wt["hours"], LOC + ("workingTime", "hours"))
    spans = []
    for i, rp in items(wt.get("reducedPeriods")):
        base = LOC + ("workingTime", "reducedPeriods", i)
        _check_hours(rep, rp.get("hours"), base + ("hours",))
        if rp.get("rule") != "fixed_dates":
            continue
        a, b = _day(rp.get("gregorianFrom")), _day(rp.get("gregorianTo"))
        if a is None or b is None:
            rep.error("BP-LOC-002", ptr(*base), "fixed_dates period needs valid gregorianFrom and gregorianTo")
        elif a > b:
            rep.error("BP-LOC-002", ptr(*base), "gregorianFrom must not be after gregorianTo")
        else:
            spans.append((a, b, i))
    for n, (a1, b1, i1) in enumerate(spans):
        for a2, b2, i2 in spans[n + 1:]:
            if a1 <= b2 and a2 <= b1:
                rep.error("BP-LOC-004", ptr(*LOC, "workingTime", "reducedPeriods", i2),
                          f"reduced period overlaps reducedPeriods/{i1}")


def rule_country(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    """Rule 2. Compares company.country, compliance.country, pack id and holiday calendar prefix."""
    company, comp = as_dict(bp.get("company")), as_dict(bp.get("compliance"))
    cc, kc = sid(company.get("country")), sid(comp.get("country"))
    if cc and kc and cc != kc:
        rep.error("BP-CTRY-001", ptr("compliance", "country"),
                  f"compliance.country {kc} differs from company.country {cc}")
    country = cc or kc
    if not country:
        return
    want = country[:2].lower()
    pack = sid(as_dict(comp.get("countryPack")).get("id"))
    if pack and pack[:2] != want:
        rep.error("BP-CTRY-002", ptr("compliance", "countryPack", "id"),
                  f"country pack '{pack}' does not match country {country} (expected prefix '{want}')")
    cal = sid(as_dict(as_dict(as_dict(company.get("locale")).get("holidays")).get("calendarRef")).get("id"))
    if cal and cal[:2] != want:
        rep.error("BP-CTRY-003", ptr("company", "locale", "holidays", "calendarRef", "id"),
                  f"holiday calendar '{cal}' does not match country {country} (expected prefix '{want}')")
