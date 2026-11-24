"""The drafting port and the validation of what it returns. The model only drafts; this module decides.

A draft is {"manifest": {...}, "spec": {...}, "generalisation": {...}}. Nothing in it is trusted: closed shapes, text
hygiene, scope and risk scans, the component manifest contract (via the registry admission rules) and cross-checks
between spec and manifest all run on a deep copy. A draft that fails is dropped, never repaired.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
from typing import Any, Protocol

from registry import Registry

from factory.errors import FacError
from factory.scan import check_relpath

from . import codes, policy
from .codes import RequestError
from .text import clean, foreign_letters, injection, per_client, personal_data, scope_hits

MAX_DRAFT_BYTES = 60_000
MAX_DEPTH = 8
MODEL_MANIFEST_KEYS = {"id", "version", "kind", "name", "description", "provides", "requires", "parameters", "tests",
                       "engineCompatibility", "i18n", "dataHandling"}
PERMISSION_ACTIONS = {"read", "list", "create", "update", "export"}   # ADR-0048 item 4: no approve, submit, cancel, amend, delete
_ID = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,4}$")
_SNAKE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_KEY = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+){1,5}$")


class DraftingPort(Protocol):
    """Implemented by a model adapter. `brief` is built by the pipeline from sanitised, structured data only."""

    def draft(self, brief: dict) -> Any: ...


def digest(draft: dict, key: bytes | None = None) -> str:
    """sha256 of the canonical draft, or HMAC-SHA256 with a host key. An unkeyed digest detects accidents only: whoever
    can write the store can recompute it (PR 216 M6), so a deployment passes `integrity_key`."""
    blob = json.dumps(draft, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hmac.new(key, blob, hashlib.sha256).hexdigest() if key else hashlib.sha256(blob).hexdigest()


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


def validate_draft(raw: Any, request_id: str, fixed_manifest: dict, library: Any = None) -> dict:
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
        if clean(s) != s or injection(s) or personal_data(s) or foreign_letters(s):
            raise RequestError(codes.HOSTILE_DRAFT, "control or bidi characters, look-alike letters, an instruction, personal data or a secret in the draft")
    hits = scope_hits(*strings)
    if hits:
        raise RequestError(codes.FORBIDDEN_SCOPE, "draft reaches ledger, tax, e-invoicing, payroll or audit scope")
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
    _artifacts(m)
    if (m.get("dataHandling") or {}).get("sendsDataToModels") is True:
        raise RequestError(codes.DRAFT_RISK, "draft sends tenant data to models")
    for t in m["tests"] if isinstance(m["tests"], list) else []:
        _test_path(t.get("path") if isinstance(t, dict) else None)
    _requires(m.get("requires"), library)
    full = {**m, **fixed_manifest, "origin": {"source": "component_factory", "requestId": request_id},
            "certification": {"level": "draft", "touchesLedgerOrTax": False}}
    reg = Registry.from_manifests([full])
    if reg.errors or not reg.list_components():
        raise RequestError(codes.MALFORMED_DRAFT, "manifest fails the component manifest contract")
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
        if not isinstance(f, dict) or not {"entity", "name", "type", "required"} <= set(f) <= {"entity", "name", "type", "required", "options", "target"}:
            raise RequestError(codes.MALFORMED_DRAFT, "field has missing or unexpected keys")
        if f["entity"] not in entities or not isinstance(f["name"], str) or not _SNAKE.match(f["name"]) \
                or f["type"] not in policy.SHAPE_FIELD_TYPES or not isinstance(f["required"], bool):
            raise RequestError(codes.MALFORMED_DRAFT, "field refers to an unknown entity or has a bad name or type")
        opts, tgt = f.get("options"), f.get("target")
        if ("options" in f) != (f["type"] == "select") or ("target" in f) != (f["type"] == "link") \
                or (opts is not None and not (isinstance(opts, list) and 1 <= len(opts) <= 30 and len(set(opts)) == len(opts)
                                              and all(isinstance(o, str) and _SNAKE.match(o) for o in opts))) \
                or (tgt is not None and (not isinstance(tgt, str) or not _SNAKE.match(tgt))):
            raise RequestError(codes.MALFORMED_DRAFT, "select needs a closed options list and link needs a target, nothing else")
        if policy.field_verdict(entities, f, library)[0] == "refuse":
            raise RequestError(codes.FORBIDDEN_SCOPE, "a field reaches sensitive data, money movement or a restricted scope")
    for p in _list(s["permissions"], "spec.permissions", 1, 40):
        _closed(p, {"role", "action"}, "permission")
        if not isinstance(p["role"], str) or not _SNAKE.match(p["role"]):
            raise RequestError(codes.MALFORMED_DRAFT, "permission role must be a snake_case role id")
        if policy.platform_role(p["role"]):
            raise RequestError(codes.DRAFT_RISK, "permission role is a platform or restricted role")
        if p["action"] not in PERMISSION_ACTIONS:
            raise RequestError(codes.DRAFT_RISK, "permission action is not allowed in an AI draft")
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
    for ident in [*caps, *entities, *keys, *test_ids, *(f["name"] for f in s["fields"]), *(x["id"] for x in m.get("parameters", []))]:
        if policy.identifier_hits(ident):
            raise RequestError(codes.FORBIDDEN_SCOPE, "an identifier reaches ledger, tax, e-invoicing, payroll, audit or identity scope")
    return {"manifest": m, "spec": s, "generalisation": gen}


def _artifacts(m: dict) -> None:
    """Allow-list of artifact kinds. Scope comes from policy.classify, never from the model: a firm no is refused here,
    an unproven artifact is left for the human classification step (classify_draft), and a model risk class other than
    `plain` is refused. A proven entity is stamped `plain` by us."""
    for p in m["provides"] if isinstance(m["provides"], list) else []:
        for a in p.get("artifacts", []) if isinstance(p, dict) and isinstance(p.get("artifacts"), list) else []:
            if not isinstance(a, dict) or a.get("type") not in policy.ALLOWED_ARTIFACTS:
                raise RequestError(codes.DRAFT_RISK, "artifact kind is not on the allow-list for an AI draft")
            ref = a.get("ref")
            if not isinstance(ref, str):
                raise RequestError(codes.MALFORMED_DRAFT, "artifact ref must be text")
            verdict, _ = policy.classify(a["type"], ref.split("/")[-1])
            if verdict == "refuse":
                raise RequestError(codes.FORBIDDEN_SCOPE, "artifact scope is refused by the reviewed policy")
            if a["type"] == "entity":
                if a.get("riskClass", "plain") != "plain":
                    raise RequestError(codes.DRAFT_RISK, "declared risk class differs from the derived class")
                a.pop("riskClass", None)
                if verdict == "plain":
                    a["riskClass"] = "plain"


def classify_draft(d: dict, library: Any = None) -> dict:
    """Structural class of a validated draft: proven plain, or the reasons a human must classify it."""
    reasons: set[str] = set()
    money = False
    entities = {a["ref"] for p in d["manifest"]["provides"] for a in p["artifacts"] if a["type"] == "entity"}
    for p in d["manifest"]["provides"]:
        for a in p["artifacts"]:
            if policy.classify(a["type"], a["ref"].split("/")[-1])[0] != "plain":
                reasons.add("artifact_name")
    for f in d["spec"]["fields"]:
        v, why = policy.field_verdict(entities, f, library)
        money = money or why == "money_field"
        if v != "plain":
            reasons.add(why)
    return {"proven": not reasons, "reasons": sorted(reasons), "has_money_field": money}


def _test_path(p: Any) -> None:
    try:
        check_relpath(p)
    except FacError:
        raise RequestError(codes.MALFORMED_DRAFT, "test path must be relative and stay inside the component") from None
    segs = p.split("/")
    if segs[0] != "tests" or len(segs) < 2 or any(x.startswith(".") for x in segs):
        raise RequestError(codes.MALFORMED_DRAFT, "test path must sit under tests/ with no hidden or dot segments")


def _requires(req: Any, library: Any) -> None:
    """A `requires` is allowed only on an admitted library manifest whose artifacts all derive as plain."""
    if req in (None, []):
        return
    if not isinstance(req, list) or library is None:
        raise RequestError(codes.DRAFT_RISK, "requires needs a library to check against")
    for r in req:
        cid, cap = (r.get("component"), r.get("capability")) if isinstance(r, dict) else (None, None)
        found = []
        for c in library.list_components():
            for v in library.versions(c):
                m = library.get(c, v)
                if isinstance(m, dict) and (c == cid or (cap and any(isinstance(p, dict) and p.get("capability") == cap
                                                                     for p in m.get("provides", [])))):
                    found.append(m)
        if not found or not all(policy.manifest_all_plain(m) for m in found):
            raise RequestError(codes.DRAFT_RISK, "requires an unknown component or one with a non-plain scope")
