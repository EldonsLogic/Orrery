"""Allow-listed response projection (ADR-0016): engine output is never passed through raw.

A route declares a schema made of OUR field names. The gateway parses the engine JSON and builds a new
document containing only the declared fields (optionally renamed from an engine key). Everything else,
including `doctype`, `docstatus`, `naming_series`, `__onload`, owner and audit columns, is dropped by
construction. The engine-structure scan on the result is a last resort, not the guard.

Schema language:  str | int | float | bool | {our_key: spec | Field(spec, source=engine_key)} | [spec]
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .markers import ENGINE_FIELD_NAMES, contains_engine_marker, contains_engine_structure

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SCALARS = (str, int, float, bool)
MAX_DEPTH = 12


class RenderError(Exception):
    """A response that cannot be rendered safely. Carries only a fixed reason code, never engine text."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Field:
    spec: object
    source: str | None = None  # engine key to read from when our key differs


def validate_schema(spec: object, _depth: int = 0) -> None:
    """Registration-time check: only our own, engine-free field names may appear in a schema."""
    if _depth > MAX_DEPTH:
        raise ValueError("schema too deep")
    if isinstance(spec, Field):
        validate_schema(spec.spec, _depth + 1)
    elif spec in _SCALARS:
        return
    elif isinstance(spec, list) and len(spec) == 1:
        validate_schema(spec[0], _depth + 1)
    elif isinstance(spec, dict) and spec:
        for key, sub in spec.items():
            if (not isinstance(key, str) or not _KEY_RE.match(key) or key in ENGINE_FIELD_NAMES
                    or contains_engine_marker(key)):
                raise ValueError(f"schema key {key!r} is not one of our own field names")
            validate_schema(sub, _depth + 1)
    else:
        raise ValueError(f"unsupported schema node {spec!r}")


def _project(value: object, spec: object, depth: int) -> object:
    if depth > MAX_DEPTH:
        raise RenderError("projection_mismatch")
    if value is None:
        return None
    if isinstance(spec, Field):
        return _project(value, spec.spec, depth)
    if spec is bool:
        if isinstance(value, bool):
            return value
    elif spec is int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    elif spec is float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    elif spec is str:
        if isinstance(value, str):
            if contains_engine_structure(value):  # last resort, strict patterns only
                raise RenderError("engine_structure_in_body")
            return value
    elif isinstance(spec, list):
        if isinstance(value, list):
            return [_project(item, spec[0], depth + 1) for item in value]
    elif isinstance(spec, dict):
        if isinstance(value, dict):
            out: dict = {}
            for key, sub in spec.items():
                source = sub.source if isinstance(sub, Field) and sub.source else key
                if source in value:
                    out[key] = _project(value[source], sub, depth + 1)
            return out
    raise RenderError("projection_mismatch")


def _reject_constant(_name: str):
    raise ValueError("non-finite number")


def media_type(headers: list[tuple[str, str]]) -> tuple[str, str | None]:
    """(media type, charset) of the Content-Type header, lower-cased; ('', None) when missing."""
    for name, value in headers:
        if name.lower() == "content-type":
            head, *params = [p.strip() for p in value.split(";")]
            charset = next((p.split("=", 1)[1].strip().strip('"').lower() for p in params
                            if p.lower().startswith("charset=")), None)
            return head.lower(), charset
    return "", None


def project_json_body(headers: list[tuple[str, str]], body: bytes, schema: object) -> bytes:
    """Parse the engine JSON body and return our own serialisation of the allow-listed projection.

    Refuses (RenderError) anything that is not strict UTF-8 JSON: UTF-16/32, gzip without a header,
    PDF, HTML, undeclared or non-JSON content types.
    """
    ctype, charset = media_type(headers)
    if not (ctype == "application/json" or ctype.endswith("+json")) or charset not in (None, "utf-8"):
        raise RenderError("undeclared_content_type")
    try:
        data = json.loads(body.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise RenderError("body_not_utf8_json") from None
    projected = _project(data, schema, 0)
    try:
        return json.dumps(projected, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (UnicodeEncodeError, ValueError):
        raise RenderError("body_not_utf8_json") from None
