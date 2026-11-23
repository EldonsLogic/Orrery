"""Country pack loader, schema/invariant validator, and fail-closed override merger (CMP-021)."""

from __future__ import annotations

import copy
from datetime import date
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jsonschema import Draft202012Validator, FormatChecker

from .certification import certification_refusals
from .strict_json import loads_strict

SCHEMA_PATH = Path(__file__).resolve().parent / "pack.schema.json"
COUNTRY_CODE_RE = re.compile(r"^[A-Za-z]{2}$")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")
WEEKDAYS = frozenset({"mon", "tue", "wed", "thu", "fri", "sat", "sun"})
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
SNAKE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
LOCALE_TAG_RE = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Go-live gate (CMP-034): mirrors ADR-0034's production boundary for components.
ENVIRONMENTS = ("sandbox", "test", "production")
PRODUCTION_STATUSES = frozenset({"certified", "regulated"})
# Q-560: secondary evidence requires the same market-accountant sign-off as official evidence.
PRODUCTION_EVIDENCE = frozenset({"verified_official", "secondary"})


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


def _load_schema(schema_path: Path | None = None) -> dict[str, Any]:
    path = schema_path or SCHEMA_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def _path_overlaps(a: str, b: str) -> bool:
    return a == b or a.startswith(f"{b}.") or b.startswith(f"{a}.")


def _check_localized_text(val: Any, prefix: str, errors: list[str]) -> None:
    if not isinstance(val, dict):
        errors.append(f"{prefix}: must be a localized text object")
        return
    for req in ("ar", "en"):
        if req not in val:
            errors.append(f"{prefix}.{req}: missing required locale")
    for k, v in val.items():
        if not isinstance(k, str) or not LOCALE_TAG_RE.match(k):
            errors.append(f"{prefix}.{k}: invalid BCP 47 locale key")
        if not isinstance(v, str) or not (1 <= len(v) <= 200):
            errors.append(f"{prefix}.{k}: localized text must be 1..200 characters")


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
    allowed_rp_keys = {"id", "labels", "rule", "gregorianFrom", "gregorianTo", "hours"}
    fixed_spans: list[tuple[date, date, int]] = []
    seen_ids: set[str] = set()
    for idx, rp in enumerate(reduced or []):
        rp_prefix = f"{prefix}.workingTime.reducedPeriods[{idx}]"
        if not isinstance(rp, dict):
            errors.append(f"{rp_prefix}: entry must be an object")
            continue
        extra_keys = sorted(set(rp) - allowed_rp_keys)
        if extra_keys:
            errors.append(f"{rp_prefix}: unexpected properties: {', '.join(extra_keys)}")
        rp_id = rp.get("id")
        if not isinstance(rp_id, str) or not SNAKE_ID_RE.match(rp_id):
            errors.append(f"{rp_prefix}.id: must match Blueprint id pattern")
        elif rp_id in seen_ids:
            errors.append(f"{rp_prefix}.id: duplicate reduced period id '{rp_id}'")
        else:
            seen_ids.add(rp_id)
        if "labels" not in rp:
            errors.append(f"{rp_prefix}.labels: missing required property")
        else:
            _check_localized_text(rp["labels"], f"{rp_prefix}.labels", errors)

        rule = rp.get("rule", "ramadan")
        if rule not in {"ramadan", "fixed_dates"}:
            errors.append(f"{rp_prefix}.rule: must be 'ramadan' or 'fixed_dates'")

        hrs = rp.get("hours")
        if not isinstance(hrs, dict) or set(hrs) != {"from", "to"}:
            errors.append(f"{rp_prefix}.hours: must define exact keys 'from' and 'to'")
        else:
            rf, rt = hrs.get("from", ""), hrs.get("to", "")
            if not (isinstance(rf, str) and isinstance(rt, str) and TIME_RE.match(rf) and TIME_RE.match(rt) and rf < rt):
                errors.append(f"{rp_prefix}.hours: invalid range")

        for d_key in ("gregorianFrom", "gregorianTo"):
            if d_key in rp:
                d_val = rp[d_key]
                if not isinstance(d_val, str) or not ISO_DATE_RE.match(d_val):
                    errors.append(f"{rp_prefix}.{d_key}: must be YYYY-MM-DD ISO date")
                else:
                    try:
                        date.fromisoformat(d_val)
                    except ValueError:
                        errors.append(f"{rp_prefix}.{d_key}: invalid calendar date")

        if rule == "fixed_dates":
            g_from = rp.get("gregorianFrom", "")
            g_to = rp.get("gregorianTo", "")
            if not (isinstance(g_from, str) and isinstance(g_to, str) and ISO_DATE_RE.match(g_from) and ISO_DATE_RE.match(g_to)):
                errors.append(f"{rp_prefix}: fixed_dates requires gregorianFrom and gregorianTo ISO dates")
                continue
            try:
                d_from = date.fromisoformat(g_from)
                d_to = date.fromisoformat(g_to)
            except ValueError:
                errors.append(f"{rp_prefix}: invalid fixed_dates ISO dates")
                continue
            if d_from > d_to:
                errors.append(f"{rp_prefix}: gregorianFrom after gregorianTo")
            else:
                for prev_a, prev_b, prev_i in fixed_spans:
                    if d_from <= prev_b and prev_a <= d_to:
                        errors.append(f"{rp_prefix} overlaps [{prev_i}]")
                fixed_spans.append((d_from, d_to, idx))


def validate_pack(pack: Any, schema_path: Path | None = None) -> list[str]:
    """Validate a country pack manifest against the schema and cross-field invariants."""
    if not isinstance(pack, dict):
        return ["pack: manifest must be a JSON object"]
    schema = _load_schema(schema_path)
    errors: list[str] = []
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for err in sorted(validator.iter_errors(pack), key=lambda e: list(e.absolute_path)):
        loc = ".".join(map(str, err.absolute_path)) or "pack"
        errors.append(f"{loc}: {err.message}")
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


def _check_environment(environment: Any) -> None:
    # Exact type: a str subclass could override __eq__ to pass the membership test and skip the gate.
    if type(environment) is not str or environment not in ENVIRONMENTS:
        raise CountryPackError(f"Unknown environment {environment!r} (allowed: {', '.join(ENVIRONMENTS)})")


def _check_go_live(pack: dict[str, Any], directory: Path, label: str, environment: str) -> None:
    """Refuse production packs lacking certification records, accepted evidence or a matching manifest."""
    if environment != "production":
        return
    try:
        reasons = certification_refusals(pack, directory)
    except RecursionError:  # deep companion data must refuse, never crash the gate
        reasons = ["certification records are nested too deeply"]
    if pack["status"] not in PRODUCTION_STATUSES:
        reasons.append(f"status '{pack['status']}' is below certified")
    if pack["evidenceStatus"] not in PRODUCTION_EVIDENCE:
        reasons.append(f"evidenceStatus '{pack['evidenceStatus']}' is not verified_official or secondary")
    if pack.get("testOnly") is True:
        reasons.append("pack is marked testOnly=true (allow_test_packs never applies in production)")
    if reasons:
        raise PackValidationError(f"Country pack {label} cannot be used in production: {'; '.join(reasons)}", errors=reasons)


def _semver_key(version: str) -> tuple[int, int, int, int, str] | None:
    m = SEMVER_RE.match(version)
    if not m:
        return None
    major, minor, patch, pre = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
    return (major, minor, patch, 1 if pre is None else 0, pre or "")


def load_country_pack(
    country_code: str,
    packs_dir: Path,
    version: str | None = None,
    *,
    allow_test_packs: bool = False,
    environment: str = "production",
) -> dict[str, Any]:
    """Load and validate a country pack from `<packs_dir>/<country>/<version>/pack.json`.

    Packs marked `testOnly: true` are rejected unless `allow_test_packs=True`. In `environment="production"`
    (the default) a pack must be certified/regulated, have official or secondary evidence, a matching
    companion manifest naming its reviewer, and a market-accountant sign-off plus founder approval in
    evidence.json. A `testOnly` pack is always refused in production. `"sandbox"` and `"test"` skip these
    certification checks and are for synthetic data only (caller's responsibility, ADR-0059).
    Any other environment, including a `str` subclass, is rejected.
    """
    _check_environment(environment)
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
                    pack_path = entry / "pack.json"
                    if not allow_test_packs:
                        try:
                            raw_meta = loads_strict(pack_path.read_text(encoding="utf-8"))
                            if isinstance(raw_meta, dict) and raw_meta.get("testOnly") is True:
                                continue
                        except ValueError:
                            pass  # kept as a candidate; the selected file is parsed (and refused) below
                    candidates.append((key, entry.name, pack_path))
        if not candidates:
            raise PackNotFoundError(f"No valid non-test versioned pack found for country '{code_upper}'")
        _, chosen_version, pack_file = max(candidates, key=lambda c: c[0])

    try:
        pack = loads_strict(pack_file.read_text(encoding="utf-8"))
    except ValueError as exc:  # malformed JSON, duplicate keys or too-deep nesting
        raise PackValidationError(f"Malformed JSON in {pack_file}: {exc}") from exc

    try:
        validate_pack_or_raise(pack)
    except RecursionError as exc:
        raise PackValidationError(f"Country pack {code_upper}@{chosen_version} is nested too deeply") from exc
    if pack.get("testOnly") is True and not allow_test_packs:
        raise PackValidationError(
            f"Country pack {code_upper}@{chosen_version} is marked testOnly=true and cannot be used in production"
        )
    if pack["countryCode"] != code_upper:
        raise PackValidationError(f"Pack countryCode '{pack['countryCode']}' does not match '{code_upper}'")
    if pack["version"] != chosen_version:
        raise PackValidationError(f"Pack version '{pack['version']}' does not match directory '{chosen_version}'")
    _check_go_live(pack, pack_file.parent, f"{code_upper}@{chosen_version}", environment)
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


def _apply_company_overrides(pack: dict[str, Any], company_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge allowed company overrides onto a validated pack; fail closed on locked/unknown paths.

    Private (CMP-034): it runs no go-live gate. `resolve_country_pack` is the only production entry.
    """
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
    *,
    allow_test_packs: bool = False,
    allow_unpinned: bool = False,
    environment: str = "production",
) -> dict[str, Any]:
    """Select, validate, and resolve a country pack with company overrides from explicit inputs.

    Requires a pinned `version` unless `allow_unpinned=True` and rejects `testOnly: true`
    packs unless `allow_test_packs=True` (never in production). `environment` gates go-live as in
    `load_country_pack`. This is the only production entry: the override merger is private and ungated.
    """
    _check_environment(environment)
    if version is None and not allow_unpinned:
        raise PackNotFoundError(
            f"resolve_country_pack requires an explicit pinned version for country '{country_code}'"
        )
    pack = load_country_pack(
        country_code=country_code,
        packs_dir=packs_dir,
        version=version,
        allow_test_packs=allow_test_packs,
        environment=environment,
    )
    if pack_id is not None and pack_id != pack["packId"]:
        raise PackValidationError(f"Requested pack_id '{pack_id}' does not match loaded pack '{pack['packId']}'")
    return _apply_company_overrides(pack, company_overrides=company_overrides)
