#!/usr/bin/env python3
"""Reviewer gate for component manifests (ADR-0034, GOV-055).

For every components/**/manifest.json that claims a reviewed level (certification.level is
reviewed, certified or regulated) the check fails when:
  - certification.reviewedBy has no usable GitHub login, or
  - owner.github appears in certification.reviewedBy (an author never reviews their own component).
Logins compare case-insensitively with a leading "@" and surrounding whitespace removed, and
must match the GitHub login charset ([A-Za-z0-9-]{1,39}); any other login fails closed.
A manifest that cannot be read, is not an object, or lacks a valid certification.level or
owner.github also fails (fail closed). Unreviewed levels (draft, tested) are not checked further.

Not covered (waits on Q-297): engine-side eligibility or certification binding on compiled artifacts.

Run: python3 scripts/check_component_reviewers.py   (standard library only; exit 1 on any problem)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEWED_LEVELS = {"reviewed", "certified", "regulated"}
UNREVIEWED_LEVELS = {"draft", "tested"}
# GitHub login charset (contracts/component.manifest.schema.json): anything else fails closed, so
# zero-width characters and Unicode lookalikes cannot hide the owner among the reviewers.
LOGIN_RE = re.compile(r"[A-Za-z0-9-]{1,39}")


def norm(login):
    return login.strip().lstrip("@").strip().casefold()


def valid_login(login):
    return LOGIN_RE.fullmatch(norm(login)) is not None


def check_manifest(data, label):
    """Return a list of problem strings (empty when the manifest is fine)."""
    if not isinstance(data, dict):
        return [f"{label}: manifest is not a JSON object"]
    cert = data.get("certification")
    if not isinstance(cert, dict):
        return [f"{label}: certification is missing or not an object"]
    level = cert.get("level")
    if not isinstance(level, str):
        return [f"{label}: certification.level {level!r} is missing or not a string"]
    if level in UNREVIEWED_LEVELS:
        return []
    if level not in REVIEWED_LEVELS:
        return [f"{label}: certification.level {level!r} is missing or unknown"]
    owner = data.get("owner")
    owner_login = owner.get("github") if isinstance(owner, dict) else None
    if not isinstance(owner_login, str) or not norm(owner_login):
        return [f"{label}: owner.github is missing or not a string"]
    if not valid_login(owner_login):
        return [f"{label}: owner.github {owner_login!r} is not a valid GitHub login"]
    raw = cert.get("reviewedBy", [])
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        return [f"{label}: certification.reviewedBy must be a list of GitHub logins"]
    problems = [f"{label}: certification.reviewedBy entry {x!r} is not a valid GitHub login"
                for x in raw if norm(x) and not valid_login(x)]
    reviewers = {norm(x) for x in raw if valid_login(x)}
    if not reviewers:
        problems.append(f"{label}: level '{level}' needs at least one login in certification.reviewedBy (ADR-0034)")
    if norm(owner_login) in reviewers:
        problems.append(f"{label}: owner.github '{owner_login}' is listed in certification.reviewedBy; "
                        "the owner cannot review their own component (ADR-0034)")
    return problems


def run(root=ROOT):
    root = Path(root)
    if not (root / "components").is_dir():
        print("FAILED: no components/ folder found; nothing to check (fail closed).")
        return 1
    manifests = sorted((root / "components").glob("**/manifest.json"))
    problems = []
    for path in manifests:
        label = path.relative_to(root).as_posix()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{label}: cannot read manifest ({type(exc).__name__})")
            continue
        problems.extend(check_manifest(data, label))
    for line in problems:
        print(line)
    if problems:
        print(f"FAILED: {len(problems)} problem(s) in {len(manifests)} manifest(s).")
        return 1
    print(f"OK: {len(manifests)} component manifest(s) checked.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
