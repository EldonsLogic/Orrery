"""In-memory fake of the engine adapter (contracts/engine-adapter.md 0.1.2, BPL-025).

Purpose: let the compiler side build and test against the contract before the real adapter exists, and give the
conformance suite (services/blueprint/tests/adapter) a reference that passes every ADP-C item.
It models behaviour only (journaled, recoverable apply of ADR-0028, idempotency, per-site lock, tenant from context,
fail closed). It is NOT evidence about any engine: every engine-specific behaviour is UNVERIFIED.

Public surface: `FakeAdapter.call(operation, context, input) -> response`. Test hooks (faults, probes) exist only when
`test_hooks=True` and are never listed in `capabilities`.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Callable

from .contract import CONTRACTS, artifact_hashes, canon, response_validator, schema_urn, sha, validator_for  # noqa: F401

ADAPTER_ID = "frappe"  # internal id; the sample artifacts name it in engineTarget.adapter (contract open question 12)
ADAPTER_VERSION = "0.1.0"
CONTRACT_VERSIONS = ["0.1.3"]
ARTIFACT_SCHEMA_VERSIONS = ["0.1.0"]
VERSION_SETS = ["set-example", "set-example-2"]
PLAN_TOKEN_TTL = 900
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_STEPS = 500
MAX_MEMBERS = 1000

SERVICES = ["control_plane", "compiler", "simulator", "operate_gateway", "identity", "observability"]
# (allowed services, onBehalfOf rule) from section 4.2
AUTHZ = {
    "capabilities": (SERVICES, "any"),
    "health": (["control_plane", "observability", "operate_gateway"], "any"),
    "site_status": (["control_plane", "compiler", "simulator"], "any"),
    "export_config": (["control_plane", "compiler", "simulator"], "any"),
    "plan": (["control_plane", "compiler", "simulator"], "any"),
    "preview": (["control_plane", "compiler", "simulator"], "any"),
    "provision_site": (["control_plane"], "system_or_user"),
    "apply": (["control_plane"], "change"),
    "rollback": (["control_plane"], "change"),
    "sync_members": (["control_plane", "identity"], "system_or_user"),
}
SCHEMA_OF = {  # operation -> (schema name, request def)
    "capabilities": ("capabilities", "request"), "provision_site": ("site", "provisionRequest"),
    "site_status": ("site", "statusRequest"), "plan": ("plan", "request"), "preview": ("preview", "request"),
    "apply": ("apply", "request"), "rollback": ("rollback", "request"), "export_config": ("export-config", "request"),
    "sync_members": ("sync-members", "request"), "health": ("health", "request"),
}

RETRYABLE = {"site_not_ready", "plan_token_invalid", "concurrent_change", "timeout", "engine_unavailable"}

STEP_KINDS = {  # kind -> (support, phase)
    "settings.set": "supported", "component.enable": "supported", "component.configure": "supported",
    "component.disable": "supported", "location.upsert": "supported", "location.disable": "supported",
    "entity.add": "supported", "entity.set_property": "supported", "entity.quarantine": "supported",
    "field.add": "supported", "field.set_property": "supported", "field.reorder": "supported",
    "field.quarantine": "supported", "option.add": "supported", "option.reorder": "supported",
    "option.quarantine": "supported", "relation.add": "supported", "relation.set_property": "supported",
    "relation.quarantine": "supported", "binding.add": "unsupported", "binding.set_property": "unsupported",
    "binding.disable": "unsupported", "role.upsert": "gated", "role.disable": "gated",
    "workflow.upsert": "supported", "workflow.disable": "supported", "approval.upsert": "supported",
    "approval.disable": "supported", "report.upsert": "supported", "report.disable": "supported",
}
SUPPORTED_TYPES = {"string", "text", "integer", "decimal", "money", "percent", "boolean", "date", "datetime",
                   "select", "link", "phone", "email"}  # 'attachment' is unsupported in the fake
# Protected subjects (ledger, tax, audit, identity). Fixture list; who owns it is open question 16.6.
PROTECTED_ENTITIES = {"general_ledger", "tax_ledger", "audit_log", "user_account", "session_token"}
SEMANTIC_PROPS = {"/type", "/unique", "/indexed", "/precision", "/maxLength", "/required", "/computed"}

SECTION_OF = {"component": "components", "location": "locations", "entity": "entities", "role": "roles",
              "workflow": "workflows", "approval": "approvals", "report": "reports"}
SETTINGS = ("company", "compliance", "i18n")  # exportedProperties keys: settings_company, settings_compliance, settings_intl (contract 5.1)
EXPORTED = {
    "settings_company": ["legalName", "tradeName", "country", "crNumber", "vatNumber", "sizeBand", "industry", "languages", "locale"],
    "settings_compliance": ["country", "countryPack", "eInvoicing", "vat", "hijriDisplay", "documentLanguages", "payroll"],
    "settings_intl": ["defaultLocale", "labelOverrides"],
    "component": ["id", "versionRange"],
    "location": ["id", "kind", "labels", "city"],
    "entity": ["id", "labels", "kind", "numbering", "workflow", "fields", "relations"],
    "field": ["id", "type", "required", "unique", "indexed", "maxLength", "precision", "min", "max", "options",
              "target", "computed", "readOnly", "labels"],
    "relation": ["id", "labels", "target", "kind"],
    "role": ["id", "labels", "function", "scope", "permissions", "isAdmin"],
    "workflow": ["id", "entity", "labels", "states", "transitions"],
    "state": ["id", "kind", "locksEditing", "labels"],
    "transition": ["id", "from", "to", "actionLabels", "allowedRoles", "guards"],
    "approval": ["id", "labels", "appliesTo", "conditions", "steps", "selfApproval"],
    "report": ["id", "kind", "labels", "entity", "metrics", "filters", "visibleToRoles"],
}
CHILDREN = {"entity": {"fields": "field", "relations": "relation"}, "workflow": {"states": "state", "transitions": "transition"}}
ORDERED = {"fields", "options", "states", "steps", "metrics"}  # order-significant collections (5.8)
FORBIDDEN_DETAIL_KEYS = {"stepSeq", "pointer", "postConditionId", "reasonCode", "fields", "limit", "allowed", "actual", "supported"}


_ULID = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid(n: int) -> str:
    out = ""
    for _ in range(26):
        out = _ULID[n % 32] + out
        n //= 32
    return out


class AdapterError(Exception):
    def __init__(self, code: str, details: dict | None = None, stage: str = "validate", retry_after_ms: int | None = None):
        super().__init__(code)
        self.code, self.details, self.stage, self.retry_after_ms = code, details or {}, stage, retry_after_ms

    def to_error(self) -> dict:
        err: dict = {"code": self.code, "messageKey": "errors.adapter." + self.code,
                     "retryable": self.code in RETRYABLE, "stage": self.stage}
        if self.retry_after_ms is not None:
            err["retryAfterMs"] = self.retry_after_ms
        if self.details:
            err["details"] = self.details
        return err


class HooksDisabled(Exception):
    """Raised when a test hook is called on a build without test hooks (ADP-C-069)."""


def _esc(seg: Any) -> str:
    return str(seg).replace("~", "~0").replace("/", "~1")


def _fields_of(errors) -> list[str]:
    fields = set()
    for e in errors:
        base = "".join("/" + _esc(p) for p in e.absolute_path)
        if e.validator == "additionalProperties" and isinstance(e.instance, dict):
            known = set(e.schema.get("properties", {}))
            for k in e.instance:
                if k not in known:
                    fields.add(base + "/" + _esc(k))
        else:
            fields.add(base or "/")
    return sorted(f[:256] for f in fields)[:32]


def _key(elem: dict) -> str:
    """Key of a collection element: `id`, `value` for select options (Blueprint), `order` for approval steps."""
    return str(elem.get("id", elem.get("value", elem.get("order"))))


def _walk(node: Any, segs: list[str]) -> Any:
    """Resolve id-based pointer segments. Returns _MISSING when absent."""
    for seg in segs:
        if isinstance(node, dict):
            if seg not in node:
                return _MISSING
            node = node[seg]
        elif isinstance(node, list):
            hit = [x for x in node if isinstance(x, dict) and _key(x) == seg]
            if not hit:
                return _MISSING
            node = hit[0]
        else:
            return _MISSING
    return node


class _Missing:
    def __repr__(self):
        return "MISSING"


_MISSING = _Missing()


def _segs(pointer: str) -> list[str]:
    return [s.replace("~1", "/").replace("~0", "~") for s in pointer.split("/")[1:]]


def _project(kind: str, node: dict) -> dict:
    out = {}
    for key in EXPORTED[kind]:
        if key in node:
            value = copy.deepcopy(node[key])
            child = CHILDREN.get(kind, {}).get(key)
            if child:
                value = _sorted_children(key, [_project(child, c) for c in value])
            out[key] = value
    return out


def _sorted_children(name: str, items: list) -> list:
    return items if name in ORDERED else sorted(items, key=lambda x: str(x.get("id", "")))


def _set_path(doc: dict, prop: str, params: dict) -> None:
    segs = _segs(prop)
    cur = doc
    for s in segs[:-1]:
        cur = cur.setdefault(s, {})
    if "after" in params:
        cur[segs[-1]] = copy.deepcopy(params["after"])
    else:
        cur.pop(segs[-1], None)


def _statements(step: dict) -> list[str]:
    """Simulated storage statements for a step, kept as internal plan evidence only. Removal is quarantine (a state flag),
    so no statement ever drops or deletes stored data (contract principle 5)."""
    kind, pointer = step["kind"], step["pointer"]
    if kind == "entity.add":
        return [f"CREATE TABLE store_{step['subject']['id']} (id VARCHAR PRIMARY KEY)"]
    if kind == "field.add":
        parent = step["subject"]["parents"][0]["id"]
        return [f"ALTER TABLE store_{parent} ADD COLUMN {step['subject']['id']} NULL"]
    if kind.endswith((".quarantine", ".disable")):
        return [f"UPDATE element_state SET state = '{kind.rsplit('.', 1)[1]}d' WHERE pointer = '{pointer}'"]
    return [f"UPDATE element_config SET value = ? WHERE pointer = '{pointer}'"]


def _prune_empty(doc: dict) -> None:
    for key in [k for k, v in doc.items() if isinstance(v, dict)]:
        _prune_empty(doc[key])
        if not doc[key]:
            del doc[key]


class _Site:
    def __init__(self, params: dict):
        self.state = "ready"
        self.site_class = params["siteClass"]
        self.engine_target = params["engineTarget"]
        self.blueprint_id = params["blueprintId"]
        self.country_pack = params["countryPack"]
        self.applied: dict | None = None
        self.applied_ids: set[str] = set()
        self.history: list[dict] = []  # applied records, newest last; a rollback pops one and "rolls back to" the previous
        self.lock: str | None = None
        self.config = {"settings": {}, **{s: [] for s in SECTION_OF.values()}}
        self.retained: dict[str, dict] = {}
        self.data: dict[str, Any] = {}
        self.members: dict[str, dict] = {}
        self.sync_version = 0
        self.tokens: dict[str, int] = {}
        self.idem: dict[tuple, tuple[str, dict]] = {}
        self.evidence: dict[str, list] = {}

    def status(self) -> dict:
        return {"state": self.state, "siteClass": self.site_class, "engineTarget": copy.deepcopy(self.engine_target),
                "blueprintId": self.blueprint_id, "applied": copy.deepcopy(self.applied), "lockedBy": self.lock}


class FakeAdapter:
    def __init__(self, test_hooks: bool = True):
        self.test_hooks = test_hooks
        self.sites: dict[str, _Site] = {}
        self._events: list[dict] = []
        self._audit: list[dict] = []
        self._seq = 0
        self.now = 0
        self._faults: list[dict] = []
        self._lock_hook: Callable[[], None] | None = None
        self.dropped_data: list[str] = []  # nothing ever appends: the fake never removes stored data (ADP-C-050)
        self._exec_log: list[dict] = []  # every step run, forward or compensating, in order: independent execution evidence (ADP-C-047)

    # ---------------------------------------------------------------- test hooks
    def _need_hooks(self):
        if not self.test_hooks:
            raise HooksDisabled("test hooks are not available in this build")

    def fault(self, stage, step_seq=None, post_condition_id=None, during_compensation=False):
        self._need_hooks()
        self._faults.append({"stage": stage, "step_seq": step_seq, "pc": post_condition_id, "comp": during_compensation})

    def on_lock_held(self, callback: Callable[[], None]):
        self._need_hooks()
        self._lock_hook = callback

    def advance_time(self, seconds: int):
        self._need_hooks()
        self.now += seconds

    def set_site_state(self, tenant_id: str, state: str):
        self._need_hooks()
        self.sites[tenant_id].state = state

    def data_probe(self, tenant_id, pointer, value=None):
        self._need_hooks()
        site = self.sites[tenant_id]
        if value is not None:
            if _walk(site.config, _cfg_segs(pointer)) is _MISSING:
                raise ValueError("no active element at pointer")
            site.data[pointer] = value
        return site.data.get(pointer)

    def plan_evidence(self, tenant_id, evidence_ref):
        """Internal plan evidence (section 5.4): the storage statements a plan would run. Never part of a response."""
        self._need_hooks()
        return list(self.sites[tenant_id].evidence[evidence_ref])

    def execution_journal(self):
        """Every step this adapter ran, forward or compensating, kept apart from the export (ADP-C-047)."""
        self._need_hooks()
        return copy.deepcopy(self._exec_log)

    def auth_probe(self, tenant_id, member_ref):
        self._need_hooks()
        return {"exists": member_ref in self.sites[tenant_id].members, "canAuthenticate": False, "emailSent": False}

    def action_probe(self, tenant_id, member_ref):
        self._need_hooks()
        member = self.sites[tenant_id].members.get(member_ref)
        return {"allowed": bool(member and member["status"] == "active")}

    def events(self) -> list[dict]:
        return copy.deepcopy(self._events)

    def audit_log(self) -> list[dict]:
        return copy.deepcopy(self._audit)

    def reset(self):
        self.__init__(self.test_hooks)

    def _take_fault(self, stage, step_seq=None, pc=None):
        for f in self._faults:
            if f["stage"] == stage and (f["step_seq"] in (None, step_seq)) and (f["pc"] in (None, pc)):
                self._faults.remove(f)
                return f
        return None

    # ---------------------------------------------------------------- envelope
    def _next(self) -> int:
        self._seq += 1
        return self._seq

    def call(self, operation: str, context: Any, input: Any) -> dict:  # noqa: A002 (name from the contract)
        seq = self._next()
        audit = {"auditId": f"aud_{seq:012d}", "operation": operation, "requestId": None, "correlationId": None,
                 "tenant": None, "service": None, "onBehalfOf": None, "inputHash": None, "artifactId": None,
                 "result": None}
        self._audit.append(audit)
        try:
            result, replayed = self._dispatch(operation, context, input, audit)
            response = {"ok": True, "result": result, "auditId": audit["auditId"], "replayed": replayed}
            audit["result"] = "ok" if "status" not in result else result["status"]
        except AdapterError as exc:
            response = {"ok": False, "error": exc.to_error(), "auditId": audit["auditId"]}
            audit["result"] = exc.code
        return response

    def _emit(self, etype: str, data: dict) -> str:
        eid = _ulid(len(self._events) + 1)
        self._events.append({"eventId": eid, "type": etype, "data": data})
        return eid

    def _dispatch(self, op: str, context: Any, inp: Any, audit: dict):
        if op not in SCHEMA_OF:
            raise AdapterError("invalid_request", {"fields": ["/operation"]})
        size = len(canon({"context": context, "input": inp})) if isinstance(inp, dict) else 0
        if size > MAX_REQUEST_BYTES:
            raise AdapterError("limit_exceeded", {"limit": "request_bytes", "allowed": MAX_REQUEST_BYTES, "actual": size})
        errors = list(validator_for("urn:platform:contract:engine-adapter:common:0.1.0#/$defs/context").iter_errors(context))
        if errors or not isinstance(inp, dict):
            raise AdapterError("invalid_request", {"fields": [("/context" + f if f != "/" else "/context") for f in _fields_of(errors)] or ["/input"]})
        audit.update(requestId=context["requestId"], correlationId=context["correlationId"], tenant=context["tenantId"],
                     service=context["caller"]["service"], onBehalfOf=copy.deepcopy(context["caller"]["onBehalfOf"]),
                     inputHash=sha(inp))
        tenant = context["tenantId"]
        site = self.sites.get(tenant)
        self._authorize(op, context, site)
        self._check_contract_version(context["contractVersion"])
        self._prechecks(op, inp)
        schema = SCHEMA_OF[op]
        errors = list(validator_for(schema_urn(schema[0]) + "#/$defs/" + schema[1]).iter_errors({"context": context, "input": inp}))
        if errors:
            raise AdapterError("invalid_request", {"fields": _fields_of(errors)})
        artifact = inp.get("artifact") or inp.get("forwardArtifact")
        if artifact:
            audit["artifactId"] = artifact["artifactId"]
            self._check_integrity(artifact)
            self._check_target(artifact, site)
        if tenant == "platform" and op not in ("capabilities", "health"):
            raise AdapterError("tenant_not_found")
        handler = getattr(self, "_op_" + op)
        return handler(context, inp, site, audit)

    def _authorize(self, op, context, site):
        services, rule = AUTHZ[op]
        who = context["caller"]["onBehalfOf"]
        kind = who["kind"] if who else None
        ok = context["caller"]["service"] in services
        if ok and rule == "system_or_user":
            ok = kind in ("system", "user")
        if ok and rule == "change" and site is not None and site.site_class == "production":
            ok = kind == "user" or (kind == "support" and bool(who.get("supportGrantId")))
        if ok and rule == "change" and site is not None and site.site_class == "sandbox":
            ok = kind is not None
        if ok and rule == "change" and site is None:
            ok = kind is not None
        if not ok:
            self._emit("permission.denied", {"action": op, "resource": "engine_adapter", "reason_code": "service_or_caller_not_allowed"})
            raise AdapterError("permission_denied", stage="authorize")

    def _check_contract_version(self, version: str):
        mm = ".".join(version.split(".")[:2])
        if mm not in {".".join(v.split(".")[:2]) for v in CONTRACT_VERSIONS}:
            raise AdapterError("unsupported_contract_version", {"supported": list(CONTRACT_VERSIONS)})

    def _prechecks(self, op, inp):
        """Limits and artifact schema version are checked before the schema, which would otherwise mask them."""
        art = inp.get("artifact") if op in ("plan", "preview", "apply") else inp.get("forwardArtifact") if op == "rollback" else None
        if isinstance(art, dict):
            if art.get("artifactSchema") not in ARTIFACT_SCHEMA_VERSIONS:
                raise AdapterError("unsupported_contract_version", {"supported": list(ARTIFACT_SCHEMA_VERSIONS)})
            steps = art.get("steps")
            if isinstance(steps, list) and len(steps) > MAX_STEPS:
                raise AdapterError("limit_exceeded", {"limit": "steps_per_artifact", "allowed": MAX_STEPS, "actual": len(steps)})
            size = len(canon(art))
            if size > MAX_ARTIFACT_BYTES:
                raise AdapterError("limit_exceeded", {"limit": "artifact_bytes", "allowed": MAX_ARTIFACT_BYTES, "actual": size})
        if op == "sync_members" and isinstance(inp.get("members"), list) and len(inp["members"]) > MAX_MEMBERS:
            raise AdapterError("limit_exceeded", {"limit": "members_per_sync", "allowed": MAX_MEMBERS, "actual": len(inp["members"])})

    def _check_integrity(self, artifact: dict):
        for art in (artifact, artifact.get("inverse")):
            if art is None:
                continue
            digest, art_id = artifact_hashes(art)
            if art["integrity"]["contentHash"] != digest or art["artifactId"] != art_id:
                raise AdapterError("artifact_integrity_failed")

    def _check_target(self, artifact: dict, site: _Site | None):
        target = artifact["engineTarget"]
        if target["adapter"] != ADAPTER_ID or target["versionSet"] not in VERSION_SETS or (
                site is not None and site.engine_target["versionSet"] != target["versionSet"]):
            raise AdapterError("unsupported_engine_target")

    def _need_site(self, site: _Site | None, ready: bool = True) -> _Site:
        if site is None:
            raise AdapterError("tenant_not_found")
        if ready and site.state in ("provisioning", "failed"):
            raise AdapterError("site_not_ready")
        return site

    # ---------------------------------------------------------------- idempotency
    def _idem_lookup(self, site: _Site, op: str, inp: dict):
        key = (op, inp["idempotencyKey"])
        if key in site.idem:
            stored_hash, stored = site.idem[key]
            if stored_hash != sha(inp):
                raise AdapterError("idempotency_conflict", stage="acquire")
            return copy.deepcopy(stored)
        return None

    def _idem_store(self, site: _Site, op: str, inp: dict, result: dict):
        site.idem[(op, inp["idempotencyKey"])] = (sha(inp), copy.deepcopy(result))

    # ---------------------------------------------------------------- simple operations
    def _op_capabilities(self, context, inp, site, audit):
        kinds = [{"kind": k, "support": v} for k, v in sorted(STEP_KINDS.items())]
        return {"adapterId": ADAPTER_ID, "adapterVersion": ADAPTER_VERSION, "contractVersions": list(CONTRACT_VERSIONS),
                "artifactSchemaVersions": list(ARTIFACT_SCHEMA_VERSIONS), "versionSets": list(VERSION_SETS),
                "stepKinds": kinds,
                "limits": {"maxRequestBytes": MAX_REQUEST_BYTES, "maxStepsPerArtifact": MAX_STEPS,
                           "maxMembersPerSync": MAX_MEMBERS, "planTokenTtlSeconds": PLAN_TOKEN_TTL},
                "exportedProperties": copy.deepcopy(EXPORTED), "idempotencyRetentionSeconds": 30 * 86400,
                "features": {"signatureVerification": False, "previewPredictsExport": True}}, False

    def _op_provision_site(self, context, inp, site, audit):
        tenant = context["tenantId"]
        if tenant == "platform":
            raise AdapterError("invalid_request", {"fields": ["/context/tenantId"]})
        if inp["engineTarget"]["adapter"] != ADAPTER_ID or inp["engineTarget"]["versionSet"] not in VERSION_SETS:
            raise AdapterError("unsupported_engine_target")
        if site is not None:
            stored = self._idem_lookup(site, "provision_site", inp)
            if stored is not None:
                return stored, True
            same = all(getattr(site, a) == v for a, v in (("engine_target", inp["engineTarget"]), ("blueprint_id", inp["blueprintId"]),
                                                          ("site_class", inp["siteClass"]), ("country_pack", inp["countryPack"])))
            if not same:
                raise AdapterError("site_exists_different_target")
            return site.status(), False
        site = self.sites[tenant] = _Site(inp)
        result = site.status()
        self._idem_store(site, "provision_site", inp, result)
        return result, False

    def _op_site_status(self, context, inp, site, audit):
        return self._need_site(site, ready=False).status(), False

    def _op_health(self, context, inp, site, audit):
        if context["tenantId"] == "platform":
            checks = [{"name": "database", "status": "ok"}, {"name": "workers", "status": "ok"}]
        else:
            site = self._need_site(site, ready=False)
            checks = [{"name": "database", "status": "ok"}, {"name": "site_lock", "status": "ok"},
                      {"name": "recovery", "status": "down" if site.state == "recovery_required" else "ok"}]
        order = {"ok": 0, "degraded": 1, "down": 2}
        status = max((c["status"] for c in checks), key=order.get)
        return {"status": status, "adapterVersion": ADAPTER_VERSION, "checks": checks}, False

    def _op_export_config(self, context, inp, site, audit):
        site = self._need_site(site)
        doc = self._export(site)
        return {"exportHash": sha(doc), "export": doc, "retained": self._retained(site)}, False

    def _retained(self, site: _Site) -> list[dict]:
        return [{"pointer": p, "state": r["state"]} for p, r in sorted(site.retained.items())]

    def _export(self, site: _Site, config: dict | None = None) -> dict:
        cfg = site.config if config is None else config
        sections: dict[str, Any] = {"settings": {}}
        for name in SETTINGS:
            if name in cfg["settings"]:
                sections["settings"][name] = _project("settings_intl" if name == "i18n" else "settings_" + name, cfg["settings"][name])
        for kind, section in SECTION_OF.items():
            sections[section] = sorted((_project(kind, e) for e in cfg[section]), key=lambda e: e["id"])
        rev = site.applied["revision"] if site.applied else None
        return {"exportSchema": "0.1.0", "engineTarget": copy.deepcopy(site.engine_target),
                "blueprintId": site.blueprint_id, "revision": copy.deepcopy(rev), "sections": sections}

    # ---------------------------------------------------------------- plan and preview
    def _plan_checks(self, site: _Site, artifact: dict):
        if artifact["blueprint"]["id"] != site.blueprint_id:
            raise AdapterError("blueprint_mismatch")
        base = artifact["blueprint"]["base"]
        if base != (site.applied["revision"] if site.applied else None):
            raise AdapterError("base_revision_mismatch")

    def _evaluate(self, site: _Site, artifact: dict) -> dict:
        steps, additive, semantic = [], 0, 0
        for step in artifact["steps"]:
            disp, reason, ddl = self._judge(site, step)
            if ddl == "additive":
                additive += 1
            elif ddl == "semantic":
                semantic += 1
            entry = {"seq": step["seq"], "disposition": disp, "ddlImpact": ddl}
            if reason:
                entry["reasonCode"] = reason
            steps.append(entry)
        if site.state == "recovery_required":
            steps = [{"seq": s["seq"], "disposition": "blocked", "ddlImpact": s["ddlImpact"], "reasonCode": "recovery_required"} for s in steps]
        kinds = {s["disposition"] for s in steps}
        verdict = "rejected" if kinds & {"blocked", "unsupported"} else "needs_gate_approval" if "gated" in kinds else "auto_approved"
        return {"steps": steps, "verdict": verdict, "storage": {"additive": additive, "semantic": semantic, "statementCount": additive + semantic}}

    def _judge(self, site: _Site, step: dict) -> tuple[str, str | None, str]:
        kind, pointer, params = step["kind"], step["pointer"], step["params"]
        ddl = step["ddlImpact"]
        support = STEP_KINDS.get(kind, "unsupported")
        if support == "unsupported":
            return "unsupported", "unsupported_step_kind", ddl
        if kind in ("field.add", "relation.add", "entity.add"):
            ddl = "additive" if ddl == "none" else ddl
        if kind.endswith("set_property") and params.get("property") in SEMANTIC_PROPS:
            ddl = "semantic"
        segs = _segs(pointer)
        if segs[:1] == ["entities"] and len(segs) > 1 and segs[1] in PROTECTED_ENTITIES:
            return "blocked", "protected_subject", ddl
        defn = params.get("definition")
        coll = self._collection(site, segs)
        elem = _walk(site.config, _cfg_segs(pointer))
        if kind.endswith((".add", ".upsert", ".enable")):
            if coll is None:
                return "blocked", "subject_missing", ddl
            held = site.retained.get(pointer)
            if held is not None:
                if held["definition"] != defn:
                    return "blocked", "definition_conflict", ddl
            elif elem is not _MISSING and kind.endswith(".add"):
                return "blocked", "subject_exists", ddl
            reason = self._storage_reason(defn) if ddl != "none" or kind in ("field.add", "entity.add") else None
            if reason and reason[0] == "blocked":
                return "blocked", reason[1], ddl
            if reason:
                return "gated", reason[1], ddl
        elif kind.endswith((".quarantine", ".disable")):
            if elem is _MISSING:
                return "blocked", "subject_missing", ddl
            if kind == "role.disable" and any(segs[1] in m["roleIds"] and m["status"] == "active" for m in site.members.values()):
                return "blocked", "subject_in_use", ddl
        elif kind != "settings.set" and elem is _MISSING:
            return "blocked", "subject_missing", ddl
        if ddl == "semantic":
            return "gated", "storage_not_additive", ddl
        if support == "gated":
            return "gated", "protected_subject", ddl
        return "ok", None, ddl

    @staticmethod
    def _storage_reason(defn: Any) -> tuple[str, str] | None:
        fields = defn.get("fields", [defn]) if isinstance(defn, dict) else []
        for f in fields:
            if "type" in f and f["type"] not in SUPPORTED_TYPES:
                return "blocked", "unsupported_value_type"
        if any(f.get("unique") or f.get("indexed") for f in fields):
            return "gated", "unique_or_index"
        return None

    def _collection(self, site: _Site, segs: list[str]):
        """The list or dict that would hold the element at segs, or None if the parent is missing."""
        if segs[0] in SETTINGS:
            return site.config["settings"]
        parent = _walk(site.config, segs[:-1])
        return None if parent is _MISSING else parent

    def _token(self, tenant: str, content_hash: str, config_hash: str) -> str:
        return "pln_" + hashlib.sha256(f"{tenant}|{content_hash}|{config_hash}|{ADAPTER_VERSION}".encode()).hexdigest()[:40]

    def _op_plan(self, context, inp, site, audit):
        site = self._need_site(site)
        artifact = inp["artifact"]
        self._plan_checks(site, artifact)
        result = self._evaluate(site, artifact)
        config_hash = sha(self._export(site))
        token = self._token(context["tenantId"], artifact["integrity"]["contentHash"], config_hash)
        site.tokens[token] = self.now
        evidence = "evd_" + hashlib.sha256(token.encode()).hexdigest()[:24]
        site.evidence[evidence] = [stmt for step in artifact["steps"] for stmt in _statements(step)]
        return {"planToken": token, "artifactId": artifact["artifactId"], "siteConfigHash": config_hash,
                "verdict": result["verdict"], "steps": result["steps"], "storage": result["storage"],
                "evidenceRef": evidence, "expiresInSeconds": PLAN_TOKEN_TTL}, False

    def _op_preview(self, context, inp, site, audit):
        site = self._need_site(site)
        artifact = inp["artifact"]
        self._plan_checks(site, artifact)
        result = self._evaluate(site, artifact)
        out = {"artifactId": artifact["artifactId"], "siteConfigHash": sha(self._export(site)),
               "verdict": result["verdict"], "predictedExportHash": None, "delta": []}
        if result["verdict"] != "rejected":
            trial = copy.deepcopy(site)
            for step in artifact["steps"]:
                self._exec(trial, step)
            trial.applied = {"artifactId": artifact["artifactId"], "revision": copy.deepcopy(artifact["blueprint"]["target"])}
            doc = self._export(trial)
            out["predictedExportHash"] = sha(doc)
            if inp.get("includeExport"):
                out["predictedExport"] = doc
            out["delta"] = self._delta(site, artifact)
        return out, False

    def _delta(self, site: _Site, artifact: dict) -> list[dict]:
        rows = []
        for step in artifact["steps"]:
            kind, pointer = step["kind"], step["pointer"]
            held = site.retained.get(pointer)
            exists = _walk(site.config, _cfg_segs(pointer)) is not _MISSING
            if kind.endswith(".quarantine"):
                change = "quarantine"
            elif kind.endswith(".disable"):
                change = "disable"
            elif kind.endswith(".reorder"):
                change = "reorder"
            elif kind.endswith(".enable"):
                change = "restore" if held else "enable"
            elif kind.endswith((".add", ".upsert")):
                change = "restore" if held else "replace" if exists else "add"
            else:
                change = "replace"
            row = {"change": change, "pointer": pointer}
            if kind.endswith(("set_property", "settings.set", ".configure")):
                row["property"] = step["params"]["property"]
            rows.append(row)
        return sorted(rows, key=lambda r: (r["pointer"], r.get("property", "")))

    # ---------------------------------------------------------------- step execution
    def _exec(self, site: _Site, step: dict) -> None:
        kind, pointer, params = step["kind"], step["pointer"], step["params"]
        segs = _segs(pointer)
        cfg = site.config
        if kind == "settings.set":
            doc = cfg["settings"].setdefault(segs[0], {})
            _set_path(doc, params["property"], params)
            if "after" not in params:  # a property removed (an undone first set): leave no empty settings shell behind
                _prune_empty(doc)
                if not doc:
                    del cfg["settings"][segs[0]]
        elif kind.endswith((".set_property", ".configure")):
            elem = _walk(cfg, segs)
            _set_path(elem, params["property"], params)
        elif kind.endswith(".reorder"):
            node = _walk(cfg, segs)
            node = node if isinstance(node, list) else node.get("fields", node.get("options"))
            node.sort(key=lambda e: params["order"].index(_key(e)))
        elif kind.endswith((".quarantine", ".disable")):
            coll = _walk(cfg, segs[:-1])
            idx = next(i for i, e in enumerate(coll) if _key(e) == segs[-1])
            site.retained[pointer] = {"state": "quarantined" if kind.endswith(".quarantine") else "disabled",
                                      "definition": coll.pop(idx), "index": idx}
        else:  # add, upsert, enable
            coll = _walk(cfg, segs[:-1])
            held = site.retained.pop(pointer, None)
            defn = copy.deepcopy(params["definition"])
            idx = next((i for i, e in enumerate(coll) if _key(e) == segs[-1]), None)
            if held is not None:
                coll.insert(min(held["index"], len(coll)), held["definition"])
            elif idx is not None:
                coll[idx] = defn
            else:
                coll.append(defn)

    def _evaluate_pc(self, doc: dict, retained: dict, pc: dict) -> bool:
        pointer, check = pc["pointer"], pc["check"]
        segs = _segs(pointer)
        sections = doc["sections"]
        node = _walk({**sections, **sections["settings"]}, segs)
        if check == "exists":
            return node is not _MISSING
        if check in ("quarantined", "disabled"):
            held = retained.get(pointer)
            return bool(held and held["state"] == check) and node is _MISSING
        if check == "property_equals":
            return node is not _MISSING and _walk(node, _segs(pc["property"])) == pc["expected"]
        if check == "count_equals":
            return isinstance(node, list) and len(node) == pc["expected"]
        if check == "order_equals":
            return isinstance(node, list) and [_key(e) for e in node] == pc["expected"]
        return False

    # ---------------------------------------------------------------- apply and rollback
    def _op_apply(self, context, inp, site, audit):
        return self._run(context, inp, self._need_site(site), "apply", audit)

    def _op_rollback(self, context, inp, site, audit):
        return self._run(context, inp, self._need_site(site), "rollback", audit)

    def _event_data(self, operation, status, artifact, target_rev, error):
        if status == "applied":
            if operation == "apply":
                return "blueprint.applied", {"change_id": artifact["artifactId"], "revision": target_rev}
            return "blueprint.rolled_back", {"change_id": artifact["artifactId"], "revision": target_rev}
        return "blueprint.apply_failed", {"change_id": artifact["artifactId"], "revision": target_rev, "error_code": error["code"]}

    def _run(self, context, inp, site: _Site, operation: str, audit: dict):
        stored = self._idem_lookup(site, operation, inp)
        if stored is not None:
            return stored, True
        if site.lock is not None:
            raise AdapterError("concurrent_change", stage="acquire", retry_after_ms=1000)
        forward = inp["artifact"] if operation == "apply" else inp["forwardArtifact"]
        artifact = forward if operation == "apply" else forward.get("inverse") or forward
        op_id = f"op_{self._next():012d}"
        stages: list[dict] = []
        steps = [{"seq": s["seq"], "status": "not_run"} for s in artifact["steps"]]
        pcs: list[dict] = []
        state = {"status": None, "error": None, "export_hash": None}
        timed_out = {"v": False}
        if site.state == "ready":
            site.lock, site.state = op_id, "applying"
        stages.append({"stage": "acquire", "status": "done"})

        def finish(status, error=None, hash_after=None):
            state.update(status=status, error=error, export_hash=hash_after)

        pre_hash = sha(self._export(site))
        try:
            self._inspect(context, inp, site, operation, forward, artifact)
        except _Early as early:
            stages.append({"stage": "inspect", "status": "done" if early.status == "already_applied" else "failed"})
            finish(early.status, early.error, pre_hash if early.status == "already_applied" else None)
            if early.status == "already_applied":
                steps = [{"seq": s["seq"], "status": "already_present"} for s in artifact["steps"]]
        else:
            stages.append({"stage": "inspect", "status": "done"})
            self._execute_all(site, artifact, steps, pcs, stages, finish, pre_hash, timed_out, operation,
                              forward if operation == "rollback" else artifact.get("inverse"))
        if site.lock == op_id:
            site.lock = None
            if site.state == "applying":
                site.state = "ready"
        status, error = state["status"], state["error"]
        target_rev = artifact["blueprint"]["target"]["revision"]
        outcome = {"operationId": op_id, "operation": operation, "artifactId": artifact["artifactId"], "status": status,
                   "stages": stages, "steps": steps, "postConditions": pcs, "site": site.status()}
        if state["export_hash"]:
            outcome["exportHash"] = state["export_hash"]
        if error:
            outcome["error"] = error
        if status != "already_applied":
            etype, data = self._event_data(operation, status, forward if operation == "rollback" and status == "applied" else artifact,
                                           artifact["blueprint"]["target"]["revision"], error)
            if operation == "rollback" and status == "applied":
                data["revision"] = forward["blueprint"]["base"]["revision"] if forward["blueprint"]["base"] else target_rev
            outcome["eventIds"] = [self._emit(etype, data)]
        self._idem_store(site, operation, inp, outcome)
        if timed_out["v"]:
            raise AdapterError("timeout", stage="execute")
        return outcome, False

    def _inspect(self, context, inp, site: _Site, operation: str, forward: dict, artifact: dict):
        def reject(code, details=None):
            raise _Early("rejected", AdapterError(code, details, stage="inspect").to_error())
        if site.state == "recovery_required":
            reject("recovery_required")
        if operation == "apply" and site.applied and site.applied["artifactId"] == artifact["artifactId"]:
            raise _Early("already_applied", None)
        if operation == "apply":
            self._verify_token(context, inp, site, artifact, reject)
        if operation == "rollback":
            if forward["artifactId"] not in site.applied_ids:
                reject("artifact_not_found")
            if not site.applied or site.applied["artifactId"] != forward["artifactId"]:
                reject("rollback_not_possible", {"reasonCode": "not_latest"})
            if forward.get("inverse") is None:
                reject("rollback_not_possible", {"reasonCode": "no_inverse"})
            if forward["risk"]["irreversibleSteps"] > 0:
                reject("rollback_not_possible", {"reasonCode": "irreversible_step"})
        try:
            self._plan_checks(site, artifact)
        except AdapterError as exc:
            reject(exc.code)
        result = self._evaluate(site, artifact)
        if result["verdict"] == "rejected":
            bad = next(s for s in result["steps"] if s["disposition"] in ("blocked", "unsupported"))
            if bad.get("reasonCode") == "unsupported_step_kind" and operation == "apply":
                reject("unsupported_step_kind", {"stepSeq": bad["seq"], "reasonCode": bad["reasonCode"]})
            reject("plan_rejected", {"stepSeq": bad["seq"], "reasonCode": bad["reasonCode"]})
        approvals = inp["approvals"]
        need = ["changeApproved"] if operation == "apply" else ["rollbackApproved"]
        if result["verdict"] == "needs_gate_approval":
            need.append("gateApproved")
        if operation == "apply" and artifact["risk"]["requiresTeamReview"]:
            need.append("teamReviewed")
        missing = [n for n in need if n not in approvals]
        if missing:
            reject("approval_missing", {"fields": ["/approvals/" + m for m in missing]})

    def _verify_token(self, context, inp, site, artifact, reject):
        token = inp["planToken"]
        issued = site.tokens.get(token)
        expected = self._token(context["tenantId"], artifact["integrity"]["contentHash"], sha(self._export(site)))
        if issued is None or token != expected or self.now - issued > PLAN_TOKEN_TTL:
            reject("plan_token_invalid")

    def _execute_all(self, site, artifact, steps, pcs, stages, finish, pre_hash, timed_out, operation="apply", counterpart=None):
        if self._take_fault("prepare"):
            stages.append({"stage": "prepare", "status": "failed"})
            finish("failed_clean", AdapterError("engine_unavailable", stage="prepare").to_error())
            return
        journal: list[dict] = []  # the durable step journal: one entry per step started, in execution order
        stages.append({"stage": "prepare", "status": "done"})
        failure: AdapterError | None = None
        comp_fault = False
        if self._lock_hook:
            hook, self._lock_hook = self._lock_hook, None
            hook()
        for step, entry in zip(artifact["steps"], steps):
            seq = step["seq"]
            entry_j = {"artifactId": artifact["artifactId"], "seq": seq, "step": step, "executed": False, "before": self._read_prop(site, step)}
            journal.append(entry_j)
            if self._take_fault("deadline", seq):
                timed_out["v"] = True
            fault = self._take_fault("execute", seq)
            if fault:
                entry["status"], failure, comp_fault = "failed", AdapterError("engine_unavailable", {"stepSeq": seq}, stage="execute"), fault["comp"]
                break
            self._exec_log.append({"artifactId": artifact["artifactId"], "seq": seq, "phase": "execute"})
            self._exec(site, step)
            entry_j["executed"] = True
            entry["status"] = "applied"
        stages.append({"stage": "execute", "status": "failed" if failure else "done"})
        doc = self._export(site, None)
        if not failure:
            fail_pc = next((f for f in self._faults if f["stage"] == "reconcile"), None)
            if fail_pc:
                self._faults.remove(fail_pc)
            for pc in artifact["postConditions"]:
                passed = self._evaluate_pc(doc, site.retained, pc)
                if fail_pc and (fail_pc["pc"] in (None, pc["id"])):
                    passed = False
                pcs.append({"id": pc["id"], "passed": passed})
                if not passed and failure is None:
                    failure = AdapterError("postcondition_failed", {"postConditionId": pc["id"]}, stage="reconcile")
                    comp_fault = bool(fail_pc and fail_pc["comp"])
            stages.append({"stage": "reconcile", "status": "failed" if failure else "done"})
        if failure:
            self._compensate(site, steps, stages, finish, journal, pre_hash, failure, comp_fault, counterpart)
            return
        if self._take_fault("finalize"):
            site.state = "recovery_required"
            stages.append({"stage": "finalize", "status": "failed"})
            finish("recovery_required", AdapterError("recovery_required", stage="finalize").to_error())
            return
        if operation == "rollback":
            site.history.pop()
            site.applied = copy.deepcopy(site.history[-1]) if site.history else None
        else:
            site.applied = {"artifactId": artifact["artifactId"], "revision": copy.deepcopy(artifact["blueprint"]["target"])}
            site.history.append(copy.deepcopy(site.applied))
        site.applied_ids.add(artifact["artifactId"])
        stages.append({"stage": "finalize", "status": "done"})
        finish("applied", None, sha(self._export(site)))

    @staticmethod
    def _read_prop(site: _Site, step: dict):
        """The value a settings.set step is about to overwrite, kept in the journal for steps that carry no stored inverse."""
        if step["kind"] != "settings.set":
            return None
        cur = site.config["settings"].get(_segs(step["pointer"])[0], {})
        for seg in _segs(step["params"]["property"]):
            cur = cur.get(seg, _MISSING) if isinstance(cur, dict) else _MISSING
        return _MISSING if cur is _MISSING else copy.deepcopy(cur)

    @staticmethod
    def _undo_for(entry: dict, counterpart: dict | None, used: set) -> dict:
        """The step that undoes a journaled step: the matching step (same pointer and property) of the stored inverse
        (section 5.6, compensate). An artifact with no stored inverse (initial build, base null) has none, so the undo is
        derived from the journal (section 5.6.2): additions are quarantined or disabled, settings are set back to the
        journaled prior value; any other kind cannot be compensated (recovery_required)."""
        step = entry["step"]
        if counterpart is not None:
            key = (step["pointer"], step["params"].get("property"))
            for cand in counterpart["steps"]:
                if id(cand) not in used and (cand["pointer"], cand["params"].get("property")) == key:
                    used.add(id(cand))
                    return cand
            raise RuntimeError("the stored inverse has no step for " + step["pointer"])
        kind = step["kind"]
        if kind == "settings.set":
            params = {"property": step["params"]["property"]}
            if entry["before"] is not _MISSING:
                params["after"] = entry["before"]
            return {**step, "params": params}
        if kind.endswith(".add"):
            return {**step, "kind": kind[:-4] + ".quarantine"}
        if kind.endswith((".upsert", ".enable")):
            return {**step, "kind": kind.rsplit(".", 1)[0] + ".disable"}
        raise RuntimeError("no stored inverse for " + kind)

    def _compensate(self, site, steps, stages, finish, journal, pre_hash, failure, comp_fault, counterpart):
        """Undo the journaled steps newest first by running their inverse steps; then check the active export equals the
        pre-apply export. Quarantined leftovers of compensated additions stay in `retained` (section 5.6)."""
        used: set = set()
        try:
            for entry in reversed(journal):
                if comp_fault:
                    raise RuntimeError("compensation fault")
                status = next(s for s in steps if s["seq"] == entry["seq"])
                if entry["executed"]:
                    self._exec_log.append({"artifactId": entry["artifactId"], "seq": entry["seq"], "phase": "compensate"})
                    self._exec(site, self._undo_for(entry, counterpart, used))
                    status["status"] = "compensated"
                else:
                    status["status"] = "failed"  # the failing step never took effect in the fake
            if sha(self._export(site)) != pre_hash:
                raise RuntimeError("compensated state differs from the pre-apply export")
        except Exception:  # any failed undo leaves a partial state a human must resolve
            site.state = "recovery_required"
            stages.append({"stage": "compensate", "status": "failed"})
            finish("recovery_required", AdapterError("recovery_required", stage="compensate").to_error())
            return
        stages.append({"stage": "compensate", "status": "done"})
        finish("compensated", failure.to_error(), pre_hash)

    # ---------------------------------------------------------------- members
    def _op_sync_members(self, context, inp, site, audit):
        site = self._need_site(site)
        stored = self._idem_lookup(site, "sync_members", inp)
        if stored is not None:
            return stored, True
        if inp["syncVersion"] <= site.sync_version:
            raise AdapterError("stale_sync_version")
        active_roles = {e["id"] for e in site.config["roles"]}
        unknown = sorted({r for m in inp["members"] for r in m["roleIds"] if r not in active_roles})
        if unknown:
            raise AdapterError("unknown_role", {"fields": ["/members/roleIds"]})
        created = updated = disabled = unchanged = 0
        listed = set()
        for m in inp["members"]:
            listed.add(m["memberRef"])
            new = {"status": m["status"], "roleIds": sorted(m["roleIds"]), "displayName": m.get("displayName")}
            old = site.members.get(m["memberRef"])
            if old is None:
                created += 1
            elif old == new:
                unchanged += 1
            else:
                updated += 1
                disabled += int(old["status"] == "active" and new["status"] == "disabled")
            site.members[m["memberRef"]] = new
        if inp["mode"] == "full":
            for ref, member in site.members.items():
                if ref not in listed and member["status"] == "active":
                    member["status"] = "disabled"
                    disabled += 1
        site.sync_version = inp["syncVersion"]
        result = {"syncVersion": site.sync_version, "created": created, "updated": updated, "disabled": disabled, "unchanged": unchanged}
        self._idem_store(site, "sync_members", inp, result)
        return result, False


def _cfg_segs(pointer: str) -> list[str]:
    """Segments for walking site.config (settings pointers live under 'settings')."""
    segs = _segs(pointer)
    return ["settings"] + segs if segs and segs[0] in SETTINGS else segs


class _Early(Exception):
    def __init__(self, status: str, error: dict | None):
        super().__init__(status)
        self.status, self.error = status, error
