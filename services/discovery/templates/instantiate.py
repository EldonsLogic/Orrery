#!/usr/bin/env python3
"""Instantiate a Discovery template Blueprint for one company (DSC-002).

    instantiate(template_path, answers) -> Blueprint dict

Pure data transformation: reads the template files, returns a new dict, never writes, never evals,
never formats strings with user input. Standard library only.

CLI (prints to stdout unless --out is given; never writes into the repo by default):
    python3 services/discovery/templates/instantiate.py --country sa --name-ar NAME --name-en NAME [--out PATH]
"""
from __future__ import annotations

import argparse
import copy
import datetime
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------------------------
ANSWER_KEYS = {
    "name_ar", "name_en", "country", "branches", "currency", "vat_registered", "languages",
    "vat_number", "cr_number",
}
REQUIRED_KEYS = {"name_ar", "name_en", "country"}
MAX_NAME = 120
MAX_BRANCHES = 50

# PLACEHOLDER country values for the compliance block. The country pack (CMP-021) is authoritative
# and the numbers below are NOT tax logic: they only fill schema-required fields until the pack
# exists. UNVERIFIED for ae and eg (the e-invoicing modes are contract placeholders too).
COUNTRIES: dict[str, dict[str, Any]] = {
    "sa": {"code": "SA", "einvoicing": "zatca_phase2", "component": "compliance.zatca_sa",
           "vat_rate": 15, "filing": "monthly", "hijri": True},
    "ae": {"code": "AE", "einvoicing": "uae_e_invoicing", "component": None,
           "vat_rate": 5, "filing": "quarterly", "hijri": False},
    "eg": {"code": "EG", "einvoicing": "eg_e_invoice", "component": None,
           "vat_rate": 14, "filing": "monthly", "hijri": False},
}
ZATCA_COMPONENT = "compliance.zatca_sa"
ZATCA_FIELD_PREFIX = "zatca_"
NAME_TOKEN = "{{company.name}}"
LOCALES = ("ar", "en")


class InstantiationError(ValueError):
    """The answers or the template cannot produce a Blueprint. Nothing is returned."""


def _check_scalar(key: str, v: Any) -> None:
    if isinstance(v, bool) or isinstance(v, str):
        return
    if isinstance(v, (int, float)):
        if isinstance(v, float) and not math.isfinite(v):
            raise InstantiationError(f"answer '{key}': number must be finite")
        return
    raise InstantiationError(f"answer '{key}': only strings, numbers, booleans and lists of those are accepted")


def check_answers(answers: Any) -> dict[str, Any]:
    """Validate shape and values of the answers; return a normalised copy."""
    if not isinstance(answers, dict):
        raise InstantiationError("answers must be a dict")
    unknown = sorted(str(k) for k in answers if k not in ANSWER_KEYS)
    if unknown:
        raise InstantiationError("unknown answer key(s): " + ", ".join(unknown))
    for key, v in answers.items():
        if isinstance(v, list):
            for item in v:
                _check_scalar(key, item)  # a nested list or dict fails here
        else:
            _check_scalar(key, v)
    missing = sorted(REQUIRED_KEYS - set(answers))
    if missing:
        raise InstantiationError("missing answer(s): " + ", ".join(missing))
    out: dict[str, Any] = {}
    for key in ("name_ar", "name_en"):
        v = answers[key]
        if not isinstance(v, str) or not v.strip():
            raise InstantiationError(f"answer '{key}': a non-empty string is required")
        v = v.strip()
        if len(v) > MAX_NAME:
            raise InstantiationError(f"answer '{key}': longer than {MAX_NAME} characters")
        if "{" in v or "}" in v or any(ord(c) < 32 for c in v):
            raise InstantiationError(f"answer '{key}': braces and control characters are not allowed")
        out[key] = v
    country = answers["country"]
    if not isinstance(country, str) or country.strip().lower() not in COUNTRIES:
        raise InstantiationError("answer 'country': must be one of sa, ae, eg")
    out["country"] = country.strip().lower()
    b = answers.get("branches", 1)
    if isinstance(b, bool) or not isinstance(b, (int, float)) or int(b) != b or not 1 <= b <= MAX_BRANCHES:
        raise InstantiationError(f"answer 'branches': a whole number from 1 to {MAX_BRANCHES}")
    out["branches"] = int(b)
    vr = answers.get("vat_registered", False)
    if not isinstance(vr, bool):
        raise InstantiationError("answer 'vat_registered': true or false")
    out["vat_registered"] = vr
    if "currency" in answers:
        c = answers["currency"]
        if not isinstance(c, str) or not re.fullmatch(r"[A-Z]{3}", c.strip().upper()):
            raise InstantiationError("answer 'currency': a three-letter ISO 4217 code")
        out["currency"] = c.strip().upper()
    langs = answers.get("languages", ["ar", "en"])
    if isinstance(langs, str):
        langs = [langs]
    if (not isinstance(langs, list) or not langs or len(set(langs)) != len(langs)
            or any(x not in LOCALES for x in langs) or "ar" not in langs):
        raise InstantiationError("answer 'languages': a list of ar and/or en, without duplicates, containing ar")
    out["languages"] = list(langs)
    for key, pattern, label in (("vat_number", r"[0-9]{15}", "15 digits"), ("cr_number", r"[0-9]{10}", "10 digits")):
        if key in answers:
            v = answers[key]
            if not isinstance(v, str) or not re.fullmatch(pattern, v.strip()):
                raise InstantiationError(f"answer '{key}': {label}")
            out[key] = v.strip()
    if "vat_number" in out and not out["vat_registered"]:
        raise InstantiationError("answers contradict: vat_number given but vat_registered is false")
    return out


# ---------------------------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------------------------
def load_template(template_path: str | Path) -> dict:
    """Read the template and splice its {"$include": "parts/x.json"} items (arrays) in place.

    Includes are resolved only below the template folder, one level deep. Returns a fresh dict on
    every call, so callers can never share state with another call.
    """
    path = Path(template_path)
    base = path.resolve().parent
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise InstantiationError("template root must be an object")
    for key, value in list(doc.items()):
        if not isinstance(value, list):
            continue
        items: list[Any] = []
        for item in value:
            if isinstance(item, dict) and set(item) == {"$include"}:
                target = (base / str(item["$include"])).resolve()
                if base not in target.parents or target.suffix != ".json":
                    raise InstantiationError(f"include outside the template folder: {item['$include']}")
                part = json.loads(target.read_text(encoding="utf-8"))
                if not isinstance(part, list):
                    raise InstantiationError(f"include must hold an array: {item['$include']}")
                items.extend(part)
            else:
                items.append(item)
        doc[key] = items
    return doc


# ---------------------------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------------------------
def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:48].strip("-") or "company"


def _fill_placeholders(node: Any, names: dict[str, str]) -> Any:
    if isinstance(node, dict):
        is_text = bool(node) and set(node) <= set(LOCALES) and all(isinstance(v, str) for v in node.values())
        out = {}
        for k, v in node.items():
            if is_text:
                out[k] = v.replace(NAME_TOKEN, names[k])
            else:
                out[k] = _fill_placeholders(v, names)
        return out
    if isinstance(node, list):
        return [_fill_placeholders(v, names) for v in node]
    return node


def _find_placeholders(node: Any, path: str = "") -> list[str]:
    if isinstance(node, dict):
        return [p for k, v in node.items() for p in _find_placeholders(v, f"{path}/{k}")]
    if isinstance(node, list):
        return [p for i, v in enumerate(node) for p in _find_placeholders(v, f"{path}/{i}")]
    if isinstance(node, str) and ("{{" in node or "}}" in node):
        return [path]
    return []


def _locations(tmpl_locs: list[dict], n: int) -> list[dict]:
    locs = copy.deepcopy(tmpl_locs)
    for i in range(2, n + 1):
        locs.append({"id": f"branch_{i}", "kind": "branch",
                     "labels": {"ar": f"الفرع {i}", "en": f"Branch {i}"}})
        locs.append({"id": f"wh_{i}", "kind": "warehouse",
                     "labels": {"ar": f"مستودع الفرع {i}", "en": f"Branch {i} warehouse"}, "parent": f"branch_{i}"})
    return locs


def _rebuild_location_selects(bp: dict, tmpl_locs: list[dict], new_locs: list[dict]) -> None:
    """Select fields that list every location of one kind get their options from the final locations."""
    old = {k: {x["id"] for x in tmpl_locs if x["kind"] == k} for k in ("branch", "warehouse")}
    for ent in bp["entities"]:
        for f in ent.get("fields", []):
            vals = {o.get("value") for o in f.get("options", [])}
            for kind, ids in old.items():
                if f.get("type") == "select" and vals and vals == ids:
                    f["options"] = [{"value": x["id"], "labels": copy.deepcopy(x["labels"])}
                                    for x in new_locs if x["kind"] == kind]


def instantiate(template_path: str | Path, answers: dict, now: str | None = None) -> dict:
    """Return a new Blueprint dict (draft) for the company described by `answers`.

    answers keys (all values strings, numbers, booleans or lists of those): name_ar, name_en and
    country (sa, ae, eg) are required; branches (default 1), currency, vat_registered (default
    false), languages (default ["ar", "en"]), vat_number, cr_number are optional. Unknown keys,
    other value types and contradictions raise InstantiationError. Country-pack differences are
    limited to the compliance block (placeholders, see COUNTRIES); locale values are left out so
    they resolve from the pack.
    """
    a = check_answers(answers)
    bp = load_template(template_path)  # fresh object: the template is never modified
    bp.pop("$schema", None)  # the template's relative schema path means nothing next to the output
    ctry = COUNTRIES[a["country"]]
    tmpl_locs = copy.deepcopy(bp["locations"])

    # meta
    stamp = now or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    bp["meta"]["id"] = f"bp-{a['country']}-{_slug(a['name_en'])}"[:64].rstrip("-")
    bp["meta"]["createdAt"] = stamp
    bp["meta"]["updatedAt"] = stamp
    bp["meta"]["defaultLocale"] = a["languages"][0]

    # company
    comp = bp["company"]
    comp["country"] = ctry["code"]
    comp["languages"] = {"primary": a["languages"][0]}
    if a["languages"][1:]:
        comp["languages"]["secondary"] = a["languages"][1:]
    if "currency" in a:
        comp["locale"] = {**comp.get("locale", {}), "currency": a["currency"]}
    if "cr_number" in a:
        comp["crNumber"] = a["cr_number"]
    if "vat_number" in a:
        comp["vatNumber"] = a["vat_number"]

    # locations, location selects, scopes
    bp["locations"] = _locations(tmpl_locs, a["branches"])
    _rebuild_location_selects(bp, tmpl_locs, bp["locations"])
    wh_ids = [x["id"] for x in bp["locations"] if x["kind"] == "warehouse"]
    for role in bp["roles"]:
        if role.get("scope", {}).get("type") == "warehouse":
            role["scope"]["values"] = list(wh_ids)

    # compliance (placeholders from COUNTRIES, never tax logic)
    old_c = bp["compliance"]
    use_zatca = a["vat_registered"] and ctry["component"] == ZATCA_COMPONENT
    comp_block: dict[str, Any] = {
        "country": ctry["code"], "countryPack": {"id": a["country"], "version": old_c["countryPack"]["version"]},
        "hijriDisplay": {"enabled": ctry["hijri"], "primary": "gregorian"},
        "documentLanguages": list(a["languages"]),
    }
    if a["vat_registered"]:
        eInv: dict[str, Any] = {"mode": ctry["einvoicing"], "environment": "sandbox"}
        if ctry["component"] and use_zatca:
            eInv["componentId"] = ctry["component"]
        comp_block["eInvoicing"] = eInv
        comp_block["vat"] = {"registered": True, "defaultRatePercent": ctry["vat_rate"],
                             "filingPeriod": ctry["filing"], "pricesIncludeVat": False}
    else:
        comp_block["eInvoicing"] = {"mode": "none"}
        comp_block["vat"] = {"registered": False}
    if "payroll" in old_c:
        comp_block["payroll"] = copy.deepcopy(old_c["payroll"])
    bp["compliance"] = comp_block
    bp["i18n"]["defaultLocale"] = a["languages"][0]

    if not use_zatca:  # e-invoicing component, its bindings and its fields only travel with ZATCA
        bp["components"] = [c for c in bp["components"] if c["id"] != ZATCA_COMPONENT]
        for ent in bp["entities"]:
            ent["components"] = [c for c in ent.get("components", []) if c.get("component") != ZATCA_COMPONENT]
            ent["fields"] = [f for f in ent["fields"] if not f["id"].startswith(ZATCA_FIELD_PREFIX)]

    # placeholders last, then fail closed on anything left over
    bp = _fill_placeholders(bp, {"ar": a["name_ar"], "en": a["name_en"]})
    left = _find_placeholders(bp)
    if left:
        raise InstantiationError("unfilled placeholder at " + ", ".join(left[:5]))
    return bp


# ---------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------
DEFAULT_TEMPLATE = Path(__file__).resolve().parent / "trading-distribution" / "blueprint.template.json"


def _yes_no(text: str) -> bool:
    t = text.strip().lower()
    if t in ("yes", "y", "true", "1"):
        return True
    if t in ("no", "n", "false", "0"):
        return False
    raise argparse.ArgumentTypeError("use yes or no")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Instantiate the trading and distribution template.")
    ap.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE, help="path to blueprint.template.json")
    ap.add_argument("--country", required=True, help="sa, ae or eg")
    ap.add_argument("--name-ar", required=True)
    ap.add_argument("--name-en", required=True)
    ap.add_argument("--branches", type=int)
    ap.add_argument("--currency")
    ap.add_argument("--vat-registered", type=_yes_no, help="yes or no (default no until confirmed)")
    ap.add_argument("--vat-number")
    ap.add_argument("--cr-number")
    ap.add_argument("--languages", help="comma separated, for example ar,en")
    ap.add_argument("--out", type=Path, help="write the Blueprint here instead of stdout")
    args = ap.parse_args(argv)
    answers: dict[str, Any] = {"country": args.country, "name_ar": args.name_ar, "name_en": args.name_en}
    for key, val in (("branches", args.branches), ("currency", args.currency), ("vat_registered", args.vat_registered),
                     ("vat_number", args.vat_number), ("cr_number", args.cr_number)):
        if val is not None:
            answers[key] = val
    if args.languages:
        answers["languages"] = [x.strip() for x in args.languages.split(",") if x.strip()]
    try:
        bp = instantiate(args.template, answers)
    except (InstantiationError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    text = json.dumps(bp, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        try:
            args.out.write_text(text, encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot write {args.out} ({type(exc).__name__})", file=sys.stderr)
            return 1
    else:
        sys.stdout.write(text)
    unconfirmed = [k for k in ("branches", "vat_registered", "languages") if k not in answers]
    if unconfirmed:
        print("note: defaults used for " + ", ".join(unconfirmed) + "; confirm with the owner (questions.json)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
