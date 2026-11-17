"""Blueprint field -> JSON Schema (2020-12). Pure. Unknown type raises FieldError (the caller turns it into a refusal)."""
from __future__ import annotations

from . import policy as P


class FieldError(Exception):
    def __init__(self, code: str, fact: str):
        super().__init__(fact)
        self.code, self.fact = code, fact


def _num(v):
    return str(v)


def _decimal(f: dict) -> dict:
    prec = f.get("precision", P.DEFAULT_PRECISION)
    frac = f"(\\.[0-9]{{1,{prec}}})?" if prec > 0 else ""
    s: dict = {"type": "string", "pattern": f"^-?[0-9]{{1,18}}{frac}$"}
    if "min" in f:
        s["x-minimum"] = _num(f["min"])
    if "max" in f:
        s["x-maximum"] = _num(f["max"])
    return s


def field_schema(f: dict, entity_ids: set[str]) -> dict:
    t = f.get("type")
    if t not in P.FIELD_TYPES:
        raise FieldError("TAPI-FIELD-001", f"field type {t!r} is not known; refused, not guessed")
    if t == "string":
        return {"type": "string", "maxLength": f.get("maxLength", P.DEFAULT_STRING_MAX)}
    if t == "text":
        return {"type": "string", "maxLength": f.get("maxLength", P.DEFAULT_TEXT_MAX)}
    if t == "integer":
        s = {"type": "integer"}
        if "min" in f:
            s["minimum"] = f["min"]
        if "max" in f:
            s["maximum"] = f["max"]
        return s
    if t in ("decimal", "percent"):
        return _decimal(f)
    if t == "money":  # decimal string plus currency, never a float
        return {"type": "object", "additionalProperties": False, "required": ["currency", "value"],
                "properties": {"currency": {"type": "string", "pattern": "^[A-Z]{3}$"}, "value": _decimal(f)}}
    if t == "boolean":
        return {"type": "boolean"}
    if t == "date":
        return {"type": "string", "format": "date"}
    if t == "datetime":
        return {"type": "string", "format": "date-time"}
    if t == "select":
        opts = f.get("options")
        vals = [o.get("value") for o in opts] if isinstance(opts, list) else []
        if not vals or any(not isinstance(v, str) for v in vals) or len(set(vals)) != len(vals):
            raise FieldError("TAPI-FIELD-002", "select field needs a non-empty list of unique string option values")
        return {"type": "string", "enum": vals}
    if t == "link":
        target = f.get("target")
        if target not in entity_ids:
            raise FieldError("TAPI-REF-001", f"link target {target!r} is not an entity")
        return {"type": "string", "pattern": P.ID_PATTERN, "x-entity-ref": target}
    if t == "attachment":
        return {"type": "string", "pattern": P.ID_PATTERN, "x-attachment": True}
    if t == "phone":
        return {"type": "string", "pattern": "^\\+?[0-9 ()-]{5,20}$"}
    return {"type": "string", "format": "email", "maxLength": 254}  # email


def object_schema(props: dict, required: list[str]) -> dict:
    s = {"type": "object", "additionalProperties": False, "properties": props}
    if required:
        s["required"] = sorted(required)
    return s
