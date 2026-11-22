"""Production-only country pack certification records (CMP-035, Q-560).

These checks validate records in the trusted pack bundle, not accountant credentials or signatures.
The pack publication review must verify those; caller-supplied approval records are never accepted.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


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
        isinstance(login, str) and re.fullmatch(r"[A-Za-z0-9-]{1,39}", login) for login in reviewers
    )):
        reasons.append("manifest.json.certification.reviewedBy: must name at least one reviewer GitHub login")

    cert = evidence.get("certification")
    if not isinstance(cert, dict):
        reasons.append("evidence.json.certification: must record accountant sign-off and founder approval")
        cert = {}
    accountant = cert.get("accountant")
    if not isinstance(accountant, dict):
        reasons.append("evidence.json.certification.accountant: must be an object")
        accountant = {}
    for field in ("name", "signOffRef"):
        value = accountant.get(field)
        if not isinstance(value, str) or not value.strip():
            reasons.append(f"evidence.json.certification.accountant.{field}: must be a non-blank string")
    if accountant.get("market") != pack["countryCode"]:
        reasons.append("evidence.json.certification.accountant.market: must equal pack countryCode")
    if cert.get("founder") not in ("eldon", "partner"):
        reasons.append("evidence.json.certification.founder: must record approval by eldon or partner")
    if pack["evidenceStatus"] == "secondary" and any("accountant" in reason for reason in reasons):
        reasons.append("secondary evidence requires a named accountant sign-off for this market")
    return reasons
