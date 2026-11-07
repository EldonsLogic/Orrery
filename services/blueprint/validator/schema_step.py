"""Step 1: JSON Schema (draft 2020-12) validation, plus schema loading and a schema-driven walker."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from jsonschema import Draft202012Validator, FormatChecker

from .report import Report, ValidationContext, ptr

# services/blueprint/validator/schema_step.py -> repo root is three levels above the package dir.
DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts" / "blueprint.schema.json"
MAX_SCHEMA_ERRORS = 100

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$")

_formats = FormatChecker()


@_formats.checks("date", raises=ValueError)
def _is_date(value: Any) -> bool:
    if not isinstance(value, str):
        return True
    if not _DATE_RE.match(value):
        raise ValueError("not a date")
    date.fromisoformat(value)
    return True


@_formats.checks("date-time", raises=ValueError)
def _is_datetime(value: Any) -> bool:
    if not isinstance(value, str):
        return True
    if not _DATETIME_RE.match(value):
        raise ValueError("not a date-time")
    datetime.fromisoformat(value.replace("z", "Z").replace("Z", "+00:00"))
    return True


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_schema(ctx: ValidationContext | None = None) -> dict:
    path = ctx.schema_path if ctx and ctx.schema_path else DEFAULT_SCHEMA_PATH
    return _load(str(path))


def run_schema(blueprint: Any, schema: dict, report: Report) -> None:
    """Add BP-SCHEMA-001 errors. `version` and `x-validator-rules` are unknown keywords and are ignored."""
    if not isinstance(blueprint, dict):
        report.error("BP-SCHEMA-001", "", "Blueprint must be a JSON object")
        return
    validator = Draft202012Validator(schema, format_checker=_formats)
    errs = sorted(validator.iter_errors(blueprint), key=lambda e: [str(p) for p in e.absolute_path])
    for e in errs[:MAX_SCHEMA_ERRORS]:
        msg = e.message if len(e.message) <= 160 else e.message[:157] + "..."
        report.error("BP-SCHEMA-001", ptr(*e.absolute_path), msg)
    if len(errs) > MAX_SCHEMA_ERRORS:
        report.error("BP-SCHEMA-001", "", f"{len(errs) - MAX_SCHEMA_ERRORS} more schema errors not shown")


def _resolve(schema: dict, root: dict) -> dict:
    seen = 0
    while isinstance(schema, dict) and "$ref" in schema and seen < 20:
        ref = schema["$ref"]
        if not ref.startswith("#/"):
            return {}
        node: Any = root
        for part in ref[2:].split("/"):
            node = node.get(part, {}) if isinstance(node, dict) else {}
        schema, seen = node, seen + 1
    return schema if isinstance(schema, dict) else {}


def walk_refs(instance: Any, schema: dict, root: dict, path: tuple = ()) -> Iterator[tuple[str, tuple, Any]]:
    """Walk `instance` along `schema`, yielding (def_name, path_parts, value) for every position whose
    schema is a $ref to a $defs entry. Robust to new places localizedText may appear, because it
    follows the contract itself (properties, items, additionalProperties, $ref) instead of a path list.
    """
    ref_name = None
    if isinstance(schema, dict) and isinstance(schema.get("$ref"), str) and schema["$ref"].startswith("#/$defs/"):
        ref_name = schema["$ref"].split("/")[-1]
        yield ref_name, path, instance
    node = _resolve(schema, root)
    if isinstance(instance, dict):
        props = node.get("properties", {})
        extra = node.get("additionalProperties")
        for k, v in instance.items():
            if k in props:
                yield from walk_refs(v, props[k], root, path + (k,))
            elif isinstance(extra, dict):
                yield from walk_refs(v, extra, root, path + (k,))
    elif isinstance(instance, list):
        sub = node.get("items")
        if isinstance(sub, dict):
            for i, v in enumerate(instance):
                yield from walk_refs(v, sub, root, path + (i,))
