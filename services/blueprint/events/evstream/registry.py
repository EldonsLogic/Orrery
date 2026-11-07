"""Event type registry: loads schemas/types.json and the JSON Schemas it points at.

The registry files are trusted package data. Event content is never used to build a path.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
KINDS = ("record", "audit", "agent", "meter", "platform")
_ENTITY_RE = re.compile(r"[a-z][a-z0-9_]{0,63}")
_REF_RE = re.compile(r"(data\.[a-z]+\.schema\.json)#(/\$defs/[a-z_]+)")


@dataclass(frozen=True)
class TypeInfo:
    type: str
    schema_version: int
    data_class: str
    kind: str
    scope: str  # tenant | platform
    requires_trace: bool
    data_schema: str
    pattern: str | None = None
    assumed: str | None = None

    @property
    def requires_subject(self) -> bool:
        return self.kind == "record"


class Registry:
    def __init__(self, doc: dict, schema_dir: Path = SCHEMA_DIR):
        self._dir = Path(schema_dir)
        self._reserved = frozenset(doc["reserved_domains"])
        self._raw: dict[str, dict] = doc["types"]
        for name, e in self._raw.items():
            if e["kind"] not in KINDS or e["scope"] not in ("tenant", "platform"):
                raise ValueError(f"registry: bad kind or scope for {name}")
            if not _REF_RE.fullmatch(e["data_schema"]):
                raise ValueError(f"registry: bad data_schema ref for {name}")
        self._files: dict[str, dict] = {}
        self._validators: dict[str, Draft202012Validator] = {}
        self._envelope: Draft202012Validator | None = None

    @classmethod
    def load(cls, schema_dir: Path | str | None = None) -> "Registry":
        d = Path(schema_dir) if schema_dir else SCHEMA_DIR
        doc = json.loads((d / "types.json").read_text(encoding="utf-8"))
        return cls(doc, d)

    # --- lookup
    def _info(self, name: str, key: str) -> TypeInfo:
        e = self._raw[key]
        return TypeInfo(type=name, schema_version=e["schema_version"], data_class=e["data_class"],
                        kind=e["kind"], scope=e["scope"], requires_trace=e["requires_trace"],
                        data_schema=e["data_schema"], pattern=key if key != name else None,
                        assumed=e.get("assumed"))

    def lookup(self, name: object) -> TypeInfo | None:
        if not isinstance(name, str) or len(name) > 130:
            return None
        if name in self._raw:
            return self._info(name, name)
        parts = name.split(".")
        if len(parts) != 2 or not _ENTITY_RE.fullmatch(parts[0]) or parts[0] in self._reserved:
            return None
        key = "<entity>." + parts[1]
        return self._info(name, key) if key in self._raw else None

    def keys(self) -> list[str]:
        """Registry keys: exact type names and <entity>.verb patterns."""
        return sorted(self._raw)

    def entries(self) -> list[TypeInfo]:
        return [self._info(k, k) for k in self.keys()]

    # --- schemas
    def _file(self, fname: str) -> dict:
        if fname not in self._files:
            self._files[fname] = json.loads((self._dir / fname).read_text(encoding="utf-8"))
        return self._files[fname]

    def data_schema(self, ref: str) -> dict:
        m = _REF_RE.fullmatch(ref)
        if not m:
            raise ValueError("bad data schema ref")
        node = self._file(m.group(1))
        for part in m.group(2).strip("/").split("/"):
            node = node[part]
        return node

    def data_validator(self, info: TypeInfo) -> Draft202012Validator:
        if info.data_schema not in self._validators:
            self._validators[info.data_schema] = Draft202012Validator(self.data_schema(info.data_schema))
        return self._validators[info.data_schema]

    def envelope_validator(self) -> Draft202012Validator:
        if self._envelope is None:
            self._envelope = Draft202012Validator(self._file("envelope.schema.json"))
        return self._envelope


_default: Registry | None = None


def default_registry() -> Registry:
    global _default
    if _default is None:
        _default = Registry.load()
    return _default
