"""The drafting port and the validation of what it returns. The model only drafts; this module decides.

A draft is {"manifest": {...}, "spec": {...}, "generalisation": {...}}. Nothing in it is trusted: closed shapes, text
hygiene, scope and risk scans, the component manifest contract (via the registry admission rules) and cross-checks
between spec and manifest all run on a deep copy. A draft that fails is dropped, never repaired.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Protocol

from registry import Registry

from . import codes
from .codes import RequestError
from .text import clean, injection, per_client, personal_data, scope_hits

MAX_DRAFT_BYTES = 60_000
MAX_DEPTH = 8
MODEL_MANIFEST_KEYS = {"id", "version", "kind", "name", "description", "provides", "requires", "parameters", "tests",
                       "engineCompatibility", "i18n", "dataHandling"}
FIELD_TYPES = {"text", "integer", "decimal", "percent", "money", "date", "boolean", "select", "link"}
PERMISSION_ACTIONS = {"read", "list", "create", "update", "export"}   # ADR-0048 item 4: no approve, submit, cancel, amend, delete
SAFE_RISK = {None, "plain"}
_ID = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,4}$")
_SNAKE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_KEY = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+){1,5}$")


class DraftingPort(Protocol):
    """Implemented by a model adapter. `brief` is built by the pipeline from sanitised, structured data only."""

    def draft(self, brief: dict) -> Any: ...


def digest(draft: dict) -> str:
    return hashlib.sha256(json.dumps(draft, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _strings(node: Any, depth: int = 0, keys: bool = True):
    if depth > MAX_DEPTH:
        raise RequestError(codes.MALFORMED_DRAFT, "draft nested too deep")
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            if not isinstance(k, str):
                raise RequestError(codes.MALFORMED_DRAFT, "non-string key")
            if keys:
                yield k
            yield from _strings(v, depth + 1, keys)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v, depth + 1, keys)
    elif node is not None and not isinstance(node, (bool, int)):   # floats, bytes, objects are not JSON data here
        raise RequestError(codes.MALFORMED_DRAFT, f"unsupported value type {type(node).__name__}")


def _closed(obj: Any, keys: set[str], what: str) -> dict:
    if not isinstance(obj, dict) or set(obj) != keys:
        raise RequestError(codes.MALFORMED_DRAFT, f"{what} must be an object with exactly {sorted(keys)}")
    return obj


def _list(obj: Any, what: str, lo: int, hi: int) -> list:
    if not isinstance(obj, list) or not lo <= len(obj) <= hi:
        raise RequestError(codes.MALFORMED_DRAFT, f"{what} must be a list of {lo} to {hi} items")
    return obj


def _text(v: Any, what: str, lo: int, hi: int) -> str:
    if not isinstance(v, str) or not lo <= len(v) <= hi:
        raise RequestError(codes.MALFORMED_DRAFT, f"{what} must be text of {lo} to {hi} characters")
    return v


def validate_draft(raw: Any, request_id: str, fixed_manifest: dict) -> dict:
    """Return a clean draft with the fixed manifest fields added, or raise RequestError. `raw` is never mutated."""
    try:
        blob = json.dumps(raw, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        raise RequestError(codes.MALFORMED_DRAFT, "draft is not JSON data") from None
    if len(blob.encode("utf-8")) > MAX_DRAFT_BYTES:
        raise RequestError(codes.MALFORMED_DRAFT, "draft too large")
    d = copy.deepcopy(raw)
    _closed(d, {"manifest", "spec", "generalisation"}, "draft")
    strings = list(_strings(d))
    for s in strings:                                           # hostile text first: nothing else is evaluated on it
        if clean(s) != s or injection(s) or personal_data(s):
            raise RequestError(codes.HOSTILE_DRAFT, "control or bidi characters, an instruction, personal data or a secret in the draft")
    hits = scope_hits(*strings)
    if hits:
        raise RequestError(codes.FORBIDDEN_SCOPE, f"draft reaches ledger, tax, e-invoicing, payroll or audit scope: {', '.join(hits)}")
    gen = _closed(d["generalisation"], {"rationale", "tenant_specific"}, "generalisation")
    if gen["tenant_specific"] is not False:
        raise RequestError(codes.NOT_GENERALISABLE, "draft says the component is tenant specific")
    _text(gen["rationale"], "generalisation.rationale", 20, 400)
    if per_client(" ".join(_strings(d, 0, False))):
        raise RequestError(codes.PER_CLIENT, "draft is written for one client")

    m = d["manifest"]
    if not isinstance(m, dict) or not set(m) <= MODEL_MANIFEST_KEYS or not {"id", "version", "kind", "name", "description", "provides", "tests"} <= set(m):
        raise RequestError(codes.MALFORMED_DRAFT, "manifest has missing or unexpected top-level keys")
    if m.get("kind") != "configurable":
        raise RequestError(codes.DRAFT_RISK, "an AI draft must be a configurable component")
    for a in (x for p in m["provides"] if isinstance(p, dict) for x in (p.get("artifacts") or []) if isinstance(x, dict)):
        if a.get("riskClass") not in SAFE_RISK:
            raise RequestError(codes.DRAFT_RISK, f"artifact risk class '{a.get('riskClass')}' needs a human-built path")
        if a.get("type") in ("scheduled_job", "tool"):
            raise RequestError(codes.DRAFT_RISK, f"artifact type '{a.get('type')}' needs a human-built path")
    if (m.get("dataHandling") or {}).get("sendsDataToModels") is True:
        raise RequestError(codes.DRAFT_RISK, "draft sends tenant data to models")
    for t in m["tests"] if isinstance(m["tests"], list) else []:
        p = t.get("path") if isinstance(t, dict) else None
        if not isinstance(p, str) or p.startswith("/") or "\\" in p or ".." in p.split("/") or ":" in p:
            raise RequestError(codes.MALFORMED_DRAFT, "test path must be relative and stay inside the component")
    full = {**m, **fixed_manifest, "origin": {"source": "component_factory", "requestId": request_id},
            "certification": {"level": "draft", "touchesLedgerOrTax": False}}
    reg = Registry.from_manifests([full])
    if reg.errors or not reg.list_components():
        raise RequestError(codes.MALFORMED_DRAFT, "manifest fails the component manifest contract: "
                           + "; ".join(i.message for i in reg.errors[:3]))
    m = full
    locales = (m.get("i18n") or {}).get("locales") or []
    if not {"ar", "en"} <= set(locales):
        raise RequestError(codes.MALFORMED_DRAFT, "manifest i18n.locales must include ar and en")

    caps = {p["capability"] for p in m["provides"]}
    entities = {a["ref"] for p in m["provides"] for a in p["artifacts"] if a["type"] == "entity"}
    test_ids = {t["id"]: t for t in m["tests"]}
    s = _closed(d["spec"], {"capabilities", "fields", "permissions", "i18n_keys", "test_plan"}, "spec")
    scaps = _list(s["capabilities"], "spec.capabilities", 1, 20)
    for c in scaps:
        _closed(c, {"id", "summary"}, "capability")
        _text(c["summary"], "capability summary", 5, 200)
    if {c["id"] for c in scaps} != caps or len(scaps) != len(caps) or not all(_ID.match(c["id"]) for c in scaps):
        raise RequestError(codes.MALFORMED_DRAFT, "spec capabilities must equal the manifest provides")
    for f in _list(s["fields"], "spec.fields", 0, 100):
        _closed(f, {"entity", "name", "type", "required"}, "field")
        if f["entity"] not in entities or not isinstance(f["name"], str) or not _SNAKE.match(f["name"]) \
                or f["type"] not in FIELD_TYPES or not isinstance(f["required"], bool):
            raise RequestError(codes.MALFORMED_DRAFT, "field refers to an unknown entity or has a bad name or type")
    for p in _list(s["permissions"], "spec.permissions", 1, 40):
        _closed(p, {"role", "action"}, "permission")
        if not isinstance(p["role"], str) or not _SNAKE.match(p["role"]):
            raise RequestError(codes.MALFORMED_DRAFT, "permission role must be a snake_case role id")
        if p["action"] not in PERMISSION_ACTIONS:
            raise RequestError(codes.DRAFT_RISK, f"permission action '{p['action']}' is not allowed in an AI draft")
    keys = _list(s["i18n_keys"], "spec.i18n_keys", 1, 200)
    if len(set(keys)) != len(keys) or not all(isinstance(k, str) and _KEY.match(k) and k.startswith(m["id"] + ".") for k in keys):
        raise RequestError(codes.MALFORMED_DRAFT, "i18n keys must be unique and start with the component id")
    plan = _list(s["test_plan"], "spec.test_plan", 1, 40)
    for t in plan:
        _closed(t, {"id", "kind", "covers", "blocking"}, "test plan entry")
        mt = test_ids.get(t["id"])
        if mt is None or mt["kind"] != t["kind"] or mt["blocking"] != t["blocking"] or not isinstance(t["covers"], list) \
                or not t["covers"] or not set(t["covers"]) <= caps:
            raise RequestError(codes.MALFORMED_DRAFT, "test plan must match the manifest tests and cover known capabilities")
    kinds = {t["kind"] for t in plan}
    if {t["id"] for t in plan} != set(test_ids) or "unit" not in kinds or not kinds & {"rtl", "arabic_text"} \
            or not any(t["blocking"] for t in plan):
        raise RequestError(codes.MALFORMED_DRAFT, "test plan needs a blocking unit test and an rtl or arabic_text test, and must list every manifest test")
    if set().union(*(set(t["covers"]) for t in plan)) != caps:
        raise RequestError(codes.MALFORMED_DRAFT, "every capability needs a test")
    return {"manifest": m, "spec": s, "generalisation": gen}
