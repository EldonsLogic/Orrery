"""Result and issue types, canonical serialisation and the content hash."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

SET_VERSION = "0.1.0"


@dataclass(frozen=True)
class Issue:
    code: str
    pointer: str
    fact: str

    def __str__(self) -> str:
        return f"{self.code} {self.pointer}: {self.fact}"


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def hash_tools(tools: list[dict]) -> str:
    return "sha256:" + hashlib.sha256(canonical(tools).encode("utf-8")).hexdigest()


def build_set(tools: list[dict], blueprint_revision) -> dict:
    return {
        "toolApiVersion": SET_VERSION,
        "blueprintRevision": blueprint_revision,
        "contentHash": hash_tools(tools),
        "tools": tools,
    }


def to_bytes(definition_set: dict) -> bytes:
    return (json.dumps(definition_set, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


@dataclass
class ToolApiResult:
    tools: list[dict] = field(default_factory=list)
    errors: list[Issue] = field(default_factory=list)
    content_hash: str | None = None
    blueprint_revision: object = None

    @property
    def ok(self) -> bool:
        return not self.errors

    def definition_set(self) -> dict:
        return build_set(self.tools, self.blueprint_revision)
