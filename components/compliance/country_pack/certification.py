"""Production-only country pack certification records (CMP-035, Q-560).

These checks validate records in the trusted pack bundle, not accountant credentials or signatures.
The pack publication review must verify those; caller-supplied approval records are never accepted.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any
import unicodedata

from .evidence import locked_fact_refusals

MANIFEST_SCHEMA = Path(__file__).resolve().parents[3] / "contracts" / "component.manifest.schema.json"


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

        schema = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))
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
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        reasons.append(f"{path.name}: missing, unreadable or malformed JSON")
        return {}
    if not isinstance(record, dict):
        reasons.append(f"{path.name}: must be a JSON object")
        return {}
    return record


def certification_refusals(pack: dict[str, Any], directory: Path) -> list[str]:
    """Return every record refusal for the selected production pack and its exact version.

    Reviewer logins use the existing component-manifest grammar (ADR-0034). Accountant sign-off
    and founder approval live in evidence.json, so neither the pack nor component contract changes.
    Call only after pack schema validation and only for production (ADR-0059).
    """
    reasons: list[str] = []
    manifest = _read_record(directory / "manifest.json", reasons)
    evidence = _read_record(directory / "evidence.json", reasons)
    reasons.extend(_manifest_refusals(manifest))
    reasons.extend(locked_fact_refusals(pack, evidence))
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
    if cert.get("founder") not in ("eldon", "partner"):
        reasons.append("evidence.json.certification.founder: must record approval by eldon or partner")
    if pack["evidenceStatus"] == "secondary" and not accountant_valid:
        reasons.append("secondary evidence requires a named accountant sign-off for this market")
    return reasons
