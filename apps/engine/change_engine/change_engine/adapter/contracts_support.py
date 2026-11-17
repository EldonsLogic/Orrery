"""Canonical JSON, hashing, and contract schema validation for the engine adapter."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    _HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover - embedded runtime without jsonschema
    Draft202012Validator = None
    Registry = None
    Resource = None
    DRAFT202012 = None
    _HAS_JSONSCHEMA = False


ADAPTER_DIR = Path(__file__).resolve().parent


def _discover_contracts_dir() -> Path | None:
    env_dir = os.environ.get("ORRERY_CONTRACTS_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.is_dir():
            return p
    for parent in ADAPTER_DIR.parents:
        cand = parent / "contracts"
        if (cand / "engine-adapter").is_dir() and (cand / "compiled-artifact.schema.json").is_file():
            return cand
    return None


CONTRACTS_DIR = _discover_contracts_dir()

SCHEMA_OF = {
    "capabilities": ("capabilities", "request"),
    "provision_site": ("site", "provisionRequest"),
    "site_status": ("site", "statusRequest"),
    "plan": ("plan", "request"),
    "preview": ("preview", "request"),
    "apply": ("apply", "request"),
    "rollback": ("rollback", "request"),
    "export_config": ("export-config", "request"),
    "sync_members": ("sync-members", "request"),
    "health": ("health", "request"),
}

_VALIDATOR_CACHE: dict[str, Any] = {}
_REGISTRY_CACHE: tuple[Any, dict[str, dict]] | None = None


def canon(value: Any) -> bytes:
    """Canonical JSON per contracts/engine-adapter.md section 5.8."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha(value: Any) -> str:
    """SHA-256 hex digest with 'sha256:' prefix over canonical JSON."""
    return "sha256:" + hashlib.sha256(canon(value)).hexdigest()


def artifact_hashes(artifact: dict[str, Any]) -> tuple[str, str]:
    """Return (contentHash, artifactId) per contracts/engine-adapter.md section 9.1."""
    body = {k: v for k, v in artifact.items() if k not in ("artifactId", "integrity")}
    digest = sha(body)
    return digest, "art_" + digest[7:39]


def schema_urn(name: str) -> str:
    return f"urn:platform:contract:engine-adapter:{name}:0.1.0"


def _load_registry() -> tuple[Any, dict[str, dict]] | None:
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None:
        return _REGISTRY_CACHE
    if not _HAS_JSONSCHEMA or CONTRACTS_DIR is None:
        return None
    registry, by_id = Registry(), {}
    for path in sorted(CONTRACTS_DIR.rglob("*.schema.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(data, default_specification=DRAFT202012)
        registry = registry.with_resource(data["$id"], resource)
        by_id[data["$id"]] = data
    _REGISTRY_CACHE = (registry, by_id)
    return _REGISTRY_CACHE


def _validator_for(ref: str) -> Any | None:
    if ref in _VALIDATOR_CACHE:
        return _VALIDATOR_CACHE[ref]
    loaded = _load_registry()
    if loaded is None:
        return None
    registry, _ = loaded
    validator = Draft202012Validator({"$ref": ref}, registry=registry)
    _VALIDATOR_CACHE[ref] = validator
    return validator


def _esc(seg: Any) -> str:
    return str(seg).replace("~", "~0").replace("/", "~1")


def _fields_of(errors: list[Any]) -> list[str]:
    fields: set[str] = set()
    for err in errors:
        base = "".join("/" + _esc(p) for p in err.absolute_path)
        if err.validator == "additionalProperties" and isinstance(err.instance, dict):
            known = set(err.schema.get("properties", {}))
            for key in err.instance:
                if key not in known:
                    fields.add(base + "/" + _esc(key))
        elif err.validator == "maxProperties" and isinstance(err.instance, dict):
            known = set(err.schema.get("properties", {}))
            extra = [k for k in err.instance if k not in known]
            if extra:
                for key in extra:
                    fields.add(base + "/" + _esc(key))
            else:
                fields.add(base or "/")
        else:
            fields.add(base or "/")
    return sorted(f[:256] for f in fields)[:32]


_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
_TENANT_RE = re.compile(r"^(t_[a-z0-9_]{3,63}|platform)$")
_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$")
_CORR_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
_SUPPORT_GRANT_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_SERVICES = {"control_plane", "compiler", "simulator", "operate_gateway", "identity", "observability"}


def validate_context(context: Any) -> list[str]:
    """Validate envelope context, returning JSON pointer fields for any violation."""
    validator = _validator_for(schema_urn("common") + "#/$defs/context")
    if validator is not None:
        errors = list(validator.iter_errors(context))
        if not errors:
            return []
        return [("/context" + f if f != "/" else "/context") for f in _fields_of(errors)]

    # Pure-Python fallback when jsonschema / contracts dir is unavailable
    if not isinstance(context, dict):
        return ["/context"]
    bad: list[str] = []
    req = {"contractVersion", "requestId", "correlationId", "tenantId", "caller", "deadlineMs"}
    for key in context:
        if key not in req:
            bad.append(f"/context/{_esc(key)}")
    for key in req - set(context):
        bad.append("/context")
    if "contractVersion" in context and not (isinstance(context["contractVersion"], str) and _SEMVER_RE.match(context["contractVersion"])):
        bad.append("/context/contractVersion")
    if "requestId" in context and not (isinstance(context["requestId"], str) and _ULID_RE.match(context["requestId"])):
        bad.append("/context/requestId")
    if "correlationId" in context and not (isinstance(context["correlationId"], str) and _CORR_RE.match(context["correlationId"])):
        bad.append("/context/correlationId")
    if "tenantId" in context and not (isinstance(context["tenantId"], str) and _TENANT_RE.match(context["tenantId"])):
        bad.append("/context/tenantId")
    deadline = context.get("deadlineMs")
    if "deadlineMs" in context and (isinstance(deadline, bool) or not isinstance(deadline, int) or not (1 <= deadline <= 3600000)):
        bad.append("/context/deadlineMs")
    caller = context.get("caller")
    if "caller" in context:
        if not isinstance(caller, dict) or set(caller) != {"service", "onBehalfOf"}:
            bad.append("/context/caller")
        else:
            if caller.get("service") not in _SERVICES:
                bad.append("/context/caller/service")
            who = caller.get("onBehalfOf")
            if who is not None:
                if not isinstance(who, dict) or "kind" not in who or "id" not in who:
                    bad.append("/context/caller/onBehalfOf")
                elif who.get("kind") == "support" and not (
                    isinstance(who.get("supportGrantId"), str) and _SUPPORT_GRANT_RE.match(who["supportGrantId"])
                ):
                    bad.append("/context/caller/onBehalfOf")
    return sorted(set(bad))[:32]


def validate_operation_request(op: str, context: dict[str, Any], inp: dict[str, Any]) -> list[str]:
    """Validate full {context, input} against the operation schema."""
    schema_name, schema_def = SCHEMA_OF[op]
    validator = _validator_for(schema_urn(schema_name) + "#/$defs/" + schema_def)
    if validator is not None:
        errors = list(validator.iter_errors({"context": context, "input": inp}))
        if not errors:
            return []
        return _fields_of(errors)

    # Pure-Python minimal structural fallback
    if op in ("capabilities", "site_status", "export_config", "health"):
        if inp:
            return [f"/input/{_esc(k)}" for k in sorted(inp)]
        return []
    return []
