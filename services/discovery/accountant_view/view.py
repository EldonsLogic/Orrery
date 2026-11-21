"""Accountant review view model: the finance-relevant parts of a Blueprint (0.4.0), read-only, as data and i18n keys.

Pure function of the Blueprint and the recorded decisions. It decides nothing, calls no model and never reads a
clock. Blueprint text (labels, ids) is untrusted data: it is passed as values for the screen to escape, never as
sentences. Sections the Blueprint does not carry (chart of accounts, posting rules in 0.4.0) are shown honestly as
`not_in_blueprint`; they cannot be signed off (see Q-370).
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import jsonschema

from .errors import AccountantViewError
from .money import money, percent_basis_points, to_minor

SCHEMA = Path(__file__).resolve().parents[3] / "contracts" / "blueprint.schema.json"
SECTIONS = ("chart_of_accounts", "tax_vat", "e_invoicing", "approval_thresholds", "posting_rules", "numbering")
VIEW_VERSION = "0.1.0"
_validator = None


# Control-plane fields written at every state transition and save (the state mirror and its timestamp); not the
# accountant's content. `meta.createdAt` is written once and stays bound.
# Everything else, including meta.revision and meta.id, is bound.
DIGEST_EXCLUDED = (("meta", "buildState"), ("meta", "updatedAt"))


def canonical(bp: dict) -> bytes:
    """The bytes the digest covers: the Blueprint without `DIGEST_EXCLUDED`, JSON with sorted keys, compact
    separators (`,` `:`), non-ASCII kept, no NaN or Infinity, UTF-8. `50000` and `"50000"` differ (fail-safe)."""
    body = copy.deepcopy(bp)
    for parent, key in DIGEST_EXCLUDED:
        if isinstance(body.get(parent), dict):
            body[parent].pop(key, None)
    try:
        raw = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        return raw.encode("utf-8")
    except (ValueError, TypeError, RecursionError):
        raise AccountantViewError("ACV-BP-002", "blueprint cannot be canonicalised")


def blueprint_digest(bp: dict) -> str:
    """SHA-256 of `canonical(bp)`. A decision is bound to this digest; a content change makes it stale, a
    build-state change does not."""
    return hashlib.sha256(canonical(bp)).hexdigest()


def check_blueprint(bp) -> dict:
    global _validator
    if not isinstance(bp, dict):
        raise AccountantViewError("ACV-BP-001", "blueprint")
    try:
        if _validator is None:
            _validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
        bad = next(_validator.iter_errors(bp), None) is not None
        canonical(bp)  # NaN, lone surrogates, absurd nesting: refused with a stable code
    except RecursionError:
        raise AccountantViewError("ACV-BP-002", "blueprint too deeply nested")
    if bad:
        raise AccountantViewError("ACV-BP-002", "blueprint does not match the schema")
    return bp


def _item(key, kind, value, **extra):
    return {"key": key, "labelKey": "acv.field." + key, "kind": kind, "value": value, **extra}


def _enum(key, value):
    return _item(key, "enum", value, valueLabelKey=f"acv.option.{key}.{value}")


def _tax(bp):
    vat = bp["compliance"]["vat"]
    items = [_item("vat_registered", "bool", vat["registered"])]
    if "defaultRatePercent" in vat:
        items.append(_item("vat_rate", "percent_bp", percent_basis_points(vat["defaultRatePercent"])))
    if "filingPeriod" in vat:
        items.append(_enum("vat_filing_period", vat["filingPeriod"]))
    items.append(_item("vat_prices_include", "bool", bool(vat.get("pricesIncludeVat", False))))
    items.append(_item("tax_number", "text", bp["company"].get("vatNumber"), untrustedText=True))
    items.append(_item("country_pack", "ref", bp["compliance"]["countryPack"]))
    return items


def _einv(bp):
    e = bp["compliance"]["eInvoicing"]
    items = [_enum("einv_mode", e["mode"]), _enum("einv_environment", e.get("environment", "sandbox"))]
    if "componentId" in e:
        items.append(_item("einv_component", "id", e["componentId"], untrustedText=True))
    return items


COUNTRY_CURRENCY = {"SA": "SAR", "AE": "AED", "EG": "EGP", "QA": "QAR", "BH": "BHD", "KW": "KWD", "OM": "OMR"}
_SCALARS = (str, int, bool)


def _field_type(bp, entity, path):
    """Type of `field` or `relation.field` on `entity`; None when it cannot be resolved."""
    ents = {e["id"]: e for e in bp["entities"]}
    parts = path.split(".")
    e = ents.get(entity)
    if len(parts) == 2 and e is not None:
        rel = next((r for r in e.get("relations", []) if r["id"] == parts[0]), None)
        e = ents.get(rel["target"]) if rel else None
        parts = parts[1:]
    if e is None:
        return None
    return next((f["type"] for f in e["fields"] if f["id"] == parts[0]), None)


def _cond_value(ftype, v, currency):
    """(kind, value) for one guard value. Money and percent are converted by code; a float never reaches the view
    unless it is a percent (basis points); an amount whose unit cannot be determined is `unknown_unit`."""
    if isinstance(v, list):
        if len(v) > 50:
            raise AccountantViewError("ACV-BP-004", "condition list too long")
        parts = [_cond_value(ftype, x, currency) for x in v]
        return "list", [{"kind": k, "value": x} for k, x in parts]
    if ftype == "money":
        return "money", money(to_minor(v, currency), currency)
    if ftype == "percent":
        return "percent_bp", percent_basis_points(v)
    if isinstance(v, float) or not isinstance(v, _SCALARS):
        raise AccountantViewError("ACV-BP-004", "condition value")
    if ftype is None and isinstance(v, (int, str)) and not isinstance(v, bool) and re.fullmatch(r"-?[0-9]+(\.[0-9]+)?", str(v)):
        return "unknown_unit", v
    return "value", v


def _thresholds(bp, currency):
    out = []
    for rule in bp.get("approvals", []):
        ent = rule["appliesTo"]["entity"]
        conds = []
        for c in rule.get("conditions", []):
            kind, v = (_cond_value(_field_type(bp, ent, c["field"]), c["value"], currency)
                       if "value" in c else ("none", None))
            conds.append({"field": c["field"], "op": c["op"], "kind": kind, "value": v})
        out.append({"id": rule["id"], "labels": copy.deepcopy(rule["labels"]),
                    "untrustedFields": ["id", "labels", "conditions"],
                    "entity": ent, "action": rule["appliesTo"]["action"], "conditions": conds,
                    "steps": [{"order": s["order"], "approverRole": s["approverRole"], "mode": s["mode"],
                               "timeoutHours": s.get("timeoutHours"), "escalateToRole": s.get("escalateToRole")}
                              for s in sorted(rule["steps"], key=lambda s: s["order"])],
                    "selfApproval": bool(rule.get("selfApproval", False))})
    return out


def _numbering(bp):
    out = []
    for e in bp["entities"]:
        if e.get("kind", "master") != "document" and "numbering" not in e:
            continue
        n = e.get("numbering")
        row = {"entity": e["id"], "labels": copy.deepcopy(e["labels"]), "untrustedFields": ["labels", "prefix", "example"], "configured": n is not None}
        if n is not None:
            prefix, pad = n.get("prefix", ""), n.get("padding", 1)
            row.update({"prefix": prefix, "padding": pad, "resetPerFiscalYear": bool(n.get("resetPerFiscalYear", False)),
                        "example": f"{prefix}{1:0{pad}d}"})
        out.append(row)
    return out


def _posting(bp):
    return [{"entity": e["id"], "component": c["component"], "mode": c["mode"]}
            for e in bp["entities"] for c in e.get("components", []) if c["mode"] == "implements"]


def build_sections(bp: dict) -> list:
    """The six read-only sections, without sign-off state (see `review.build_review`)."""
    currency = bp["company"].get("locale", {}).get("currency") or COUNTRY_CURRENCY.get(bp["compliance"]["country"])
    pack = bp["compliance"]["countryPack"]
    thresholds = _thresholds(bp, currency)
    numbering, posting = _numbering(bp), _posting(bp)
    secs = {
        "chart_of_accounts": {"status": "not_in_blueprint", "source": {"countryPack": copy.deepcopy(pack)}},
        "tax_vat": {"status": "present", "items": _tax(bp)},
        "e_invoicing": {"status": "present", "items": _einv(bp)},
        "approval_thresholds": {"status": "present" if thresholds else "empty", "currency": currency, "currencySource": "company" if bp["company"].get("locale", {}).get("currency") else "country_default", "rules": thresholds},
        "posting_rules": {"status": "not_in_blueprint", "implementedBy": posting},
        "numbering": {"status": "present" if numbering else "empty", "entities": numbering},
    }
    return [{"id": s, "labelKey": "acv.section." + s, **secs[s]} for s in SECTIONS]
