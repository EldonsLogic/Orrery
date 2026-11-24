"""Country pack loader, schema/invariant validator, and fail-closed override merger (CMP-021)."""

from __future__ import annotations

import copy
from datetime import date
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional when jsonschema is not installed
    Draft202012Validator = None

SCHEMA_PATH = Path(__file__).resolve().parent / "pack.schema.json"
COUNTRY_CODE_RE = re.compile(r"^[A-Za-z]{2}$")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")
WEEKDAYS = frozenset({"mon", "tue", "wed", "thu", "fri", "sat", "sun"})
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class CountryPackError(ValueError):
    """Base error for country pack loading, validation, and override resolution."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or [message]


class UnknownCountryError(CountryPackError):
    """Raised when a country code is invalid or no pack directory exists for it."""


class PackNotFoundError(CountryPackError):
    """Raised when a requested pack version or pack.json file is missing."""


class PackValidationError(CountryPackError):
    """Raised when a country pack manifest fails schema or invariant validation."""


class OverrideRejectedError(CountryPackError):
    """Raised when company overrides target a locked/unknown path or violate constraints."""


def _is_int(val: Any) -> bool:
    return isinstance(val, int) and not isinstance(val, bool)


def _is_num(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def _load_schema(schema_path: Path | None = None) -> dict[str, Any]:
    path = schema_path or SCHEMA_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_ref(ref: str, root_schema: dict[str, Any]) -> dict[str, Any]:
    node: Any = root_schema
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def _check_schema_node(val: Any, schema: dict[str, Any], root: dict[str, Any], path: str, errors: list[str]) -> None:
    if "$ref" in schema:
        schema = _resolve_ref(schema["$ref"], root)
    if "const" in schema and val != schema["const"]:
        errors.append(f"{path}: expected {schema['const']!r}")
        return
    if "enum" in schema and val not in schema["enum"]:
        errors.append(f"{path}: value {val!r} not in {schema['enum']}")
        return
    expected_types = schema.get("type")
    if expected_types is not None:
        types = expected_types if isinstance(expected_types, list) else [expected_types]
        ok = False
        for t in types:
            if t == "null" and val is None:
                ok = True
            elif t == "boolean" and isinstance(val, bool):
                ok = True
            elif t == "integer" and _is_int(val):
                ok = True
            elif t == "number" and _is_num(val):
                ok = True
            elif t == "string" and isinstance(val, str):
                ok = True
            elif t == "array" and isinstance(val, list):
                ok = True
            elif t == "object" and isinstance(val, dict):
                ok = True
        if not ok:
            errors.append(f"{path}: expected type {expected_types}, got {type(val).__name__}")
            return
    if isinstance(val, str):
        if "minLength" in schema and len(val) < schema["minLength"]:
            errors.append(f"{path}: string shorter than {schema['minLength']}")
        if "maxLength" in schema and len(val) > schema["maxLength"]:
            errors.append(f"{path}: string longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], val):
            errors.append(f"{path}: '{val}' does not match pattern {schema['pattern']}")
    elif _is_num(val):
        if "minimum" in schema and val < schema["minimum"]:
            errors.append(f"{path}: {val} < minimum {schema['minimum']}")
        if "maximum" in schema and val > schema["maximum"]:
            errors.append(f"{path}: {val} > maximum {schema['maximum']}")
    elif isinstance(val, list):
        if "minItems" in schema and len(val) < schema["minItems"]:
            errors.append(f"{path}: expected at least {schema['minItems']} item(s)")
        if "maxItems" in schema and len(val) > schema["maxItems"]:
            errors.append(f"{path}: expected at most {schema['maxItems']} item(s)")
        if schema.get("uniqueItems") and len(val) != len({json.dumps(x, sort_keys=True) for x in val}):
            errors.append(f"{path}: duplicate items are not allowed")
        if "items" in schema:
            for idx, item in enumerate(val):
                _check_schema_node(item, schema["items"], root, f"{path}[{idx}]", errors)
    elif isinstance(val, dict):
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in val:
                errors.append(f"{path}.{req}: missing required property")
        addl = schema.get("additionalProperties", True)
        for k, v in val.items():
            if k in props:
                _check_schema_node(v, props[k], root, f"{path}.{k}", errors)
            elif addl is False:
                errors.append(f"{path}.{k}: unexpected property")
            elif isinstance(addl, dict):
                _check_schema_node(v, addl, root, f"{path}.{k}", errors)


def _path_overlaps(a: str, b: str) -> bool:
    return a == b or a.startswith(f"{b}.") or b.startswith(f"{a}.")


def _check_working_time(locale: dict[str, Any], errors: list[str], prefix: str) -> None:
    weekend_raw = locale.get("week", {}).get("weekendDays", [])
    weekend = set(weekend_raw) if isinstance(weekend_raw, list) else set()
    wt = locale.get("workingTime", {})
    work_days = wt.get("workDays", [])
    if isinstance(work_days, list):
        overlap = sorted(set(work_days) & weekend)
        if overlap:
            errors.append(f"{prefix}.workingTime.workDays overlaps weekendDays: {', '.join(overlap)}")
    hours = wt.get("hours", {})
    if isinstance(hours, dict):
        h_from, h_to = hours.get("from", ""), hours.get("to", "")
        if isinstance(h_from, str) and isinstance(h_to, str) and not h_from < h_to:
            errors.append(f"{prefix}.workingTime.hours: from ({h_from}) must be before to ({h_to})")
    reduced = wt.get("reducedPeriods")
    if reduced is not None and not isinstance(reduced, list):
        errors.append(f"{prefix}.workingTime.reducedPeriods: must be a list")
        return
    fixed_spans: list[tuple[date, date, int]] = []
    for idx, rp in enumerate(reduced or []):
        if not isinstance(rp, dict) or not isinstance(rp.get("hours"), dict):
            errors.append(f"{prefix}.workingTime.reducedPeriods[{idx}]: invalid entry")
            continue
        rf, rt = rp["hours"].get("from", ""), rp["hours"].get("to", "")
        if not (isinstance(rf, str) and isinstance(rt, str) and TIME_RE.match(rf) and TIME_RE.match(rt) and rf < rt):
            errors.append(f"{prefix}.workingTime.reducedPeriods[{idx}].hours: invalid range")
        if rp.get("rule", "ramadan") == "fixed_dates":
            try:
                d_from = date.fromisoformat(str(rp.get("gregorianFrom", "")))
                d_to = date.fromisoformat(str(rp.get("gregorianTo", "")))
            except ValueError:
                errors.append(f"{prefix}.workingTime.reducedPeriods[{idx}]: invalid fixed_dates ISO dates")
                continue
            if d_from > d_to:
                errors.append(f"{prefix}.workingTime.reducedPeriods[{idx}]: gregorianFrom after gregorianTo")
            else:
                for prev_a, prev_b, prev_i in fixed_spans:
                    if d_from <= prev_b and prev_a <= d_to:
                        errors.append(f"{prefix}.workingTime.reducedPeriods[{idx}] overlaps [{prev_i}]")
                fixed_spans.append((d_from, d_to, idx))


def validate_pack(pack: Any, schema_path: Path | None = None) -> list[str]:
    """Validate a country pack manifest against the schema and cross-field invariants."""
    if not isinstance(pack, dict):
        return ["pack: manifest must be a JSON object"]
    schema = _load_schema(schema_path)
    errors: list[str] = []
    if Draft202012Validator is not None:
        for err in sorted(Draft202012Validator(schema).iter_errors(pack), key=lambda e: list(e.absolute_path)):
            loc = ".".join(map(str, err.absolute_path)) or "pack"
            errors.append(f"{loc}: {err.message}")
    else:
        _check_schema_node(pack, schema, schema, "pack", errors)
    if errors:
        return errors

    cc_lower = pack["countryCode"].lower()
    if pack["packId"] != cc_lower:
        errors.append(f"packId '{pack['packId']}' must match countryCode '{pack['countryCode']}'")
    if pack["componentId"] != f"country.{pack['packId']}":
        errors.append(f"componentId '{pack['componentId']}' must equal 'country.{pack['packId']}'")

    loc = pack["localeDefaults"]
    if loc["currency"] != pack["formats"]["currency"]:
        errors.append("localeDefaults.currency must match formats.currency")
    cal_id = loc["holidays"]["calendarRef"]["id"]
    if not cal_id.startswith(f"{pack['packId']}."):
        errors.append(f"holidays.calendarRef.id '{cal_id}' must start with '{pack['packId']}.'")
    try:
        ZoneInfo(loc["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        errors.append(f"localeDefaults.timezone '{loc['timezone']}' is not a valid IANA zone")

    _check_working_time(loc, errors, "localeDefaults")

    for pat_key in ("vatNumberPattern", "crNumberPattern"):
        try:
            re.compile(pack["tax"][pat_key])
        except re.error as exc:
            errors.append(f"tax.{pat_key}: invalid regex ({exc})")

    einv = pack["eInvoicing"]
    if einv["required"] and (einv["mode"] == "none" or not einv["mandatoryDocumentLanguages"]):
        errors.append("eInvoicing.required=true demands mode != 'none' and mandatoryDocumentLanguages")

    policy = pack["overridesPolicy"]
    for ov in policy["overridablePaths"]:
        for lk in policy["lockedPaths"]:
            if _path_overlaps(ov, lk):
                errors.append(f"overridesPolicy conflict: '{ov}' overlaps locked path '{lk}'")
    return errors


def validate_pack_or_raise(pack: Any, schema_path: Path | None = None) -> None:
    errors = validate_pack(pack, schema_path=schema_path)
    if errors:
        raise PackValidationError(f"Invalid country pack ({len(errors)} error(s)): {errors[0]}", errors=errors)


def _semver_key(version: str) -> tuple[int, int, int, int, str] | None:
    m = SEMVER_RE.match(version)
    if not m:
        return None
    major, minor, patch, pre = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
    return (major, minor, patch, 1 if pre is None else 0, pre or "")


def load_country_pack(country_code: str, packs_dir: Path, version: str | None = None) -> dict[str, Any]:
    """Load and validate a country pack from `<packs_dir>/<country>/<version>/pack.json`."""
    if not isinstance(country_code, str) or not COUNTRY_CODE_RE.match(country_code.strip()):
        raise UnknownCountryError(f"Invalid or missing country code: {country_code!r}")
    code_upper = country_code.strip().upper()
    country_dir = Path(packs_dir) / code_upper.lower()
    if not country_dir.is_dir():
        raise UnknownCountryError(f"Unknown country '{code_upper}': no pack directory at {country_dir}")

    if version is not None:
        if not isinstance(version, str) or _semver_key(version.strip()) is None:
            raise PackNotFoundError(f"Invalid pack version '{version}' for country '{code_upper}'")
        chosen_version = version.strip()
        pack_file = country_dir / chosen_version / "pack.json"
        if not pack_file.is_file():
            raise PackNotFoundError(f"Pack {code_upper}@{chosen_version} not found at {pack_file}")
    else:
        candidates = []
        for entry in country_dir.iterdir():
            if entry.is_dir() and (entry / "pack.json").is_file():
                key = _semver_key(entry.name)
                if key is not None:
                    candidates.append((key, entry.name, entry / "pack.json"))
        if not candidates:
            raise PackNotFoundError(f"No valid versioned pack found for country '{code_upper}'")
        _, chosen_version, pack_file = max(candidates, key=lambda c: c[0])

    try:
        pack = json.loads(pack_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PackValidationError(f"Malformed JSON in {pack_file}: {exc}") from exc

    validate_pack_or_raise(pack)
    if pack["countryCode"] != code_upper:
        raise PackValidationError(f"Pack countryCode '{pack['countryCode']}' does not match '{code_upper}'")
    if pack["version"] != chosen_version:
        raise PackValidationError(f"Pack version '{pack['version']}' does not match directory '{chosen_version}'")
    return copy.deepcopy(pack)


def _flatten_override_paths(obj: dict[str, Any], prefix: str = "") -> list[str]:
    paths: list[str] = []
    for key, val in obj.items():
        if not isinstance(key, str) or not key:
            raise OverrideRejectedError("Override keys must be non-empty strings")
        full = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            if not val:
                raise OverrideRejectedError(f"Empty override object at '{full}' is not allowed")
            paths.extend(_flatten_override_paths(val, full))
        else:
            paths.append(full)
    return paths


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, val in over.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = copy.deepcopy(val)
    return out


def _validate_holiday_overrides(entries: Any, errors: list[str]) -> None:
    if not isinstance(entries, list):
        errors.append("holidays.overrides must be a list")
        return
    allowed_keys = {"action", "date", "movedTo", "labels", "reason"}
    for idx, item in enumerate(entries):
        if not isinstance(item, dict) or set(item) - allowed_keys:
            errors.append(f"holidays.overrides[{idx}]: invalid override entry")
            continue
        action = item.get("action")
        if action not in {"add", "remove", "move"}:
            errors.append(f"holidays.overrides[{idx}].action: must be add, remove, or move")
        try:
            date.fromisoformat(str(item.get("date", "")))
        except ValueError:
            errors.append(f"holidays.overrides[{idx}].date: invalid ISO date")
        if action == "move":
            try:
                date.fromisoformat(str(item.get("movedTo", "")))
            except ValueError:
                errors.append(f"holidays.overrides[{idx}].movedTo: required ISO date for move")
        if action == "add" and not isinstance(item.get("labels"), dict):
            errors.append(f"holidays.overrides[{idx}].labels: required for add")


def _validate_merged_locale(
    merged: dict[str, Any], pack: dict[str, Any], override_paths: list[str], errors: list[str]
) -> None:
    constraints = pack["overridesPolicy"].get("constraints", {})
    tz = merged.get("timezone", "")
    try:
        ZoneInfo(str(tz))
    except (ZoneInfoNotFoundError, ValueError):
        errors.append(f"timezone '{tz}' is not a valid IANA zone")
    if "allowedTimezones" in constraints and tz not in constraints["allowedTimezones"]:
        errors.append(f"timezone '{tz}' is not permitted by pack constraints")

    cal = merged.get("calendar", {})
    if not isinstance(cal, dict) or set(cal) - {"primary", "secondaryDisplay"}:
        errors.append("calendar: invalid keys")
    else:
        if cal.get("primary") not in {"gregorian", "hijri_umm_al_qura"}:
            errors.append("calendar.primary: must be gregorian or hijri_umm_al_qura")
        if cal.get("secondaryDisplay") not in {"none", "gregorian", "hijri_umm_al_qura"}:
            errors.append("calendar.secondaryDisplay: must be none, gregorian, or hijri_umm_al_qura")

    week = merged.get("week", {})
    if not isinstance(week, dict) or set(week) - {"startDay", "weekendDays"}:
        errors.append("week: invalid keys")
    else:
        if week.get("startDay") not in WEEKDAYS:
            errors.append("week.startDay: invalid weekday")
        wd = week.get("weekendDays")
        if not isinstance(wd, list) or not (1 <= len(wd) <= 3) or len(set(wd)) != len(wd) or not set(wd) <= WEEKDAYS:
            errors.append("week.weekendDays: must be 1..3 unique valid weekdays")

    wt = merged.get("workingTime", {})
    if not isinstance(wt, dict) or set(wt) - {"workDays", "hours", "reducedPeriods"}:
        errors.append("workingTime: invalid keys")
    else:
        w_days = wt.get("workDays")
        if not isinstance(w_days, list) or not w_days or len(set(w_days)) != len(w_days) or not set(w_days) <= WEEKDAYS:
            errors.append("workingTime.workDays: must be non-empty unique valid weekdays")
        hrs = wt.get("hours")
        if not isinstance(hrs, dict) or set(hrs) != {"from", "to"} or not (
            isinstance(hrs.get("from"), str) and TIME_RE.match(hrs["from"])
            and isinstance(hrs.get("to"), str) and TIME_RE.match(hrs["to"])
        ):
            errors.append("workingTime.hours: must define HH:MM 'from' and 'to'")
        _check_working_time(merged, errors, "locale")

    fy = merged.get("fiscalYear", {})
    if constraints.get("fiscalYearLocked") and any(_path_overlaps(p, "fiscalYear") for p in override_paths):
        errors.append("fiscalYear is locked by pack constraints")
    if not isinstance(fy, dict) or set(fy) - {"type", "startMonth", "startDay"}:
        errors.append("fiscalYear: invalid keys")
    else:
        fy_type = fy.get("type")
        allowed_fy = constraints.get("allowedFiscalYearTypes") or ["gregorian", "hijri"]
        if fy_type not in allowed_fy:
            errors.append(f"fiscalYear.type '{fy_type}' not in allowed types {allowed_fy}")
        if not (_is_int(fy.get("startMonth")) and 1 <= fy["startMonth"] <= 12):
            errors.append("fiscalYear.startMonth: must be integer 1..12")
        if not (_is_int(fy.get("startDay")) and 1 <= fy["startDay"] <= 31):
            errors.append("fiscalYear.startDay: must be integer 1..31")

    hol = merged.get("holidays", {})
    if not isinstance(hol, dict) or set(hol) - {"calendarRef", "announcedDates", "overrides"}:
        errors.append("holidays: invalid keys")
    elif "overrides" in hol:
        _validate_holiday_overrides(hol["overrides"], errors)

    if merged.get("numberSystem") not in {"western", "eastern_arabic"}:
        errors.append("numberSystem: must be western or eastern_arabic")
    allowed_cur = constraints.get("allowedCurrencies")
    if allowed_cur is not None and merged.get("currency") not in allowed_cur:
        errors.append(f"currency '{merged.get('currency')}' not in allowedCurrencies {allowed_cur}")


def apply_company_overrides(pack: dict[str, Any], company_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge allowed company overrides onto a validated pack; fail closed on locked/unknown paths."""
    validate_pack_or_raise(pack)
    overrides = {} if company_overrides is None else company_overrides
    if not isinstance(overrides, dict):
        raise OverrideRejectedError("company_overrides must be a JSON object")

    policy = pack["overridesPolicy"]
    locked = policy["lockedPaths"]
    overridable = policy["overridablePaths"]
    leaf_paths = _flatten_override_paths(overrides)

    rejected: list[str] = []
    for p in leaf_paths:
        if any(_path_overlaps(p, lk) for lk in locked):
            rejected.append(f"Override rejected: '{p}' is a locked setting")
        elif not any(p == ov or p.startswith(f"{ov}.") for ov in overridable):
            rejected.append(f"Override rejected: '{p}' is not in pack overridablePaths")
    if rejected:
        raise OverrideRejectedError(rejected[0], errors=rejected)

    merged_locale = _deep_merge(pack["localeDefaults"], overrides)
    post_errors: list[str] = []
    _validate_merged_locale(merged_locale, pack, leaf_paths, post_errors)
    if post_errors:
        raise OverrideRejectedError(post_errors[0], errors=post_errors)

    return {
        "packId": pack["packId"],
        "componentId": pack["componentId"],
        "countryCode": pack["countryCode"],
        "version": pack["version"],
        "status": pack["status"],
        "evidenceStatus": pack["evidenceStatus"],
        "locked": {
            "coaTemplate": copy.deepcopy(pack["coaTemplate"]),
            "tax": copy.deepcopy(pack["tax"]),
            "eInvoicing": copy.deepcopy(pack["eInvoicing"]),
            "formats": copy.deepcopy(pack["formats"]),
            "payrollHooks": copy.deepcopy(pack["payrollHooks"]),
            "printFormats": copy.deepcopy(pack["printFormats"]),
            "holidaysCalendarRef": copy.deepcopy(pack["localeDefaults"]["holidays"]["calendarRef"]),
        },
        "locale": merged_locale,
        "appliedOverrides": sorted(leaf_paths),
    }


def resolve_country_pack(
    country_code: str,
    packs_dir: Path,
    company_overrides: dict[str, Any] | None = None,
    version: str | None = None,
    pack_id: str | None = None,
) -> dict[str, Any]:
    """Select, validate, and resolve a country pack with company overrides from explicit inputs."""
    pack = load_country_pack(country_code=country_code, packs_dir=packs_dir, version=version)
    if pack_id is not None and pack_id != pack["packId"]:
        raise PackValidationError(f"Requested pack_id '{pack_id}' does not match loaded pack '{pack['packId']}'")
    return apply_company_overrides(pack, company_overrides=company_overrides)
