"""Contract helpers shared by the fake and the test kit: canonical JSON, hashes, schema validators (sections 5.8, 9.1)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
RESPONSE_SCHEMA = {"rollback": "apply", "provision_site": "site", "site_status": "site", "export_config": "export-config",
                   "sync_members": "sync-members"}
OPERATION_SCHEMA = {"capabilities": "capabilities", "plan": "plan", "preview": "preview", "apply": "apply", "health": "health"}


def canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canon(value)).hexdigest()


def artifact_hashes(artifact: dict) -> tuple[str, str]:
    """(contentHash, artifactId) per section 9.1."""
    body = {k: v for k, v in artifact.items() if k not in ("artifactId", "integrity")}
    digest = sha(body)
    return digest, "art_" + digest[7:39]


def _schemas() -> tuple[Registry, dict]:
    registry, by_id = Registry(), {}
    for path in sorted(CONTRACTS.rglob("*.schema.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(data, default_specification=DRAFT202012)
        registry = registry.with_resource(data["$id"], resource)
        by_id[data["$id"]] = data
    return registry, by_id


_REGISTRY, _BY_ID = _schemas()
_VALIDATORS: dict[str, Draft202012Validator] = {}


def validator_for(ref: str) -> Draft202012Validator:
    if ref not in _VALIDATORS:
        _VALIDATORS[ref] = Draft202012Validator({"$ref": ref}, registry=_REGISTRY)
    return _VALIDATORS[ref]


def schema_urn(name: str) -> str:
    return f"urn:platform:contract:engine-adapter:{name}:0.1.0"


def response_validator(operation: str) -> Draft202012Validator:
    name = RESPONSE_SCHEMA.get(operation) or OPERATION_SCHEMA[operation]
    return validator_for(schema_urn(name) + "#/$defs/response")
