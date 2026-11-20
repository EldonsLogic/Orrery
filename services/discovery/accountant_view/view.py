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
from pathlib import Path

import jsonschema

from .errors import AccountantViewError
from .money import money, percent_basis_points, to_minor

SCHEMA = Path(__file__).resolve().parents[3] / "contracts" / "blueprint.schema.json"
SECTIONS = ("chart_of_accounts", "tax_vat", "e_invoicing", "approval_thresholds", "posting_rules", "numbering")
VIEW_VERSION = "0.1.0"
_validator = None


def blueprint_digest(bp: dict) -> str:
    """SHA-256 of the canonical Blueprint. A decision is bound to this digest; any change makes it stale."""
    raw = json.dumps(bp, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def check_blueprint(bp) -> dict:
    global _validator
    if not isinstance(bp, dict):
        raise AccountantViewError("ACV-BP-001", "blueprint")
    if _validator is None:
        _validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    if next(iter(_validator.iter_errors(bp)), None) is not None:
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


def _field_types(bp):
    return {(e["id"], f["id"]): f["type"] for e in bp["entities"] for f in e["fields"]}


def _thresholds(bp, currency):
    types = _field_types(bp)
    out = []
    for rule in bp.get("approvals", []):
        ent = rule["appliesTo"]["entity"]
        conds = []
        for c in rule.get("conditions", []):
            v = c.get("value")
            if types.get((ent, c["field"])) == "money" and "value" in c and c["op"] in ("gt", "gte", "lt", "lte", "eq", "neq"):
                v = money(to_minor(v, currency), currency)
                kind = "money"
            else:
                kind = "value"
            conds.append({"field": c["field"], "op": c["op"], "kind": kind, "value": copy.deepcopy(v)})
        out.append({"id": rule["id"], "labels": copy.deepcopy(rule["labels"]), "untrustedText": True,
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
        row = {"entity": e["id"], "labels": copy.deepcopy(e["labels"]), "untrustedText": True, "configured": n is not None}
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
    currency = bp["company"].get("locale", {}).get("currency")
    pack = bp["compliance"]["countryPack"]
    thresholds = _thresholds(bp, currency)
    numbering, posting = _numbering(bp), _posting(bp)
    secs = {
        "chart_of_accounts": {"status": "not_in_blueprint", "source": {"countryPack": copy.deepcopy(pack)}},
        "tax_vat": {"status": "present", "items": _tax(bp)},
        "e_invoicing": {"status": "present", "items": _einv(bp)},
        "approval_thresholds": {"status": "present" if thresholds else "empty", "currency": currency, "rules": thresholds},
        "posting_rules": {"status": "not_in_blueprint", "implementedBy": posting},
        "numbering": {"status": "present" if numbering else "empty", "entities": numbering},
    }
    return [{"id": s, "labelKey": "acv.section." + s, **secs[s]} for s in SECTIONS]
