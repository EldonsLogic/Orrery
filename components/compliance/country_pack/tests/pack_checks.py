"""Shared helpers for the real country pack tests (CMP-028, CMP-029, CMP-031).

Not a test module (no `test_` prefix): `test_country_packs.py` and the per-pack modules import from it.
Every real pack version folder holds `pack.json`, `manifest.json` and `evidence.json` (per-fact sources),
plus `strings.json` only when the manifest names it in `i18n.stringsFile`.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

PACKAGE_DIR = Path(__file__).resolve().parents[1]
PACKS_DIR = PACKAGE_DIR / "packs"
REPO_ROOT = PACKAGE_DIR.parents[2]
MANIFEST_SCHEMA = REPO_ROOT / "contracts" / "component.manifest.schema.json"
BLUEPRINT_SCHEMA = REPO_ROOT / "contracts" / "blueprint.schema.json"

EVIDENCE_LABELS = {"VERIFIED-OFFICIAL", "SECONDARY", "UNVERIFIED", "PLATFORM-DEFAULT"}
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# A source whose note says it was not fetched or not read carries no access date.
UNREAD_NOTE = re.compile(r"not (fetched|read)")
# Areas whose every leaf must be backed by an evidence entry.
EVIDENCED_AREAS = ("coaTemplate", "tax", "eInvoicing", "localeDefaults", "formats", "payrollHooks", "printFormats")
# Keys that would mean a pack carries tax, ledger or invoice maths (principle 3, ADR-0031).
MATHS_KEY = re.compile(r"rate|percent|amount|formula|expression|calc|threshold|account_number|(?<![a-z])ratio", re.I)
# The only numeric leaves a pack may hold: counts and calendar positions, never money or rates.
NUMERIC_LEAVES = {
    "formats.currencyDecimals",
    "eInvoicing.archiveRetentionYears",
    "localeDefaults.fiscalYear.startMonth",
    "localeDefaults.fiscalYear.startDay",
}
# A sane upper bound for a locked retention period, so a rate or a mistyped number stands out.
MAX_RETENTION_YEARS = 10
# Pack levels allowed while any reference is pending: nothing above `tested` (CMP-034 gates on it).
UNCERTIFIABLE_LEVELS = ("draft", "tested")
SEMVER = r"\d+\.\d+\.\d+"
# Locked string values may hold digits only in these known id formats (path pattern, value check).
DIGIT_ALLOWED = [
    (re.compile(r"(^|\.)version$"), re.compile(rf"^{SEMVER}$").fullmatch),
    (re.compile(r"(^|\.)(versionRange|compatibilityRange)$"), re.compile(rf"^>={SEMVER} <{SEMVER}$").fullmatch),
    (re.compile(r"(^|\.)hours\.(from|to)$"), re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$").fullmatch),
    (re.compile(r"^tax\.(vatNumberPattern|crNumberPattern)$"), re.compile(r"^\^[^%]*\$$").fullmatch),
    (re.compile(r"^eInvoicing\.mode$"), None),  # checked against the Blueprint enum instead
]
# Free text (top-level `notes` and `name`) may hold digits only inside these tokens: record ids such as
# ADR-0033, CMP-030 or Q-559, ISO dates, semver, version labels such as v1 and phase names such as Phase 2.
# Anything else, or a `%`, fails.
FREE_TEXT_TOKENS = re.compile(rf"\b(?:[A-Z]{{1,4}}-\d+|\d{{4}}-\d{{2}}-\d{{2}}|{SEMVER}|v\d+|Phase \d)\b")
# One `provides` convention for every pack: the shared loader function, once (the manifest contract needs an
# artifact and has no data or pack type; `entity` means an engine entity id and feeds ADR-0037 risk classing).
LOADER_ARTIFACT = {"type": "function", "ref": "components.compliance.country_pack.loader.resolve_country_pack"}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def real_pack_dirs() -> list[Path]:
    """Every version folder under the real packs root that holds a pack.json."""
    return sorted(p.parent for p in PACKS_DIR.glob("*/*/pack.json"))


def load_triplet(vdir: Path) -> tuple[dict, dict, dict]:
    return tuple(read_json(vdir / n) for n in ("pack.json", "manifest.json", "evidence.json"))


def leaves(obj, prefix: str = ""):
    """(dotted path, value) for every leaf; lists are leaves."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            yield from leaves(val, f"{prefix}.{key}" if prefix else key)
    else:
        yield prefix, obj


def all_leaves(obj, prefix: str = ""):
    """Like `leaves`, but also walks lists (`name[0]`)."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            yield from all_leaves(val, f"{prefix}.{key}" if prefix else key)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            yield from all_leaves(item, f"{prefix}[{idx}]")
    else:
        yield prefix, obj


def keys(obj):
    if isinstance(obj, dict):
        for key, val in obj.items():
            yield key
            yield from keys(val)
    elif isinstance(obj, list):
        for item in obj:
            yield from keys(item)


def covered(leaf: str, paths: list[str]) -> bool:
    return any(leaf == p or leaf.startswith(f"{p}.") for p in paths)


def get(obj: dict, dotted: str):
    """Resolve a dotted path; `name[0]` indexes a list."""
    for part in dotted.split("."):
        key, _, idx = part.partition("[")
        obj = obj[key]
        if idx:
            obj = obj[int(idx.rstrip("]"))]
    return obj


def blueprint_modes() -> set[str]:
    schema = read_json(BLUEPRINT_SCHEMA)
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            einv = node.get("eInvoicing")
            if isinstance(einv, dict):
                mode = einv.get("properties", {}).get("mode", {})
                found.update(mode.get("enum", []))
            for val in node.values():
                walk(val)
        elif isinstance(node, list):
            for val in node:
                walk(val)

    walk(schema)
    return found


def rate_like_violations(pack: dict, modes: set[str]) -> list[str]:
    """Locked values, notes or names that look like a rate, an amount or an implausible period.

    Digits in a locked string are allowed only in the known id formats of DIGIT_ALLOWED; digits in the
    top-level `notes` and `name` only inside FREE_TEXT_TOKENS.
    """
    bad = []
    for area in (*EVIDENCED_AREAS, "upgradePolicy"):
        for path, val in all_leaves(pack[area], area):
            plain = re.sub(r"\[\d+\]", "", path)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                if plain not in NUMERIC_LEAVES:
                    bad.append(f"{path}: numeric leaf {val!r}")
                elif plain == "eInvoicing.archiveRetentionYears" and not 0 < val <= MAX_RETENTION_YEARS:
                    bad.append(f"{path}: retention {val!r} outside 1..{MAX_RETENTION_YEARS}")
            if not isinstance(val, str) or not re.search(r"\d", val):
                continue
            rule = next((check for pat, check in DIGIT_ALLOWED if pat.search(plain)), False)
            if rule is False:
                bad.append(f"{path}: digits in {val!r}")
            elif rule is None and val not in modes:
                bad.append(f"{path}: {val!r} is not a Blueprint e-invoicing mode")
            elif rule is not None and not rule(val):
                bad.append(f"{path}: {val!r} is not a known id format")
    for path, val in all_leaves({"notes": pack.get("notes", ""), "name": pack.get("name", {})}):
        if isinstance(val, str):
            rest = FREE_TEXT_TOKENS.sub("", val)
            if "%" in rest or re.search(r"\d", rest):
                bad.append(f"{path}: rate-like digits in free text {val!r}")
    return bad


def pending(evidence: dict) -> list:
    return [*evidence.get("pendingRefs", []), *evidence.get("goLiveBlockers", [])]


def certifiability_violations(pack: dict, manifest: dict, evidence: dict) -> list[str]:
    """While any reference is pending, neither the pack nor the manifest may claim more than `tested`."""
    if not pending(evidence):
        return []
    bad = []
    if pack["status"] not in UNCERTIFIABLE_LEVELS:
        bad.append(f"pack status {pack['status']} with pending references")
    if manifest["certification"]["level"] not in UNCERTIFIABLE_LEVELS:
        bad.append(f"manifest level {manifest['certification']['level']} with pending references")
    if pack["evidenceStatus"] != "unverified":
        bad.append(f"evidenceStatus {pack['evidenceStatus']} with pending references")
    return bad


def requires_key(entry: dict) -> tuple[str, str]:
    kind = "component" if "component" in entry else "capability"
    return kind, entry[kind]


def referenced_requirements(pack: dict, evidence: dict) -> set[tuple[str, str]]:
    """Every component the pack points at, plus every go-live blocker's requirement."""
    referenced = {
        val for path, val in leaves(pack)
        if isinstance(val, str) and (path.endswith(".componentId") or path.endswith("calendarRef.id"))
    }
    referenced.update(t["componentId"] for t in pack["printFormats"]["templates"] if t.get("componentId"))
    blocker_reqs = [b["requires"] for b in evidence.get("goLiveBlockers", []) if "requires" in b]
    return {("component", c) for c in referenced} | {requires_key(r) for r in blocker_reqs}


def repo_components() -> tuple[set[str], set[str]]:
    """Ids and capabilities of every registered component manifest outside the packs root."""
    ids, caps = set(), set()
    for path in REPO_ROOT.glob("components/**/manifest.json"):
        if PACKS_DIR in path.parents:
            continue
        manifest = read_json(path)
        ids.add(manifest.get("id"))
        caps.update(p["capability"] for p in manifest.get("provides", []))
    return ids, caps


def arabic_strings(obj, prefix: str = ""):
    """Yield (path, text) for every `ar` label, including those inside lists."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            if key == "ar" and isinstance(val, str):
                yield path, val
            else:
                yield from arabic_strings(val, path)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            yield from arabic_strings(item, f"{prefix}[{idx}]")
