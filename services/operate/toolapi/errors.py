"""Domain error catalog (OPR-018): build contract error objects and render customer text from the catalog only.

Contract: contracts/tool-api.md section 7 and contracts/tool-api-error-catalog.json. Pure, no network.
Fails closed: an unknown code or bad params become a generic `internal_error` carrying only a correlation id.

HOOK (PLT-024): the gateway maps an engine failure to a catalog id and params, then calls `build_error`.
Mapping engine exceptions is NOT done here; an unmapped failure stays a plain `engine_error` with no `domain`.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date
from html import escape
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[3] / "contracts" / "tool-api-error-catalog.json"
CLASSES = {"guard_failed", "conflict", "engine_error", "invalid_arguments", "permission_denied"}
SLOT_TYPES = {"string", "integer", "decimal_string", "id", "date"}
LOCALES = ("en", "ar")
ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,47}$")
KEY_RE = re.compile(r"^errors\.domain\.([a-z][a-z0-9_]+)$")
SLOT_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")
_ID_VALUE = re.compile(r"^[\w\-.:]{1,256}$")
_DECIMAL = re.compile(r"^-?[0-9]{1,18}(\.[0-9]{1,6})?$")
# Bidi and invisible formatting controls: embedding/override/isolate marks, LRM/RLM/ALM, zero-width, BOM.
_BIDI = re.compile("[​-‏‪-‮⁠-⁩؜﻿]")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
# Text that must never appear in a catalog message: engine names, class/table names, SQL, paths, stack traces.
_FORBIDDEN = re.compile(
    r"frappe|erpnext|doctype|\btab[A-Z]|\bsql\b|\b(select|insert|delete|drop|truncate)\b|\bupdate\b.+\bset\b"
    r"|traceback|\bexception\b|\.py\b|[/\\]|\bat line\b|\bhttp",
    re.IGNORECASE)


def load_catalog(path=None) -> dict:
    return json.loads(Path(path or CATALOG_PATH).read_text(encoding="utf-8"))


def validate_catalog(catalog: dict) -> list[str]:
    """Return a list of problems; empty means valid. Structural shape is also covered by the JSON Schema."""
    problems: list[str] = []
    entries = catalog.get("entries") if isinstance(catalog, dict) else None
    if not isinstance(entries, list) or not entries:
        return ["entries: missing or empty"]
    seen: set[str] = set()
    for i, e in enumerate(entries):
        eid = e.get("id", "") if isinstance(e, dict) else ""
        at = f"entries[{i}] {eid}"
        if not isinstance(e, dict) or not ID_RE.match(str(eid)):
            problems.append(f"{at}: id missing or not snake_case")
            continue
        if eid in seen:
            problems.append(f"{at}: duplicate id")
        seen.add(eid)
        if e.get("class") not in CLASSES:
            problems.append(f"{at}: class not allowed")
        if not isinstance(e.get("retryable"), bool):
            problems.append(f"{at}: retryable must be boolean")
        m = KEY_RE.match(str(e.get("message_key", "")))
        if not m or m.group(1) != eid:
            problems.append(f"{at}: message_key must be errors.domain.{eid}")
        params = e.get("params") if isinstance(e.get("params"), dict) else None
        if params is None:
            problems.append(f"{at}: params must be an object")
            params = {}
        for name, slot in params.items():
            if not isinstance(slot, dict) or slot.get("type") not in SLOT_TYPES or not isinstance(slot.get("max_length"), int):
                problems.append(f"{at}: slot {name} needs type and max_length")
            elif slot["type"] == "string" and not slot.get("enum") and slot.get("escaped") is not True:
                problems.append(f"{at}: free-text slot {name} must have enum or escaped: true")
        msgs = e.get("messages") if isinstance(e.get("messages"), dict) else {}
        for loc in LOCALES:
            text = msgs.get(loc)
            if not isinstance(text, str) or not text.strip():
                problems.append(f"{at}: messages.{loc} missing")
                continue
            used = set(SLOT_RE.findall(text))
            for u in sorted(used - set(params)):
                problems.append(f"{at}: messages.{loc} uses undeclared slot {u}")
            for d in sorted(set(params) - used):
                problems.append(f"{at}: messages.{loc} does not use declared slot {d}")
            if _FORBIDDEN.search(SLOT_RE.sub("", text)):
                problems.append(f"{at}: messages.{loc} contains engine, SQL, path or trace text")
        if not e.get("owner_action"):
            problems.append(f"{at}: owner_action missing")
        if e.get("review") not in ("unreviewed", "reviewed"):
            problems.append(f"{at}: review must be unreviewed or reviewed")
    return problems


def _entry(catalog: dict, code) -> dict | None:
    for e in catalog.get("entries", []):
        if e.get("id") == code:
            return e
    return None


def _valid_value(slot: dict, value) -> bool:
    t, n = slot["type"], slot["max_length"]
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool) and len(str(value)) <= n
    if not isinstance(value, str) or len(value) > n or _BIDI.search(value) or _CTRL.search(value):
        return False
    if slot.get("enum") is not None:
        return value in slot["enum"]
    if t == "id":
        return bool(_ID_VALUE.match(value))
    if t == "decimal_string":
        return bool(_DECIMAL.match(value))
    if t == "date":
        try:
            return date.fromisoformat(value).isoformat() == value
        except ValueError:
            return False
    return slot.get("escaped") is True and len(value) > 0


def internal_error(correlation_id: str | None = None) -> dict:
    """Generic fail-closed error: no detail, only a correlation id for the internal log."""
    return {"code": "internal_error", "message_key": "errors.internal_error", "retryable": False,
            "details": {"correlation_id": correlation_id or uuid.uuid4().hex}}


def build_error(code, params, catalog: dict, correlation_id: str | None = None) -> dict:
    """Contract error object with a `domain` block, or `internal_error` if code or params are not valid."""
    entry = _entry(catalog, code) if isinstance(code, str) else None
    if entry is None or not isinstance(params, dict):
        return internal_error(correlation_id)
    slots = entry["params"]
    if set(params) != set(slots) or not all(_valid_value(slots[k], v) for k, v in params.items()):
        return internal_error(correlation_id)
    return {"code": entry["class"], "message_key": f"errors.{entry['class']}", "retryable": entry["retryable"],
            "details": {}, "domain": {"code": entry["id"], "params": dict(sorted(params.items()))}}


def _clean(value) -> str:
    return escape(_CTRL.sub(" ", _BIDI.sub("", str(value))), quote=True)


def render_message(error: dict, locale: str, catalog: dict) -> str:
    """Customer text for an error. Only catalog text is used; params are cleaned and escaped; falls back to English."""
    domain = error.get("domain") if isinstance(error, dict) else None
    entry = _entry(catalog, domain.get("code")) if isinstance(domain, dict) else None
    if entry is None:
        return ""  # caller renders the top-level message_key from its own i18n table
    text = entry["messages"].get(locale) or entry["messages"]["en"]
    params = domain.get("params") if isinstance(domain.get("params"), dict) else {}
    slots = entry["params"]
    return SLOT_RE.sub(lambda m: _clean(params[m.group(1)]) if m.group(1) in slots and m.group(1) in params else "", text)
