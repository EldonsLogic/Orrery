"""Untrusted-content discipline (SEC-003, PI-RULE-1 and 2): tool results and documents become `DataItem`s with a
provenance label and sanitise flags. They travel in `ModelRequest.data`, never in the instruction position.

Sanitising reuses the discovery connector functions (control characters, comparison copy, instruction-like patterns)
loaded by file path, so no import name can be shadowed. A load failure raises at import: fail closed."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

from .models import DataItem

_CONNECTORS = Path(__file__).resolve().parents[2] / "discovery" / "connectors"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_orrery_rt_{name}", _CONNECTORS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_san, _det = _load("sanitise"), _load("detect")
TRUNC_MARK = " [truncated]"
_FLAG_NAMES = {"bidi": "bidi_control", "zero_width": "zero_width", "unicode_tag": "unicode_tag",
               "invisible": "invisible_char", "control": "control_char"}
ENGINE = re.compile(r"frappe|erpnext|doctype|\btab[A-Z]|traceback|\bsql\b|\.py\b|site_config|/apps/", re.IGNORECASE)


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def sanitise_text(text: str, max_chars: int) -> tuple:
    """Return (clean text, sorted flags). Engine names and stack-like text are replaced, never passed on."""
    clean, counts = _san.strip_controls(text if isinstance(text, str) else canonical(text))
    flags = {_FLAG_NAMES[k] for k, n in counts.items() if n}
    if len(clean) > max_chars:
        clean, flags = clean[:max_chars] + TRUNC_MARK, flags | {"truncated"}
    if _det.instruction_hits(_san.comparison_copy(clean)):
        flags.add("instruction_like")
    if ENGINE.search(clean):
        clean, flags = "[withheld: internal detail]", flags | {"internal_detail_withheld"}
    return clean, tuple(sorted(flags))


def wrap_data(content_id: str, source: str, payload, max_chars: int = 8000) -> DataItem:
    """Build an L3 item. `payload` may be text or any JSON value (rendered canonically)."""
    text = payload if isinstance(payload, str) else canonical(payload)
    clean, flags = sanitise_text(text, max_chars)
    return DataItem(content_id=content_id, source=source, text=clean, content_hash=sha(text), flags=flags)


_SENSITIVE = re.compile(r"iban|swift|account|password|passwd|secret|token|credential|api_?key|email|phone|mobile|"
                        r"whatsapp|address|beneficiary|salary|tax_?id|vat", re.IGNORECASE)


def redact_args(value, depth: int = 0):
    """Span-safe copy of tool arguments: sensitive keys masked, long strings reduced to a length and hash."""
    if depth > 6:
        return "[deep]"
    if isinstance(value, dict):
        return {str(k)[:64]: ("[redacted]" if _SENSITIVE.search(str(k)) else redact_args(v, depth + 1))
                for k, v in list(value.items())[:50]}
    if isinstance(value, (list, tuple)):
        return [redact_args(v, depth + 1) for v in list(value)[:20]]
    if isinstance(value, str) and len(value) > 80:
        return f"[{len(value)} chars {sha(value)[7:19]}]"
    return value if isinstance(value, (int, float, bool)) or value is None or isinstance(value, str) else "[value]"
