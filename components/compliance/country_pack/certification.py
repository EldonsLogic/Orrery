"""Production-only country pack certification records (CMP-035, Q-560).

These checks validate records in the trusted pack bundle, not accountant credentials or signatures.
The pack publication review must verify those; caller-supplied approval records are never accepted.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any
import unicodedata

from .evidence import EVIDENCE_TOP_LEVEL_KEYS, blocker_refusals, locked_fact_refusals
from .strict_json import loads_strict

MANIFEST_SCHEMA = Path(__file__).resolve().parents[3] / "contracts" / "component.manifest.schema.json"
# Trusted repo data (CMP-036): who the two founders are, and where registered components live.
LANES_FILE = Path(__file__).resolve().parents[3] / "scripts" / "lanes.json"
COMPONENTS_ROOT = Path(__file__).resolve().parents[2]
COUNTRY_PACK_DIR = Path(__file__).resolve().parent
FOUNDER_NAMES = ("eldon", "partner")


def _is_datetime(value: Any) -> bool:
    """Check the contract's RFC 3339 timestamp without jsonschema's optional format dependency."""
    if not isinstance(value, str):
        return True  # The contract's type validator reports non-strings.
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
                        r"(?:\.[0-9]+)?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])", value):
        return False
    try:
        datetime.fromisoformat(value.upper())
    except ValueError:
        return False
    return True


def _manifest_refusals(manifest: dict[str, Any]) -> list[str]:
    """Validate against the bundled contract; unavailable validation is a production refusal."""
    try:
        from jsonschema import Draft202012Validator, FormatChecker

        schema = loads_strict(MANIFEST_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        formats = FormatChecker()
        formats.checks("date-time")(_is_datetime)
        validator = Draft202012Validator(schema, format_checker=formats)
        return [f"manifest.json contract: {error.json_path}: {error.message}"
                for error in validator.iter_errors(manifest)]
    except Exception:
        # Dependency, contract and reference-resolution failures must never skip the production gate.
        return ["manifest.json: contract validation unavailable or failed"]


def _has_letter_or_digit(value: Any) -> bool:
    """Reject blank, punctuation-only and invisible placeholders after Unicode normalization."""
    if not isinstance(value, str):
        return False
    normalized = "".join(c for c in unicodedata.normalize("NFKC", value) if unicodedata.category(c) != "Cf")
    return any(c.isalnum() for c in normalized)


def _read_record(path: Path, reasons: list[str]) -> dict[str, Any]:
    """Read a companion JSON object, recording unreadable or malformed documents as refusals."""
    try:
        record = loads_strict(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        reasons.append(f"{path.name}: missing, unreadable or malformed JSON")
        return {}
    except ValueError as exc:  # malformed, duplicate keys or too-deep nesting (loads_strict)
        reasons.append(f"{path.name}: malformed JSON ({exc})")
        return {}
    if not isinstance(record, dict):
        reasons.append(f"{path.name}: must be a JSON object")
        return {}
    return record


def _founders() -> dict[str, str]:
    """Casefolded founder GitHub login -> founder name, from scripts/lanes.json; ValueError if unusable."""
    try:
        data = loads_strict(LANES_FILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"{LANES_FILE.name} unreadable") from exc
    raw = data.get("founders") if isinstance(data, dict) else None
    if not isinstance(raw, dict) or not raw:
        raise ValueError("no founders object")
    founders: dict[str, str] = {}
    for login, name in raw.items():
        if not (isinstance(login, str) and re.fullmatch(r"[A-Za-z0-9-]{1,39}", login) and name in FOUNDER_NAMES):
            raise ValueError(f"invalid founder entry {login!r}")
        if founders.setdefault(login.casefold(), name) != name:
            raise ValueError(f"login {login!r} maps to two founders")
    return founders


def _registered(directory: Path) -> tuple[set[Any], set[Any]]:
    """Ids and capabilities of registered component manifests; country packs never register themselves."""
    skipped = (COUNTRY_PACK_DIR, directory.parents[1])
    ids: set[Any] = set()
    capabilities: set[Any] = set()
    for path in COMPONENTS_ROOT.glob("**/manifest.json"):
        if any(parent in skipped for parent in path.parents):
            continue
        try:
            record = loads_strict(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            continue  # an unreadable manifest registers nothing
        if isinstance(record, dict):
            ids.add(record.get("id"))
            provides = record.get("provides")
            capabilities.update(p.get("capability") for p in provides if isinstance(p, dict)) \
                if isinstance(provides, list) else None
    return ids, capabilities


def _manifest_meaning_refusals(manifest: dict[str, Any], directory: Path) -> list[str]:
    """Values the component contract allows but a production country pack must not have (CMP-036)."""
    reasons = []
    if manifest.get("kind") != "rigid":
        reasons.append("manifest.json.kind: a country pack is a rigid component")
    cert = manifest.get("certification")
    if isinstance(cert, dict):
        if cert.get("touchesLedgerOrTax") is not True:
            reasons.append("manifest.json.certification.touchesLedgerOrTax: must be true for a country pack")
        stamp = cert.get("certifiedAt")
        try:
            certified = datetime.fromisoformat(stamp.upper()) if isinstance(stamp, str) else None
        except ValueError:
            certified = None  # the contract check above reports a malformed timestamp
        if certified is not None and certified.tzinfo is not None and certified > datetime.now(timezone.utc):
            reasons.append("manifest.json.certification.certifiedAt: is in the future")
    lifecycle = manifest.get("lifecycle")
    if isinstance(lifecycle, dict) and lifecycle.get("status") == "retired":
        reasons.append("manifest.json.lifecycle.status: a retired component cannot be used")
    requires = manifest.get("requires")
    if isinstance(requires, list):
        ids, capabilities = _registered(directory)
        for entry in requires:
            if not isinstance(entry, dict):
                continue  # the contract check reports a malformed entry
            if "component" in entry and entry["component"] not in ids:
                reasons.append(f"manifest.json.requires: component {entry['component']} is not registered")
            if "capability" in entry and entry["capability"] not in capabilities:
                reasons.append(f"manifest.json.requires: capability {entry['capability']} is not provided "
                               "by any registered component")
    return reasons


def certification_refusals(pack: dict[str, Any], directory: Path) -> list[str]:
    """Return every record refusal for the selected production pack and its exact version.

    Reviewer logins use the existing component-manifest grammar (ADR-0034). Accountant sign-off
    and founder approval live in evidence.json, so neither the pack nor component contract changes.
    Call only after pack schema validation and only for production (ADR-0059).
    """
    reasons: list[str] = []
    manifest = _read_record(directory / "manifest.json", reasons)
    evidence = _read_record(directory / "evidence.json", reasons)
    try:
        founders: dict[str, str] | None = _founders()
    except ValueError as exc:
        reasons.append(f"scripts/lanes.json founders map unusable: {exc}")
        founders = None
    reasons.extend(_manifest_refusals(manifest))
    reasons.extend(_manifest_meaning_refusals(manifest, directory))
    if set(evidence) - EVIDENCE_TOP_LEVEL_KEYS:
        reasons.append("evidence.json: unknown top-level keys are refused: "
                       + ", ".join(sorted(map(str, set(evidence) - EVIDENCE_TOP_LEVEL_KEYS))))
    reasons.extend(locked_fact_refusals(pack, evidence))
    reasons.extend(blocker_refusals(pack, evidence, None if founders is None else set(founders)))
    for filename, record, identity, expected in (
        ("manifest.json", manifest, "id", pack["componentId"]),
        ("evidence.json", evidence, "packId", pack["packId"]),
    ):
        for field, value in ((identity, expected), ("version", pack["version"])):
            if record.get(field) != value:
                reasons.append(f"{filename}.{field}: must match the selected pack ({value})")

    manifest_cert = manifest.get("certification")
    if not isinstance(manifest_cert, dict):
        reasons.append("manifest.json.certification: must be an object")
        manifest_cert = {}
    if manifest_cert.get("level") != pack["status"]:
        reasons.append("manifest.json.certification.level: must equal pack status")
    reviewers = manifest_cert.get("reviewedBy")
    if not (isinstance(reviewers, list) and reviewers and all(
        _has_letter_or_digit(login) and re.fullmatch(r"[A-Za-z0-9-]{1,39}", login) for login in reviewers
    )):
        reasons.append("manifest.json.certification.reviewedBy: must name at least one reviewer GitHub login")
    owner = manifest.get("owner")
    owner_login = owner.get("github") if isinstance(owner, dict) else None
    if founders is not None:
        if isinstance(reviewers, list) and not all(
            isinstance(login, str) and login.casefold() in founders for login in reviewers
        ):
            reasons.append("manifest.json.certification.reviewedBy: every reviewer must be a founder login "
                           "(scripts/lanes.json, ADR-0034)")
        if not (isinstance(owner_login, str) and owner_login.casefold() in founders):
            reasons.append("manifest.json.owner.github: must be a founder login (scripts/lanes.json)")
    if isinstance(owner_login, str) and isinstance(reviewers, list) and any(
        isinstance(login, str) and login.casefold() == owner_login.casefold() for login in reviewers
    ):
        reasons.append("manifest.json.certification.reviewedBy: owner cannot review their own component (ADR-0034)")

    cert = evidence.get("certification")
    if not isinstance(cert, dict):
        reasons.append("evidence.json.certification: must record accountant sign-off and founder approval")
        cert = {}
    if set(cert) - {"accountant", "founder"}:
        reasons.append("evidence.json.certification: unknown keys are refused")
    accountant_valid = True
    accountant = cert.get("accountant")
    if not isinstance(accountant, dict):
        reasons.append("evidence.json.certification.accountant: must be an object")
        accountant = {}
        accountant_valid = False
    if set(accountant) - {"name", "market", "signOffRef"}:
        reasons.append("evidence.json.certification.accountant: unknown keys are refused")
        accountant_valid = False
    for field in ("name", "signOffRef"):
        value = accountant.get(field)
        if not _has_letter_or_digit(value):
            reasons.append(f"evidence.json.certification.accountant.{field}: must contain a letter or digit")
            accountant_valid = False
    if accountant.get("market") != pack["countryCode"]:
        reasons.append("evidence.json.certification.accountant.market: must equal pack countryCode")
        accountant_valid = False
    if cert.get("founder") not in FOUNDER_NAMES:
        reasons.append("evidence.json.certification.founder: must record approval by eldon or partner")
    elif founders is not None and isinstance(owner_login, str) and owner_login.casefold() in founders \
            and founders[owner_login.casefold()] != cert["founder"]:
        reasons.append("evidence.json.certification.founder: must be the founder who owns the pack "
                       "(manifest.json.owner.github maps to a different founder)")
    if pack["evidenceStatus"] == "secondary" and not accountant_valid:
        reasons.append("secondary evidence requires a named accountant sign-off for this market")
    return reasons
