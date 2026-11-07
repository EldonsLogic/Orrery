"""redact_for_model: minimise personal and financial payloads for model-bound consumers.

Policy (default, mask mode): in events whose data_class is personal or financial,
  - keep values under id-like keys ("id", "*_id", "*_ids") when they are short scalars;
  - keep values under KEEP_KEYS (enums and structure such as from, to, status, decision) when short scalars;
  - mask every other leaf with "[REDACTED]" (mode "mask") or remove the key (mode "drop").
Other data classes are copied unchanged. The original is never mutated. A summary is written
to data["_redaction"] = {"policy", "masked", "dropped"}. Envelope fields (ids, actor id, subject)
are kept: they are ids. Names, amounts, IBANs, phone numbers and free text never survive.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

MASK = "[REDACTED]"
KEEP_KEYS = frozenset({"from", "to", "status", "decision", "mode", "kind", "type", "tier", "purpose", "currency",
                       "einvoice_status", "reason_code", "error_code", "method", "entity", "field", "fields",
                       "changed_fields", "day", "count"})
MAX_KEEP_STRING = 64


@dataclass(frozen=True)
class RedactionPolicy:
    name: str = "default-v1"
    classes: frozenset = frozenset({"personal", "financial"})
    mode: str = "mask"  # mask | drop
    keep_keys: frozenset = KEEP_KEYS


DEFAULT_POLICY = RedactionPolicy()


def _is_id_key(k: str) -> bool:
    k = k.lower()
    return k == "id" or k.endswith("_id") or k.endswith("_ids")


def _short_scalar(v: object) -> bool:
    return isinstance(v, (str, int, bool)) and not (isinstance(v, str) and len(v) > MAX_KEEP_STRING)


def redact_for_model(ev: dict, policy: RedactionPolicy = DEFAULT_POLICY) -> dict:
    """Return a redacted deep copy. Expects an event already validated (bounded depth)."""
    out = copy.deepcopy(ev)
    if not isinstance(out, dict) or out.get("data_class") not in policy.classes or not isinstance(out.get("data"), dict):
        return out
    counts = {"masked": 0, "dropped": 0}

    def walk(v: object, keep: bool, depth: int):
        if depth > 12:  # defence in depth; validated events are far shallower
            counts["dropped"] += 1
            return MASK
        if isinstance(v, dict):
            res = {}
            for k, x in v.items():
                kk = _is_id_key(str(k)) or str(k) in policy.keep_keys
                if policy.mode == "drop" and not kk and not isinstance(x, (dict, list)):
                    counts["dropped"] += 1
                    continue
                res[k] = walk(x, kk, depth + 1)
            return res
        if isinstance(v, list):
            return [walk(x, keep, depth + 1) for x in v]
        if keep and _short_scalar(v):
            return v
        counts["masked"] += 1
        return MASK

    out["data"] = walk(out["data"], False, 1)
    out["data"]["_redaction"] = {"policy": policy.name, **counts}
    return out
