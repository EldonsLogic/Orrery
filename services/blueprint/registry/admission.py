"""Admission rules. Fail closed: a manifest with any error is not admitted. Manifest content is data only."""
from __future__ import annotations

import json
from functools import cmp_to_key, lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from validator import semver
from validator.schema_step import _formats  # same date / date-time checks the validator uses

from . import issues as codes
from .issues import Issue, sort_issues
from .store import RawManifest

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts" / "component.manifest.schema.json"
MAX_SCHEMA_ERRORS = 20
_NO_LICENCE = {"", "NOASSERTION", "NONE", "UNKNOWN"}


@lru_cache(maxsize=2)
def _validator(path: str) -> Draft202012Validator:
    with open(path, encoding="utf-8") as fh:
        return Draft202012Validator(json.load(fh), format_checker=_formats)


def subject_of(m: dict, fallback: str) -> str:
    cid, ver = m.get("id"), m.get("version")
    return f"{cid}@{ver}" if isinstance(cid, str) and isinstance(ver, str) else fallback


def _canonical(m: dict) -> str:
    return json.dumps(m, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _schema_issues(raw: RawManifest, schema_path: str) -> list[Issue]:
    errs = sorted(_validator(schema_path).iter_errors(raw.data), key=lambda e: [str(p) for p in e.absolute_path])
    out = []
    for e in errs[:MAX_SCHEMA_ERRORS]:
        where = "/" + "/".join(str(p) for p in e.absolute_path)
        msg = e.message if len(e.message) <= 160 else e.message[:157] + "..."
        out.append(Issue(codes.SCHEMA, codes.ERROR, raw.name, f"{where}: {msg}"))
    if len(errs) > MAX_SCHEMA_ERRORS:
        out.append(Issue(codes.SCHEMA, codes.ERROR, raw.name, f"{len(errs) - MAX_SCHEMA_ERRORS} more schema errors not shown"))
    return out


def _single_checks(m: dict, raw: RawManifest, subj: str) -> list[Issue]:
    """Checks on one schema-valid manifest."""
    out: list[Issue] = []

    def err(code, msg):
        out.append(Issue(code, codes.ERROR, subj, msg))

    if raw.name_id is not None and raw.name_id != m["id"]:
        err(codes.FILE, f"file name id '{raw.name_id}' differs from manifest id '{m['id']}'")
    if raw.name_version is not None and raw.name_version != m["version"]:
        err(codes.FILE, f"file name version '{raw.name_version}' differs from manifest version '{m['version']}'")

    lic = m["licence"]
    if lic["spdx"].strip().upper() in _NO_LICENCE:
        err(codes.LICENCE, "licence is not recorded (licence.spdx is empty or NOASSERTION)")
    for tp in lic.get("thirdParty", []):
        spdx = tp["spdx"].strip()
        if spdx.upper() in _NO_LICENCE:
            err(codes.LICENCE, f"third-party licence for '{tp['name']}' is not recorded")
        elif "AGPL" in spdx.upper():
            err(codes.COPYLEFT, f"third-party '{tp['name']}' is {spdx}; AGPL is not accepted without an ADR")
        elif any(k in spdx.upper() for k in ("GPL", "SSPL", "EUPL", "MPL", "CC-BY-SA")) and not lic.get("copyleftReviewed", False):
            err(codes.COPYLEFT, f"third-party '{tp['name']}' is {spdx}; copyleftReviewed must be true")

    cert = m["certification"]
    level = cert["level"]
    blocking = [t for t in m["tests"] if t["blocking"]]
    kinds = {e["kind"] for e in cert.get("evidence", [])}
    if level in ("certified", "regulated") and blocking and "ci_run" not in kinds:
        err(codes.EVIDENCE, f"level '{level}' with blocking tests needs certification evidence of kind 'ci_run'")
    if level == "regulated" and any(t["kind"] == "compliance_sandbox" for t in blocking) and "compliance_sandbox" not in kinds:
        err(codes.EVIDENCE, "level 'regulated' with a blocking compliance_sandbox test needs evidence of kind 'compliance_sandbox'")
    if level == "draft":
        out.append(Issue(codes.DRAFT, codes.WARNING, subj, "draft level: admitted, not usable by tenants"))
    return out


def _check_requires(admitted: list[dict], strict: bool) -> tuple[set[int], list[Issue]]:
    """Cross checks against the other admitted manifests. Returns indexes to reject and the findings."""
    by_id: dict[str, list[dict]] = {}
    for m in admitted:
        by_id.setdefault(m["id"], []).append(m)
    reject: set[int] = set()
    out: list[Issue] = []
    for idx, m in enumerate(admitted):
        subj = f"{m['id']}@{m['version']}"
        for req in m["requires"]:
            rng = req["versionRange"]
            if "component" in req:
                what, cands = f"component '{req['component']}'", by_id.get(req["component"], [])
            else:
                cap = req["capability"]
                what = f"capability '{cap}'"
                cands = [o for o in admitted if o["id"] != m["id"]
                         and any(p["capability"] == cap for p in o["provides"])]
            if not cands:
                sev = codes.ERROR if strict else codes.WARNING
                out.append(Issue(codes.REQ_UNKNOWN, sev, subj, f"requires {what}, which is not in the registry"))
                if strict:
                    reject.add(idx)
                continue
            try:
                ok = any(semver.satisfies(o["version"], rng) for o in cands)
            except ValueError:
                out.append(Issue(codes.REQ_UNSAT, codes.ERROR, subj, f"requires {what}: version range '{rng}' is not valid"))
                reject.add(idx)
                continue
            if not ok:
                have = ", ".join(sorted(o["version"] for o in cands))
                out.append(Issue(codes.REQ_UNSAT, codes.ERROR, subj,
                                 f"requires {what} {rng}, but no registry version satisfies it (available: {have})"))
                reject.add(idx)
    return reject, out


def admit(raws: list[RawManifest], strict: bool = False, schema_path: str | Path | None = None) -> tuple[list[dict], list[Issue]]:
    """Return (admitted manifests sorted by id then version, findings sorted). Never raises for bad input."""
    sp = str(schema_path or SCHEMA_PATH)
    found: list[Issue] = []
    ok: list[tuple[RawManifest, dict]] = []
    for raw in raws:
        found.extend(raw.issues)
        if raw.data is None:
            continue
        try:
            errs = _schema_issues(raw, sp)
        except Exception as exc:  # fail closed on anything unexpected
            errs = [Issue(codes.SCHEMA, codes.ERROR, raw.name, f"schema check could not run ({type(exc).__name__})")]
        if errs:
            found.extend(errs)
            continue
        subj = subject_of(raw.data, raw.name)
        single = _single_checks(raw.data, raw, subj)
        found.extend(single)
        if not any(i.is_error for i in single):
            ok.append((raw, raw.data))

    groups: dict[tuple[str, str], list[dict]] = {}
    for _, m in ok:
        groups.setdefault((m["id"], m["version"]), []).append(m)
    unique: list[dict] = []
    for (cid, ver), ms in sorted(groups.items()):
        if len({_canonical(m) for m in ms}) > 1:
            found.append(Issue(codes.DUPLICATE, codes.ERROR, f"{cid}@{ver}",
                               f"{len(ms)} manifests with the same id and version have different content; none admitted"))
        else:
            unique.append(ms[0])

    reject, req_issues = _check_requires(unique, strict)
    found.extend(req_issues)
    admitted = [m for i, m in enumerate(unique) if i not in reject]
    admitted.sort(key=_order_key)
    return admitted, sort_issues(found)


def version_key(version: str):
    """Sort key for semver version strings (precedence order)."""
    return cmp_to_key(semver.compare)(semver.parse_version(version))


def _order_key(m: dict):
    return (m["id"], version_key(m["version"]))
