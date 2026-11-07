"""Country-pack locale defaults and resolution of company.locale (rule 1)."""
from __future__ import annotations

import copy
from typing import Any

from .report import ValidationContext, as_dict

# PLACEHOLDER DEFAULTS. The country pack (CMP-021) is authoritative; these values only let the
# validator resolve omitted company.locale fields until the packs ship. UNVERIFIED for ae and eg.
# Each value below is a placeholder default, not a statement of law.
DEFAULT_PACK_LOCALES: dict[str, dict[str, Any]] = {
    "sa": {  # placeholder defaults, the country pack (CMP-021) is authoritative
        "timezone": "Asia/Riyadh",
        "calendar": {"primary": "gregorian", "secondaryDisplay": "hijri_umm_al_qura"},
        "week": {"startDay": "sun", "weekendDays": ["fri", "sat"]},
        "workingTime": {
            "workDays": ["sun", "mon", "tue", "wed", "thu"],
            "hours": {"from": "08:00", "to": "17:00"},
        },
        "fiscalYear": {"type": "gregorian", "startMonth": 1, "startDay": 1},
        "holidays": {"calendarRef": {"id": "sa.holidays", "version": "0.1.0"}},
        "numberSystem": "western",
        "currency": "SAR",
    },
    "ae": {  # placeholder defaults, the country pack (CMP-021) is authoritative
        "timezone": "Asia/Dubai",
        "calendar": {"primary": "gregorian", "secondaryDisplay": "none"},
        "week": {"startDay": "mon", "weekendDays": ["sat", "sun"]},
        "workingTime": {
            "workDays": ["mon", "tue", "wed", "thu", "fri"],
            "hours": {"from": "08:00", "to": "17:00"},
        },
        "fiscalYear": {"type": "gregorian", "startMonth": 1, "startDay": 1},
        "holidays": {"calendarRef": {"id": "ae.holidays", "version": "0.1.0"}},
        "numberSystem": "western",
        "currency": "AED",
    },
    "eg": {  # placeholder defaults, the country pack (CMP-021) is authoritative
        "timezone": "Africa/Cairo",
        "calendar": {"primary": "gregorian", "secondaryDisplay": "none"},
        "week": {"startDay": "sat", "weekendDays": ["fri", "sat"]},
        "workingTime": {
            "workDays": ["sun", "mon", "tue", "wed", "thu"],
            "hours": {"from": "09:00", "to": "17:00"},
        },
        "fiscalYear": {"type": "gregorian", "startMonth": 7, "startDay": 1},
        "holidays": {"calendarRef": {"id": "eg.holidays", "version": "0.1.0"}},
        "numberSystem": "western",
        "currency": "EGP",
    },
}


def _merge(base: dict, over: dict) -> dict:
    """Deep merge: values in `over` win; lists and scalars replace as a whole."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def resolve_locale(blueprint: Any, ctx: ValidationContext | None = None) -> dict:
    """Return company.locale with omitted fields filled from the country pack defaults.

    The pack is chosen by compliance.countryPack.id. An unknown pack adds nothing. Never raises.
    """
    bp = as_dict(blueprint)
    pack_id = as_dict(as_dict(as_dict(bp.get("compliance")).get("countryPack"))).get("id")
    table = (ctx.pack_locales if ctx and ctx.pack_locales is not None else DEFAULT_PACK_LOCALES)
    defaults = table.get(pack_id, {}) if isinstance(pack_id, str) else {}
    explicit = as_dict(as_dict(bp.get("company")).get("locale"))
    return _merge(as_dict(defaults), explicit)
