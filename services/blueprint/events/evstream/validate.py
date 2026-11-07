"""validate_event: checks one event against the contract. Never raises on bad input.

Event content is untrusted: the walk over `data` is iterative (no recursion), bounded by
depth, node count and bytes, and never evaluates or follows anything found in it.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Iterable

from .errors import Issue, clip
from .registry import Registry, default_registry

# --- caps (documented in README.md)
MAX_DATA_BYTES = 64 * 1024     # serialised UTF-8 size of `data`
MAX_DATA_DEPTH = 6             # `data` itself is depth 1
MAX_DATA_NODES = 5000          # every value in `data` counts
MAX_DATA_KEYS = 40             # object keys in `data`, flat and nested together
# Whole-record heuristic: an object under one of these keys, or any object carrying the marker
# key with a truthy value, is a whole record, not "ids and changed values".
WHOLE_RECORD_KEYS = frozenset({"record", "whole_record", "full_record", "document", "doc", "row", "snapshot"})
WHOLE_RECORD_MARKER = "__whole_record__"
# Personal and financial minimisation rule: only ids, enums, counts and short changed values.
MAX_PERSONAL_STRING = 64
PERSONAL_DENY_KEYS = frozenset({
    "name", "full_name", "first_name", "last_name", "email", "phone", "mobile", "address",
    "iban", "account_number", "card_number", "national_id", "id_number", "passport", "passport_number",
    "dob", "date_of_birth", "salary_text", "notes", "body", "content", "text", "message",
})
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_IBAN_RE = re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}")
_PHONE_RE = re.compile(r"\+?\d[\d\s-]{8,}")
_TENANT_VALUE_RE = re.compile(r"t_[A-Za-z0-9_]{3,62}")  # heuristic: how tenant ids look in the contract
_TENANT_KEYS = frozenset({"tenantid", "tenantids", "tenant"})
_PLATFORM = "platform"
_AI_ACTOR = "agent"


@dataclass
class ValidationResult:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    unknown_type: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {"ok": self.ok, "unknown_type": self.unknown_type,
                "errors": [i.as_dict() for i in self.errors], "warnings": [i.as_dict() for i in self.warnings]}


def _norm_key(k: str) -> str:
    return re.sub(r"[^a-z]", "", k.lower())


def scan_data(data: dict, tenant_id: str | None, data_class: str | None,
              known_tenant_ids: Iterable[str] = ()) -> list[Issue]:
    """Iterative walk of `data`. Returns issues; stops at the first structural overflow."""
    known = frozenset(known_tenant_ids)
    issues: list[Issue] = []
    seen: set[tuple[str, str]] = set()

    def add(code: str, path: str, msg: str) -> None:
        if (code, path) not in seen and len(issues) < 25:
            seen.add((code, path))
            issues.append(Issue(code, path, msg))

    minimise = data_class in ("personal", "financial")
    nodes = keys = 0
    stack: list[tuple[object, int, str]] = [(data, 1, "data")]
    while stack:
        val, depth, path = stack.pop()
        nodes += 1
        if nodes > MAX_DATA_NODES:
            return issues + [Issue("EVS-DATA-002", "data", f"more than {MAX_DATA_NODES} values")]
        if depth > MAX_DATA_DEPTH:
            return issues + [Issue("EVS-DATA-003", path, f"nesting deeper than {MAX_DATA_DEPTH}")]
        if isinstance(val, dict):
            keys += len(val)
            if keys > MAX_DATA_KEYS:
                add("EVS-DATA-004", "data", f"more than {MAX_DATA_KEYS} keys: looks like a whole record")
            if val.get(WHOLE_RECORD_MARKER):
                add("EVS-DATA-004", path, "object marked as a whole record")
            for k, v in val.items():
                if not isinstance(k, str):
                    add("EVS-DATA-005", path, "non-string key")
                    continue
                p = f"{path}.{k[:60]}"
                nk = _norm_key(k)
                if nk in _TENANT_KEYS:
                    add("EVS-TENANT-001", p, "data must not carry a tenant id")
                if k in WHOLE_RECORD_KEYS and isinstance(v, (dict, list)):
                    add("EVS-DATA-004", p, "whole record embedded")
                if minimise and k.lower() in PERSONAL_DENY_KEYS:
                    add("EVS-DATA-006", p, "direct identifier or free text in personal/financial data")
                stack.append((v, depth + 1, p))
        elif isinstance(val, list):
            for i, v in enumerate(val):
                stack.append((v, depth + 1, f"{path}[{i}]"))
        elif isinstance(val, str):
            if _TENANT_VALUE_RE.fullmatch(val) and val != tenant_id:
                add("EVS-TENANT-001", path, "another tenant's id inside data")
            elif val in known and val != tenant_id:
                add("EVS-TENANT-001", path, "another tenant's id inside data")
            if minimise:
                if len(val) > MAX_PERSONAL_STRING:
                    add("EVS-DATA-006", path, f"string longer than {MAX_PERSONAL_STRING} in personal/financial data")
                elif _EMAIL_RE.fullmatch(val) or _IBAN_RE.fullmatch(val) or _PHONE_RE.fullmatch(val):
                    add("EVS-DATA-006", path, "email, IBAN or phone number in personal/financial data")
        elif isinstance(val, bool) or val is None or isinstance(val, int):
            pass
        elif isinstance(val, float):
            if not math.isfinite(val):
                add("EVS-DATA-005", path, "NaN or infinity")
        else:
            add("EVS-DATA-005", path, f"value of type {type(val).__name__} is not JSON")
    if not any(i.code in ("EVS-DATA-005",) for i in issues):
        try:
            if len(json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_DATA_BYTES:
                issues.append(Issue("EVS-DATA-002", "data", f"more than {MAX_DATA_BYTES} bytes"))
        except (TypeError, ValueError):
            issues.append(Issue("EVS-DATA-005", "data", "not serialisable as JSON"))
    return issues


def _path(err) -> str:
    return ".".join(str(p) for p in err.absolute_path) or "$"


def validate_event(ev: object, registry: Registry | None = None, *, stamped: bool = True,
                   known_tenant_ids: Iterable[str] = ()) -> ValidationResult:
    """Check `ev`. stamped=False is for events not yet appended: sequence must be absent."""
    res = ValidationResult()
    try:
        _validate(ev, registry or default_registry(), stamped, known_tenant_ids, res)
    except Exception as e:  # untrusted input must never crash the caller
        res.errors.append(Issue("EVS-ENV-002", "$", f"could not check event ({type(e).__name__})"))
    return res


def _validate(ev, reg: Registry, stamped: bool, known, res: ValidationResult) -> None:
    if not isinstance(ev, dict):
        res.errors.append(Issue("EVS-ENV-002", "$", "event is not a JSON object"))
        return
    target = ev
    if not stamped:
        if ev.get("sequence") is not None:
            res.errors.append(Issue("EVS-SEQ-001", "sequence", "producers must not set sequence"))
        target = {**ev, "sequence": 1}
    data = ev.get("data")
    scan: list[Issue] = []
    if isinstance(data, dict):
        tid = ev.get("tenant_id") if isinstance(ev.get("tenant_id"), str) else None
        dc = ev.get("data_class") if isinstance(ev.get("data_class"), str) else None
        scan = scan_data(data, tid, dc, known)
        if any(i.code in ("EVS-DATA-002", "EVS-DATA-003", "EVS-DATA-005") for i in scan):
            res.errors.extend(scan)
            return  # hostile shape: do not hand it to the schema engine
    errs = sorted(reg.envelope_validator().iter_errors(target), key=lambda e: _path(e))
    for e in errs[:20]:
        res.errors.append(Issue("EVS-ENV-001", _path(e), clip(e.message)))
    res.errors.extend(scan)
    if errs:
        return
    info = reg.lookup(ev["type"])
    actor, trace, tenant = ev["actor"], ev.get("trace"), ev["tenant_id"]
    if info is None:
        res.unknown_type = True
        res.warnings.append(Issue("EVS-TYPE-001", "type", "unknown type: stored and skipped", "warning"))
    else:
        if ev["schema_version"] != info.schema_version:
            res.warnings.append(Issue("EVS-TYPE-002", "schema_version",
                                      f"registry has {info.schema_version}; data not checked", "warning"))
        else:
            for e in sorted(reg.data_validator(info).iter_errors(data), key=lambda e: _path(e))[:20]:
                res.errors.append(Issue("EVS-DATA-001", "data" + ("." + _path(e) if _path(e) != "$" else ""), clip(e.message)))
        if info.requires_subject and not ev.get("subject"):
            res.errors.append(Issue("EVS-SUBJ-001", "subject", "record events need a subject"))
        if (tenant == _PLATFORM) != (info.scope == _PLATFORM):
            res.errors.append(Issue("EVS-TENANT-002", "tenant_id", f"{info.type} has scope {info.scope}"))
        if info.type == "meter.ai_usage" and not (trace or {}).get("model_id"):
            res.errors.append(Issue("EVS-TRACE-001", "trace.model_id", "meter.ai_usage needs trace.model_id"))
        if info.data_class in ("personal", "financial") and ev["data_class"] not in ("personal", "financial"):
            res.warnings.append(Issue("EVS-CLASS-001", "data_class", f"type default is {info.data_class}", "warning"))
    needs_trace = (info is not None and info.requires_trace) or actor["kind"] == _AI_ACTOR \
        or bool(trace and trace.get("model_id"))
    if needs_trace and not trace:
        res.errors.append(Issue("EVS-TRACE-001", "trace", "an AI model took part: trace is required"))
    if ev.get("causation_id") == ev["event_id"]:
        res.errors.append(Issue("EVS-CAUSE-002", "causation_id", "event cannot cause itself"))
