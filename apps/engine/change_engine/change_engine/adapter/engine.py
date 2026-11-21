"""ChangeEngineAdapter implementing contracts/engine-adapter.md v0.1.2 (BPL-012).

Bridges Blueprint compiled artifacts to change_engine guarded-apply primitives
(ddl_plan_gate, safety_guardrails, schema_reconciler) and an AdapterStore holding the durable
per-tenant state (MariaDB on the tenant database in production, ADR-0041; SQLite for dev and
tests only), step journaling, and additive-only non-destructive schema state.
"""
from __future__ import annotations

import copy
import hashlib
import re
import secrets
import time
import uuid
from typing import Any, Callable

from change_engine.adapter.contracts_support import (
    artifact_hashes,
    canon,
    sha,
    validate_context,
    validate_operation_request,
)
from change_engine.adapter.mapping import (
    PROTECTED_ENTITY_IDS,
    SEMANTIC_PROPS,
    SUPPORTED_BLUEPRINT_TYPES,
    bounded_site_lock_key,
    has_prohibited_expression,
    inspect_field_ddl,
    is_protected_entity,
    plan_statements_for_step,
)
from change_engine.adapter.storage import SQLiteAdapterStore, SiteRecord, TenantMismatch
from change_engine.adapter.store_api import AdapterStore, StoreRefused, assert_store_allowed, is_production

ADAPTER_ID = "frappe"
ADAPTER_VERSION = "0.1.0"
CONTRACT_VERSIONS = ["0.1.2"]
ARTIFACT_SCHEMA_VERSIONS = ["0.1.0"]
VERSION_SETS = ["set-example", "set-example-2"]
PLAN_TOKEN_TTL = 900
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_STEPS = 500
MAX_MEMBERS = 1000

SERVICES = [
    "control_plane",
    "compiler",
    "simulator",
    "operate_gateway",
    "identity",
    "observability",
]

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

OPERATIONS = set(AUTHZ)
RETRYABLE = {"site_not_ready", "plan_token_invalid", "concurrent_change", "timeout", "engine_unavailable"}

STEP_KINDS = {
    "settings.set": "supported",
    "component.enable": "supported",
    "component.configure": "supported",
    "component.disable": "supported",
    "location.upsert": "supported",
    "location.disable": "supported",
    "entity.add": "supported",
    "entity.set_property": "supported",
    "entity.quarantine": "supported",
    "field.add": "supported",
    "field.set_property": "supported",
    "field.reorder": "supported",
    "field.quarantine": "supported",
    "option.add": "supported",
    "option.reorder": "supported",
    "option.quarantine": "supported",
    "relation.add": "supported",
    "relation.set_property": "supported",
    "relation.quarantine": "supported",
    "binding.add": "unsupported",
    "binding.set_property": "unsupported",
    "binding.disable": "unsupported",
    "role.upsert": "gated",
    "role.disable": "gated",
    "workflow.upsert": "supported",
    "workflow.disable": "supported",
    "approval.upsert": "supported",
    "approval.disable": "supported",
    "report.upsert": "supported",
    "report.disable": "supported",
}

SECTION_OF = {
    "component": "components",
    "location": "locations",
    "entity": "entities",
    "role": "roles",
    "workflow": "workflows",
    "approval": "approvals",
    "report": "reports",
}
SETTINGS = ("company", "compliance", "i18n")

EXPORTED = {
    "settings_company": ["legalName", "tradeName", "country", "crNumber", "vatNumber", "sizeBand", "industry", "languages", "locale"],
    "settings_compliance": ["country", "countryPack", "eInvoicing", "vat", "hijriDisplay", "documentLanguages", "payroll"],
    "settings_intl": ["defaultLocale", "labelOverrides"],
    "component": ["id", "versionRange"],
    "location": ["id", "kind", "labels", "city"],
    "entity": ["id", "labels", "kind", "numbering", "workflow", "fields", "relations"],
    "field": [
        "id",
        "type",
        "required",
        "unique",
        "indexed",
        "maxLength",
        "precision",
        "min",
        "max",
        "options",
        "target",
        "computed",
        "readOnly",
        "labels",
    ],
    "relation": ["id", "labels", "target", "kind"],
    "role": ["id", "labels", "function", "scope", "permissions", "isAdmin"],
    "workflow": ["id", "entity", "labels", "states", "transitions"],
    "state": ["id", "kind", "locksEditing", "labels"],
    "transition": ["id", "from", "to", "actionLabels", "allowedRoles", "guards"],
    "approval": ["id", "labels", "appliesTo", "conditions", "steps", "selfApproval"],
    "report": ["id", "kind", "labels", "entity", "metrics", "filters", "visibleToRoles"],
}
CHILDREN = {
    "entity": {"fields": "field", "relations": "relation"},
    "workflow": {"states": "state", "transitions": "transition"},
}
ORDERED = {"fields", "options", "states", "steps", "metrics"}

_ULID = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid(n: int) -> str:
    out = ""
    for _ in range(26):
        out = _ULID[n % 32] + out
        n //= 32
    return out


def _new_event_id() -> str:
    """Time-ordered, collision-free across workers: 48-bit milliseconds then 80 random bits, as a ULID."""
    return _ulid((int(time.time() * 1000) << 80) | secrets.randbits(80))


class AdapterError(Exception):
    def __init__(
        self,
        code: str,
        details: dict[str, Any] | None = None,
        stage: str = "validate",
        retry_after_ms: int | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.details = details or {}
        self.stage = stage
        self.retry_after_ms = retry_after_ms

    def to_error(self) -> dict[str, Any]:
        err: dict[str, Any] = {
            "code": self.code,
            "messageKey": "errors.adapter." + self.code,
            "retryable": self.code in RETRYABLE,
            "stage": self.stage,
        }
        if self.retry_after_ms is not None:
            err["retryAfterMs"] = self.retry_after_ms
        if self.details:
            err["details"] = self.details
        return err


class HooksDisabled(Exception):
    """Raised when a test hook is called on a production adapter instance."""


class _Missing:
    def __repr__(self) -> str:
        return "MISSING"


_MISSING = _Missing()


class _LeaseLost(Exception):
    """This worker no longer owns its operation (lease expired, or another worker recovered it): stop, write nothing."""


class _Early(Exception):
    def __init__(self, status: str, error: dict[str, Any] | None):
        super().__init__(status)
        self.status = status
        self.error = error


def _segs(pointer: str) -> list[str]:
    return [s.replace("~1", "/").replace("~0", "~") for s in pointer.split("/")[1:]]


def _cfg_segs(pointer: str) -> list[str]:
    segs = _segs(pointer)
    return ["settings"] + segs if segs and segs[0] in SETTINGS else segs


def _walk(node: Any, segs: list[str]) -> Any:
    for seg in segs:
        if isinstance(node, dict):
            if seg not in node:
                return _MISSING
            node = node[seg]
        elif isinstance(node, list):
            hit = [x for x in node if isinstance(x, dict) and str(x.get("id", x.get("order"))) == seg]
            if not hit:
                return _MISSING
            node = hit[0]
        else:
            return _MISSING
    return node


def _sorted_children(name: str, items: list[Any]) -> list[Any]:
    return items if name in ORDERED else sorted(items, key=lambda x: str(x.get("id", "")))


def _project(kind: str, node: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in EXPORTED[kind]:
        if key in node:
            value = copy.deepcopy(node[key])
            child = CHILDREN.get(kind, {}).get(key)
            if child:
                value = _sorted_children(key, [_project(child, c) for c in value])
            out[key] = value
    return out


def _set_path(doc: dict[str, Any], prop: str, params: dict[str, Any]) -> None:
    segs = _segs(prop)
    cur = doc
    for seg in segs[:-1]:
        cur = cur.setdefault(seg, {})
    if "after" in params:
        cur[segs[-1]] = copy.deepcopy(params["after"])
    else:
        cur.pop(segs[-1], None)


def _prune_empty(doc: dict[str, Any]) -> None:
    for key in [k for k, v in doc.items() if isinstance(v, dict)]:
        _prune_empty(doc[key])
        if not doc[key]:
            del doc[key]


class ChangeEngineAdapter:
    """Real engine adapter backed by change_engine guarded_apply, an AdapterStore, and optional FrappeRuntimeBackend.

    Fails closed: test hooks are off unless asked for, and are refused (like a volatile or file-based store) when the
    environment is production or unknown (ADR-0041). `lease_seconds` is how long a worker may hold an operation before
    another worker may recover it; keep it above the longest operation (the contract deadline is at most one hour).
    """

    def __init__(
        self,
        test_hooks: bool = False,
        db_path: str = ":memory:",
        frappe_backend: Any | None = None,
        store: AdapterStore | None = None,
        environment: str | None = None,
        lease_seconds: int = 3900,
    ) -> None:
        production = is_production(test_hooks, environment)
        if production and test_hooks:
            raise StoreRefused("test hooks are refused in production (unset, empty or unknown environments count as production)")
        if store is None and production:
            raise StoreRefused("no adapter store given: production needs MariaDB on the tenant database (ADR-0041)")
        self.test_hooks = test_hooks
        self.db_path = db_path
        self.lease_seconds = lease_seconds
        self.store = store if store is not None else SQLiteAdapterStore(db_path=db_path)
        assert_store_allowed(self.store, production)
        self.frappe_backend = frappe_backend
        self.now = 0
        self._faults: list[dict[str, Any]] = []
        self._lock_hook: Callable[[], None] | None = None
        self.recover_interrupted()

    @staticmethod
    def _site_snapshot(site: SiteRecord) -> dict[str, Any]:
        return {
            "state": site.state,
            "site_class": site.site_class,
            "engine_target": site.engine_target,
            "blueprint_id": site.blueprint_id,
            "country_pack": site.country_pack,
            "applied": site.applied,
            "applied_ids": set(site.applied_ids),
            "history": site.history,
            "sync_version": site.sync_version,
            "config": site.config,
            "retained": site.retained,
        }

    def execute_as_caller(
        self,
        tenant_id: str,
        caller: dict[str, Any] | None,
        fn: Callable[[Any], Any],
    ) -> Any:
        """Execute a tenant operation under caller's own Frappe User permissions (T36)."""
        if self.frappe_backend is None:
            raise AdapterError("engine_unavailable", stage="execute")
        try:
            return self.frappe_backend.execute_as_caller(tenant_id, caller, fn)
        except AdapterError:
            raise
        except Exception as exc:
            code = getattr(exc, "code", "engine_unavailable")
            details = getattr(exc, "details", {})
            stage = getattr(exc, "stage", "execute")
            raise AdapterError(code, details, stage=stage) from None

    # ------------------------------------------------------------------ test hooks
    def _need_hooks(self) -> None:
        if not self.test_hooks:
            raise HooksDisabled("test hooks are not available in this build")

    def fault(
        self,
        stage: str,
        step_seq: int | None = None,
        post_condition_id: str | None = None,
        during_compensation: bool = False,
    ) -> None:
        self._need_hooks()
        self._faults.append(
            {
                "stage": stage,
                "step_seq": step_seq,
                "pc": post_condition_id,
                "comp": during_compensation,
            }
        )

    def on_lock_held(self, callback: Callable[[], None]) -> None:
        self._need_hooks()
        self._lock_hook = callback

    def advance_time(self, seconds: int) -> None:
        self._need_hooks()
        self.now += seconds

    def _get_or_hydrate_site(self, tenant_id: str) -> SiteRecord | None:
        site = self.store.get_site(tenant_id)
        if site is not None or self.frappe_backend is None or tenant_id == "platform":
            return site
        loader = getattr(self.frappe_backend, "load_site_state", None)
        if not callable(loader):
            return None
        snap = loader(tenant_id)
        if not snap:
            return None
        params = {
            "siteClass": snap["site_class"],
            "engineTarget": snap["engine_target"],
            "blueprintId": snap["blueprint_id"],
            "countryPack": snap["country_pack"],
        }
        site = SiteRecord(tenant_id, params)
        site.state = snap["state"]
        site.applied = copy.deepcopy(snap["applied"])
        site.applied_ids = set(snap["applied_ids"])
        site.history = copy.deepcopy(snap["history"])
        site.sync_version = int(snap["sync_version"])
        site.config = copy.deepcopy(snap["config"])
        site.retained = copy.deepcopy(snap["retained"])
        return self.store.hydrate_site(site)

    def set_site_state(self, tenant_id: str, state: str) -> None:
        self._need_hooks()
        site = self._get_or_hydrate_site(tenant_id)
        if site is None:
            raise KeyError(tenant_id)
        site.state = state
        self.store.save_site(site)
        if self.frappe_backend is not None:
            self.frappe_backend.persist_site_state(tenant_id, self._site_snapshot(site))

    def data_probe(self, tenant_id: str, pointer: str, value: Any = None) -> Any:
        self._need_hooks()
        site = self._get_or_hydrate_site(tenant_id)
        if site is None:
            raise KeyError(tenant_id)
        segs = _segs(pointer)
        entity_id = segs[1] if segs[:1] == ["entities"] and len(segs) >= 2 else "_global"
        if value is not None:
            if _walk(site.config, _cfg_segs(pointer)) is _MISSING:
                raise ValueError("no active element at pointer")
            if self.frappe_backend is not None and entity_id != "_global":
                return self.frappe_backend.data_probe(tenant_id, pointer, value)
            return self.store.write_field_data(tenant_id, entity_id, pointer, value)
        if self.frappe_backend is not None and entity_id != "_global":
            return self.frappe_backend.data_probe(tenant_id, pointer, None)
        return self.store.read_field_data(tenant_id, entity_id, pointer)

    def plan_evidence(self, tenant_id: str, evidence_ref: str) -> list[str]:
        self._need_hooks()
        if self._get_or_hydrate_site(tenant_id) is None:
            raise KeyError(tenant_id)
        return self.store.get_evidence(tenant_id, evidence_ref)

    def execution_journal(self) -> list[dict[str, Any]]:
        self._need_hooks()
        return self.store.execution_journal()

    def auth_probe(self, tenant_id: str, member_ref: str) -> dict[str, Any]:
        self._need_hooks()
        if self._get_or_hydrate_site(tenant_id) is None:
            raise KeyError(tenant_id)
        if self.frappe_backend is not None:
            return self.frappe_backend.auth_probe(tenant_id, member_ref)
        member = self.store.get_member(tenant_id, member_ref)
        if member is None:
            return {"exists": False, "canAuthenticate": False, "emailSent": False}
        return {
            "exists": True,
            "canAuthenticate": member["canAuthenticate"],
            "emailSent": member["emailSent"],
        }

    def action_probe(self, tenant_id: str, member_ref: str) -> dict[str, Any]:
        self._need_hooks()
        if self._get_or_hydrate_site(tenant_id) is None:
            raise KeyError(tenant_id)
        if self.frappe_backend is not None:
            return self.frappe_backend.action_probe(tenant_id, member_ref)
        member = self.store.get_member(tenant_id, member_ref)
        return {"allowed": bool(member and member["status"] == "active")}

    def dropped_data(self) -> list[str]:
        return list(self.store.dropped_data)

    def events(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        return self.store.events(tenant_id)

    def audit_log(self) -> list[dict[str, Any]]:
        return self.store.audit_log()

    def reset(self) -> None:
        self._need_hooks()
        self.store.reset()
        if self.frappe_backend is not None:
            self.frappe_backend.reset_site()
        self.now = 0
        self._faults.clear()
        self._lock_hook = None

    def _take_fault(self, stage: str, step_seq: int | None = None, pc: str | None = None) -> dict[str, Any] | None:
        for f in self._faults:
            if f["stage"] == stage and (f["step_seq"] in (None, step_seq)) and (f["pc"] in (None, pc)):
                self._faults.remove(f)
                return f
        return None

    # ------------------------------------------------------------------ envelope & authz
    @staticmethod
    def _new_id(prefix: str) -> str:
        """Collision-free across workers sharing one database (an in-process counter is not)."""
        return f"{prefix}_{uuid.uuid4().hex[:24]}"

    def call(self, operation: str, context: Any, input: Any) -> dict[str, Any]:  # noqa: A002
        audit = {
            "auditId": self._new_id("aud"),
            "operation": operation,
            "requestId": None,
            "correlationId": None,
            "tenant": None,
            "service": None,
            "onBehalfOf": None,
            "inputHash": None,
            "artifactId": None,
            "result": None,
        }
        self.store.insert_audit(audit)
        try:
            result, replayed = self._dispatch(operation, context, input, audit)
            response: dict[str, Any] = {
                "ok": True,
                "result": result,
                "auditId": audit["auditId"],
                "replayed": replayed,
            }
            audit["result"] = "ok" if "status" not in result else result["status"]
        except AdapterError as exc:
            response = {"ok": False, "error": exc.to_error(), "auditId": audit["auditId"]}
            audit["result"] = exc.code
        except TenantMismatch:  # a store bound to another tenant (misrouted connection): it looks like an unknown tenant here
            err = AdapterError("tenant_not_found")
            response = {"ok": False, "error": err.to_error(), "auditId": audit["auditId"]}
            audit["result"] = err.code
            audit["tenant"] = None  # never write the foreign tenant id into this tenant's audit log
        except Exception as exc:
            code = getattr(exc, "code", None)
            if isinstance(code, str):
                err = AdapterError(code, getattr(exc, "details", None), stage=getattr(exc, "stage", "execute"))
            else:
                err = AdapterError("engine_unavailable", stage="execute")
            response = {"ok": False, "error": err.to_error(), "auditId": audit["auditId"]}
            audit["result"] = err.code
        finally:
            self.store.update_audit(audit)
        return response

    def _emit(self, etype: str, data: dict[str, Any], tenant_id: str | None = None) -> str:
        eid = _new_event_id()
        self.store.append_event(eid, etype, data, tenant_id)
        return eid

    def _dispatch(self, op: str, context: Any, inp: Any, audit: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        if op not in OPERATIONS:
            raise AdapterError("invalid_request", {"fields": ["/operation"]})
        size = len(canon({"context": context, "input": inp})) if isinstance(inp, dict) else 0
        if size > MAX_REQUEST_BYTES:
            raise AdapterError(
                "limit_exceeded",
                {"limit": "request_bytes", "allowed": MAX_REQUEST_BYTES, "actual": size},
            )
        ctx_fields = validate_context(context)
        if ctx_fields or not isinstance(inp, dict):
            raise AdapterError("invalid_request", {"fields": ctx_fields or ["/input"]})

        audit.update(
            requestId=context["requestId"],
            correlationId=context["correlationId"],
            tenant=context["tenantId"],
            service=context["caller"]["service"],
            onBehalfOf=copy.deepcopy(context["caller"]["onBehalfOf"]),
            inputHash=sha(inp),
        )
        tenant = context["tenantId"]
        site = self._get_or_hydrate_site(tenant)
        self._authorize(op, context, site)
        self._check_contract_version(context["contractVersion"])
        self._prechecks(op, inp)
        req_fields = validate_operation_request(op, context, inp)
        if req_fields:
            raise AdapterError("invalid_request", {"fields": req_fields})

        artifact = inp.get("artifact") or inp.get("forwardArtifact")
        if artifact:
            audit["artifactId"] = artifact["artifactId"]
            self._check_integrity(artifact)
            self._check_target(artifact, site)

        if tenant == "platform" and op not in ("capabilities", "health"):
            raise AdapterError("tenant_not_found")

        handler = getattr(self, "_op_" + op)
        return handler(context, inp, site, audit)

    def _authorize(self, op: str, context: dict[str, Any], site: SiteRecord | None) -> None:
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
            self._emit(
                "permission.denied",
                {"action": op, "resource": "engine_adapter", "reason_code": "service_or_caller_not_allowed"},
                context["tenantId"],
            )
            raise AdapterError("permission_denied", stage="authorize")

    def _check_contract_version(self, version: str) -> None:
        mm = ".".join(version.split(".")[:2])
        if mm not in {".".join(v.split(".")[:2]) for v in CONTRACT_VERSIONS}:
            raise AdapterError("unsupported_contract_version", {"supported": list(CONTRACT_VERSIONS)})

    def _prechecks(self, op: str, inp: dict[str, Any]) -> None:
        art = (
            inp.get("artifact")
            if op in ("plan", "preview", "apply")
            else inp.get("forwardArtifact")
            if op == "rollback"
            else None
        )
        if isinstance(art, dict):
            if art.get("artifactSchema") not in ARTIFACT_SCHEMA_VERSIONS:
                raise AdapterError("unsupported_contract_version", {"supported": list(ARTIFACT_SCHEMA_VERSIONS)})
            steps = art.get("steps")
            if isinstance(steps, list) and len(steps) > MAX_STEPS:
                raise AdapterError(
                    "limit_exceeded",
                    {"limit": "steps_per_artifact", "allowed": MAX_STEPS, "actual": len(steps)},
                )
            size = len(canon(art))
            if size > MAX_ARTIFACT_BYTES:
                raise AdapterError(
                    "limit_exceeded",
                    {"limit": "artifact_bytes", "allowed": MAX_ARTIFACT_BYTES, "actual": size},
                )
        if op == "sync_members" and isinstance(inp.get("members"), list) and len(inp["members"]) > MAX_MEMBERS:
            raise AdapterError(
                "limit_exceeded",
                {"limit": "members_per_sync", "allowed": MAX_MEMBERS, "actual": len(inp["members"])},
            )

    def _check_integrity(self, artifact: dict[str, Any]) -> None:
        for art in (artifact, artifact.get("inverse")):
            if art is None:
                continue
            digest, art_id = artifact_hashes(art)
            if art["integrity"]["contentHash"] != digest or art["artifactId"] != art_id:
                raise AdapterError("artifact_integrity_failed")

    def _check_target(self, artifact: dict[str, Any], site: SiteRecord | None) -> None:
        target = artifact["engineTarget"]
        if (
            target["adapter"] != ADAPTER_ID
            or target["versionSet"] not in VERSION_SETS
            or (site is not None and site.engine_target["versionSet"] != target["versionSet"])
        ):
            raise AdapterError("unsupported_engine_target")

    def _need_site(self, site: SiteRecord | None, ready: bool = True) -> SiteRecord:
        if site is None:
            raise AdapterError("tenant_not_found")
        if ready and site.state in ("provisioning", "failed"):
            raise AdapterError("site_not_ready")
        return site

    # ------------------------------------------------------------------ idempotency (ADR-0041)
    def _acquire(
        self,
        tenant: str,
        op: str,
        inp: dict[str, Any],
        op_id: str,
        *,
        lock: bool = False,
        pending: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> tuple[str, Any]:
        """Reserve (tenant, op, key) for this input before any effect, in the database, atomically.

        Returns ("acquired", None), ("replay", stored outcome) or ("in_progress", the pending outcome of the running
        operation); a different input raises idempotency_conflict, a held site lock raises concurrent_change. A lock or
        lease left behind by a dead worker is recovered once (recover_interrupted) before giving up."""
        for attempt in (0, 1):
            status, info = self.store.acquire_operation(
                tenant, op, inp["idempotencyKey"], sha(inp), op_id, pending or {}, meta or {},
                lock=lock, lease_seconds=self.lease_seconds,
            )
            stale = status == "locked" or (status == "in_progress" and info["expired"])
            if stale and attempt == 0 and self.recover_interrupted():
                continue
            break
        if status == "conflict":
            raise AdapterError("idempotency_conflict", stage="acquire")
        if status == "locked":
            raise AdapterError("concurrent_change", stage="acquire", retry_after_ms=1000)
        if status == "in_progress":
            if op not in ("apply", "rollback"):  # the contract defines the in_progress outcome for apply and rollback only
                raise AdapterError("concurrent_change", stage="acquire", retry_after_ms=1000)
            return "in_progress", copy.deepcopy(info["outcome"])
        return status, (copy.deepcopy(info) if info is not None else None)

    def recover_interrupted(self) -> int:
        """Close operations whose worker died (lease expired): apply and rollback end as recovery_required with the site
        blocked and unlocked for a human (ADR-0028, never a second blind run); other operations are released to retry.
        Safe to call from every worker at any time: each operation is closed once (compare and set)."""
        closed = 0
        for rec in self.store.expired_operations():
            try:
                if rec["operation"] in ("apply", "rollback"):
                    err = AdapterError("recovery_required", stage="execute").to_error()
                    pend = rec["pending"]
                    eid = _new_event_id()
                    final = {
                        **pend,
                        "status": "recovery_required",
                        "stages": [{"stage": "acquire", "status": "done"}, {"stage": "execute", "status": "failed"}],
                        "steps": [{"seq": st["seq"], "status": "failed"} for st in pend.get("steps", [])],
                        "site": {**pend["site"], "state": "recovery_required", "lockedBy": None},
                        "error": err,
                        "eventIds": [eid],
                    }
                    with self.store.transaction():
                        if not self.store.recover_operation(rec, final):
                            continue
                        self.store.append_event(
                            eid,
                            "blueprint.apply_failed",
                            {"change_id": pend["artifactId"], "revision": rec["meta"].get("revision"), "error_code": "recovery_required"},
                            rec["tenant"],
                        )
                else:
                    if not self.store.recover_operation(rec, None):
                        continue
                closed += 1
            except Exception:  # a recovery that cannot run now must not break the caller; it is retried next time
                continue
        return closed

    def _release_on_error(self, tenant: str, op: str, inp: dict[str, Any], op_id: str) -> None:
        self.store.idem_release(tenant, op, inp["idempotencyKey"], op_id)

    def _complete_or_refuse(self, tenant: str, op: str, inp: dict[str, Any], op_id: str, result: dict[str, Any]) -> None:
        """Store the outcome under our reservation, inside the caller's transaction. When the reservation is gone (our
        lease was recovered and the key released), raise so the transaction rolls back: nothing is committed and the
        caller is not told the operation is done. A retry with the same key is a correct first run."""
        if not self.store.idem_complete(tenant, op, inp["idempotencyKey"], op_id, result):
            raise AdapterError("concurrent_change", stage="finalize", retry_after_ms=1000)

    def _lost_lease_outcome(self, tenant: str, operation: str, inp: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """This worker lost its lease: it stops and writes nothing. Close the operation if no one has (recovery is compare
        and set) and return the stored outcome. An apply or rollback ends recovery_required with the site blocked for a
        human; the operation record exists, so this is ok: true (contract 5.6.1)."""
        self.recover_interrupted()
        found = self.store.idem_status(tenant, operation, inp["idempotencyKey"])
        if found is None:
            raise AdapterError("concurrent_change", stage="execute", retry_after_ms=1000)
        return copy.deepcopy(found[1]), True

    # ------------------------------------------------------------------ simple operations
    def _op_capabilities(self, context, inp, site, audit):
        kinds = [{"kind": k, "support": v} for k, v in sorted(STEP_KINDS.items())]
        return (
            {
                "adapterId": ADAPTER_ID,
                "adapterVersion": ADAPTER_VERSION,
                "contractVersions": list(CONTRACT_VERSIONS),
                "artifactSchemaVersions": list(ARTIFACT_SCHEMA_VERSIONS),
                "versionSets": list(VERSION_SETS),
                "stepKinds": kinds,
                "limits": {
                    "maxRequestBytes": MAX_REQUEST_BYTES,
                    "maxStepsPerArtifact": MAX_STEPS,
                    "maxMembersPerSync": MAX_MEMBERS,
                    "planTokenTtlSeconds": PLAN_TOKEN_TTL,
                },
                "exportedProperties": copy.deepcopy(EXPORTED),
                "idempotencyRetentionSeconds": 30 * 86400,
                "features": {"signatureVerification": False, "previewPredictsExport": True},
            },
            False,
        )

    def _op_provision_site(self, context, inp, site, audit):
        tenant = context["tenantId"]
        if tenant == "platform":
            raise AdapterError("invalid_request", {"fields": ["/context/tenantId"]})
        if inp["engineTarget"]["adapter"] != ADAPTER_ID or inp["engineTarget"]["versionSet"] not in VERSION_SETS:
            raise AdapterError("unsupported_engine_target")
        op_id = self._new_id("op")
        status, stored = self._acquire(tenant, "provision_site", inp, op_id)
        if status == "replay":
            return stored, True
        try:
            site = self.store.get_site(tenant)  # re-read now that the key is ours
            if site is not None:
                same = all(
                    getattr(site, attr) == val
                    for attr, val in (
                        ("engine_target", inp["engineTarget"]),
                        ("blueprint_id", inp["blueprintId"]),
                        ("site_class", inp["siteClass"]),
                        ("country_pack", inp["countryPack"]),
                    )
                )
                if not same:
                    raise AdapterError("site_exists_different_target")
                result = site.status()
                self._complete_or_refuse(tenant, "provision_site", inp, op_id, result)
                return result, False

            candidate = SiteRecord(tenant, inp)
            if self.frappe_backend is not None:
                self.frappe_backend.provision_tenant_site(tenant, inp, self._site_snapshot(candidate))
            with self.store.transaction():
                site = self.store.create_site(tenant, inp)
                result = site.status()
                self._complete_or_refuse(tenant, "provision_site", inp, op_id, result)
            return result, False
        except BaseException:
            self._release_on_error(tenant, "provision_site", inp, op_id)
            raise

    def _op_site_status(self, context, inp, site, audit):
        return self._need_site(site, ready=False).status(), False

    def _op_health(self, context, inp, site, audit):
        if context["tenantId"] == "platform":
            if self.frappe_backend is not None:
                checks = self.frappe_backend.check_health("platform")
            else:
                checks = [{"name": "database", "status": "ok"}, {"name": "workers", "status": "ok"}]
        else:
            site = self._need_site(site, ready=False)
            if self.frappe_backend is not None:
                checks = self.frappe_backend.check_health(site.tenant_id, site.state)
            else:
                checks = [
                    {"name": "database", "status": "ok"},
                    {"name": "site_lock", "status": "ok"},
                    {"name": "recovery", "status": "down" if site.state == "recovery_required" else "ok"},
                ]
        order = {"ok": 0, "degraded": 1, "down": 2}
        status = max((c["status"] for c in checks), key=lambda s: order[s])
        return {"status": status, "adapterVersion": ADAPTER_VERSION, "checks": checks}, False

    def _op_export_config(self, context, inp, site, audit):
        site = self._need_site(site)
        doc = self._export(site)
        return {"exportHash": sha(doc), "export": doc, "retained": self._retained(site)}, False

    def _retained(self, site: SiteRecord) -> list[dict[str, Any]]:
        return [{"pointer": p, "state": r["state"]} for p, r in sorted(site.retained.items())]

    def _export(self, site: SiteRecord, config: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = site.config if config is None else config
        sections: dict[str, Any] = {"settings": {}}
        for name in SETTINGS:
            if name in cfg["settings"]:
                key = "settings_intl" if name == "i18n" else "settings_" + name
                sections["settings"][name] = _project(key, cfg["settings"][name])
        for kind, section in SECTION_OF.items():
            sections[section] = sorted((_project(kind, e) for e in cfg[section]), key=lambda e: e["id"])
        rev = site.applied["revision"] if site.applied else None
        return {
            "exportSchema": "0.1.0",
            "engineTarget": copy.deepcopy(site.engine_target),
            "blueprintId": site.blueprint_id,
            "revision": copy.deepcopy(rev),
            "sections": sections,
        }

    # ------------------------------------------------------------------ plan and preview
    def _plan_checks(self, site: SiteRecord, artifact: dict[str, Any]) -> None:
        if artifact["blueprint"]["id"] != site.blueprint_id:
            raise AdapterError("blueprint_mismatch")
        base = artifact["blueprint"]["base"]
        if base != (site.applied["revision"] if site.applied else None):
            raise AdapterError("base_revision_mismatch")

    def _evaluate(self, site: SiteRecord, artifact: dict[str, Any]) -> dict[str, Any]:
        steps, additive, semantic = [], 0, 0
        for step in artifact["steps"]:
            disp, reason, ddl = self._judge(site, step)
            if ddl == "additive":
                additive += 1
            elif ddl == "semantic":
                semantic += 1
            entry: dict[str, Any] = {"seq": step["seq"], "disposition": disp, "ddlImpact": ddl}
            if reason:
                entry["reasonCode"] = reason
            steps.append(entry)
        if site.state == "recovery_required":
            steps = [
                {
                    "seq": s["seq"],
                    "disposition": "blocked",
                    "ddlImpact": s["ddlImpact"],
                    "reasonCode": "recovery_required",
                }
                for s in steps
            ]
        kinds = {s["disposition"] for s in steps}
        verdict = (
            "rejected"
            if kinds & {"blocked", "unsupported"}
            else "needs_gate_approval"
            if "gated" in kinds
            else "auto_approved"
        )
        return {
            "steps": steps,
            "verdict": verdict,
            "storage": {"additive": additive, "semantic": semantic, "statementCount": additive + semantic},
        }

    def _judge(self, site: SiteRecord, step: dict[str, Any]) -> tuple[str, str | None, str]:
        kind, pointer, params = step["kind"], step["pointer"], step["params"]
        ddl = step["ddlImpact"]
        support = STEP_KINDS.get(kind, "unsupported")
        if support == "unsupported":
            return "unsupported", "unsupported_step_kind", ddl
        if kind in ("field.add", "relation.add", "entity.add") and ddl == "none":
            ddl = "additive"
        if kind.endswith("set_property") and params.get("property") in SEMANTIC_PROPS:
            ddl = "semantic"
        if has_prohibited_expression(params):
            return "blocked", "prohibited_expression", ddl
        segs = _segs(pointer)
        if segs[:1] == ["entities"] and len(segs) > 1 and is_protected_entity(segs[1]):
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

            reason = (
                self._storage_reason(segs, defn)
                if ddl != "none" or kind in ("field.add", "entity.add")
                else None
            )
            if reason is None and self.frappe_backend is not None and kind == "field.add":
                reason = self.frappe_backend.inspect_step_plan(site.tenant_id, step, held is not None)
            if reason and reason[0] == "blocked":
                return "blocked", reason[1], ddl
            if reason:
                return "gated", reason[1], ddl
        elif kind.endswith((".quarantine", ".disable")):
            if elem is _MISSING:
                return "blocked", "subject_missing", ddl
            if kind == "role.disable":
                members = self.store.get_members(site.tenant_id)
                if any(segs[1] in m["roleIds"] and m["status"] == "active" for m in members.values()):
                    return "blocked", "subject_in_use", ddl
        elif kind != "settings.set" and elem is _MISSING:
            return "blocked", "subject_missing", ddl

        if ddl == "semantic":
            return "gated", "storage_not_additive", ddl
        if support == "gated":
            return "gated", "protected_subject", ddl
        return "ok", None, ddl

    @staticmethod
    def _storage_reason(segs: list[str], defn: Any) -> tuple[str, str] | None:
        if not isinstance(defn, dict):
            return None
        entity_id = segs[1] if segs[:1] == ["entities"] and len(segs) > 1 else "entity"
        fields = defn.get("fields", [defn])
        for f in fields:
            if not isinstance(f, dict):
                continue
            if "type" in f and f["type"] not in SUPPORTED_BLUEPRINT_TYPES:
                return "blocked", "unsupported_value_type"
            if f.get("unique") or f.get("indexed"):
                return "gated", "unique_or_index"
            if "type" in f:
                ok, _, reason = inspect_field_ddl(entity_id, f)
                if not ok and reason:
                    if reason == "unsupported_value_type":
                        return "blocked", reason
                    return "gated", reason
        return None

    def _collection(self, site: SiteRecord, segs: list[str]):
        if segs[0] in SETTINGS:
            return site.config["settings"]
        parent = _walk(site.config, segs[:-1])
        return None if parent is _MISSING else parent

    def _token(self, tenant: str, content_hash: str, config_hash: str) -> str:
        raw = f"{tenant}|{content_hash}|{config_hash}|{ADAPTER_VERSION}".encode("utf-8")
        return "pln_" + hashlib.sha256(raw).hexdigest()[:40]

    def _op_plan(self, context, inp, site, audit):
        site = self._need_site(site)
        artifact = inp["artifact"]
        self._plan_checks(site, artifact)
        result = self._evaluate(site, artifact)
        config_hash = sha(self._export(site))
        token = self._token(context["tenantId"], artifact["integrity"]["contentHash"], config_hash)
        self.store.save_token(site.tenant_id, token, self.now)
        evidence = "evd_" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]
        statements = [stmt for step in artifact["steps"] for stmt in plan_statements_for_step(step)]
        self.store.save_evidence(site.tenant_id, evidence, statements)
        return (
            {
                "planToken": token,
                "artifactId": artifact["artifactId"],
                "siteConfigHash": config_hash,
                "verdict": result["verdict"],
                "steps": result["steps"],
                "storage": result["storage"],
                "evidenceRef": evidence,
                "expiresInSeconds": PLAN_TOKEN_TTL,
            },
            False,
        )

    def _op_preview(self, context, inp, site, audit):
        site = self._need_site(site)
        artifact = inp["artifact"]
        self._plan_checks(site, artifact)
        result = self._evaluate(site, artifact)
        out: dict[str, Any] = {
            "artifactId": artifact["artifactId"],
            "siteConfigHash": sha(self._export(site)),
            "verdict": result["verdict"],
            "predictedExportHash": None,
            "delta": [],
        }
        if result["verdict"] != "rejected":
            trial = copy.deepcopy(site)
            for step in artifact["steps"]:
                self._exec(trial, step, persist_storage=False)
            trial.applied = {
                "artifactId": artifact["artifactId"],
                "revision": copy.deepcopy(artifact["blueprint"]["target"]),
            }
            doc = self._export(trial)
            out["predictedExportHash"] = sha(doc)
            if inp.get("includeExport"):
                out["predictedExport"] = doc
            out["delta"] = self._delta(site, artifact)
        return out, False

    def _delta(self, site: SiteRecord, artifact: dict[str, Any]) -> list[dict[str, Any]]:
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
            row: dict[str, Any] = {"change": change, "pointer": pointer}
            if kind.endswith(("set_property", "settings.set", ".configure")):
                row["property"] = step["params"]["property"]
            rows.append(row)
        return sorted(rows, key=lambda r: (r["pointer"], r.get("property", "")))

    # ------------------------------------------------------------------ step execution
    def _exec(
        self, site: SiteRecord, step: dict[str, Any], persist_storage: bool = True, guard: Callable[[], None] | None = None
    ) -> None:
        kind, pointer, params = step["kind"], step["pointer"], step["params"]
        segs = _segs(pointer)
        if persist_storage and self.frappe_backend is not None:
            # Execute the engine backend BEFORE mutating site.config/site.retained so a failed
            # step never mutates or aliases in-memory state. Partial engine effects are handled
            # fail-closed in _execute_all (any exception not proven side_effect_free transitions
            # the site to recovery_required rather than hiding engine-side writes).
            if guard is not None:
                guard()
            self.frappe_backend.execute_step(site.tenant_id, step)
        cfg = site.config
        if kind == "settings.set":
            doc = cfg["settings"].setdefault(segs[0], {})
            _set_path(doc, params["property"], params)
            if "after" not in params:
                _prune_empty(doc)
                if not doc:
                    del cfg["settings"][segs[0]]
        elif kind.endswith((".set_property", ".configure")):
            elem = _walk(cfg, segs)
            _set_path(elem, params["property"], params)
            if "after" not in params:
                prop_segs = _segs(params["property"])
                if prop_segs and isinstance(elem, dict) and isinstance(elem.get(prop_segs[0]), dict):
                    _prune_empty(elem[prop_segs[0]])
                    if not elem[prop_segs[0]]:
                        del elem[prop_segs[0]]
        elif kind.endswith(".reorder"):
            node = _walk(cfg, segs)
            node = node if isinstance(node, list) else node.get("fields", node.get("options"))
            node.sort(key=lambda e: params["order"].index(str(e["id"])))
        elif kind.endswith((".quarantine", ".disable")):
            coll = _walk(cfg, segs[:-1])
            idx = next(i for i, e in enumerate(coll) if str(e["id"]) == segs[-1])
            site.retained[pointer] = {
                "state": "quarantined" if kind.endswith(".quarantine") else "disabled",
                "definition": coll.pop(idx),
                "index": idx,
            }
        else:
            coll = _walk(cfg, segs[:-1])
            held = site.retained.pop(pointer, None)
            defn = copy.deepcopy(params["definition"])
            idx = next((i for i, e in enumerate(coll) if str(e["id"]) == segs[-1]), None)
            if held is not None:
                coll.insert(min(held["index"], len(coll)), held["definition"])
            elif idx is not None:
                coll[idx] = defn
            else:
                coll.append(defn)

        if persist_storage:
            if guard is not None and kind in ("entity.add", "field.add"):
                guard()  # the engine step above may have run long: re-check ownership before the DDL
            if kind == "entity.add":
                self.store.ensure_entity_table(site.tenant_id, str(segs[1] if len(segs) > 1 else "entity"))
            elif kind == "field.add" and len(segs) >= 4 and segs[0] == "entities":
                self.store.ensure_field_column(site.tenant_id, segs[1], pointer)

    def _evaluate_pc(self, doc: dict[str, Any], retained: dict[str, Any], pc: dict[str, Any]) -> bool:
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
            return isinstance(node, list) and [str(e.get("id", e.get("order"))) for e in node] == pc["expected"]
        return False

    # ------------------------------------------------------------------ apply and rollback
    def _op_apply(self, context, inp, site, audit):
        return self._run(context, inp, self._need_site(site), "apply", audit)

    def _op_rollback(self, context, inp, site, audit):
        return self._run(context, inp, self._need_site(site), "rollback", audit)

    def _event_data(self, operation: str, status: str, artifact: dict[str, Any], target_rev: Any, error: dict[str, Any] | None):
        if status == "applied":
            if operation == "apply":
                return "blueprint.applied", {"change_id": artifact["artifactId"], "revision": target_rev}
            return "blueprint.rolled_back", {"change_id": artifact["artifactId"], "revision": target_rev}
        return (
            "blueprint.apply_failed",
            {"change_id": artifact["artifactId"], "revision": target_rev, "error_code": error["code"]},
        )

    def _run(self, context, inp, site: SiteRecord, operation: str, audit: dict[str, Any]):
        forward = inp["artifact"] if operation == "apply" else inp["forwardArtifact"]
        artifact = forward if operation == "apply" else forward.get("inverse") or forward
        op_id = self._new_id("op")
        _lock_key = bounded_site_lock_key(site.tenant_id, site.blueprint_id)
        stages: list[dict[str, str]] = []
        steps = [{"seq": s["seq"], "status": "not_run"} for s in artifact["steps"]]
        pcs: list[dict[str, Any]] = []
        state: dict[str, Any] = {"status": None, "error": None, "export_hash": None}
        timed_out = {"v": False}
        target_rev = artifact["blueprint"]["target"]["revision"]

        # acquire (5.6): the key is bound to its input and the site lock taken in the database, in one committed
        # transaction, before any effect. A second worker gets in_progress or the stored outcome, never a second run.
        running = {
            "operationId": op_id,
            "operation": operation,
            "artifactId": artifact["artifactId"],
            "status": "in_progress",
            "stages": [{"stage": "acquire", "status": "done"}, {"stage": "inspect", "status": "running"}],
            "steps": [dict(st) for st in steps],
            "postConditions": [],
            "site": {**site.status(), "state": "applying" if site.state == "ready" else site.state, "lockedBy": op_id},
        }
        verdict, stored = self._acquire(
            site.tenant_id, operation, inp, op_id, lock=True, pending=running, meta={"revision": target_rev}
        )
        if verdict in ("replay", "in_progress"):
            return stored, True
        # whether to put the site back to ready is decided by the acquire itself, in the transaction that took the lock;
        # reading the state earlier races with a worker that finishes in between and leaves the site stuck in applying
        ready_before = bool(stored and stored.get("ready_before"))
        tenant = site.tenant_id
        # the row may have changed under us (another worker, or a recovery just run): continue from what the database holds
        site = self._need_site(self.store.get_site(tenant), ready=False)
        stages.append({"stage": "acquire", "status": "done"})

        def owned() -> None:
            """Called before every engine or DDL step: a worker whose lease expired or was recovered stops at once."""
            if not self.store.operation_owned(tenant, operation, inp["idempotencyKey"], op_id):
                raise _LeaseLost()

        def finish(status: str, error: dict[str, Any] | None = None, hash_after: str | None = None) -> None:
            state.update(status=status, error=error, export_hash=hash_after)

        try:
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
                self._execute_all(
                    site,
                    artifact,
                    steps,
                    pcs,
                    stages,
                    finish,
                    pre_hash,
                    timed_out,
                    op_id,
                    _lock_key,
                    operation,
                    forward if operation == "rollback" else artifact.get("inverse"),
                    guard=owned,
                )
        except _LeaseLost:
            return self._lost_lease_outcome(tenant, operation, inp)
        except Exception as exc:
            # An unexpected error must not strand the lock until the lease ends: close the operation here. With no step
            # run yet nothing changed (failed_clean, contract 5.6); otherwise the partial state needs a human.
            err = exc if isinstance(exc, AdapterError) else AdapterError("engine_unavailable", stage="prepare")
            if any(st["status"] != "not_run" for st in steps):
                site.state = "recovery_required"
                stages.append({"stage": "execute", "status": "failed"})
                finish("recovery_required", AdapterError("recovery_required", stage="execute").to_error())
            else:
                stages.append({"stage": "prepare", "status": "failed"})
                finish("failed_clean", err.to_error())

        if site.lock == op_id:
            site.lock = None
            if ready_before and site.state == "applying":
                site.state = "ready"

        status, error = state["status"], state["error"]
        outcome: dict[str, Any] = {
            "operationId": op_id,
            "operation": operation,
            "artifactId": artifact["artifactId"],
            "status": status,
            "stages": stages,
            "steps": steps,
            "postConditions": pcs,
            "site": site.status(),
        }
        if state["export_hash"]:
            outcome["exportHash"] = state["export_hash"]
        if error:
            outcome["error"] = error
        event: tuple[str, str, dict[str, Any]] | None = None
        if status != "already_applied":
            event_art = forward if operation == "rollback" and status == "applied" else artifact
            etype, data = self._event_data(operation, status, event_art, target_rev, error)
            if operation == "rollback" and status == "applied":
                data["revision"] = forward["blueprint"]["base"]["revision"] if forward["blueprint"]["base"] else target_rev
            event = (_new_event_id(), etype, data)
            outcome["eventIds"] = [event[0]]

        # finalize (5.6): the stored outcome, the site state and the event commit together or not at all. The outcome
        # write goes first and is compare-and-set on our reservation: a worker whose lease was recovered by another
        # one writes nothing (its site and event writes roll back with the transaction).
        try:
            with self.store.transaction():
                if not self.store.idem_complete(site.tenant_id, operation, inp["idempotencyKey"], op_id, outcome):
                    raise _LeaseLost()  # rolls the site and event writes back with the transaction
                self.store.save_site(site)
                if event is not None:
                    self.store.append_event(*event, tenant_id=site.tenant_id)
        except _LeaseLost:
            return self._lost_lease_outcome(site.tenant_id, operation, inp)
        if self.frappe_backend is not None:
            try:
                self.frappe_backend.persist_site_state(site.tenant_id, self._site_snapshot(site))
            except Exception:
                pass
        if timed_out["v"]:
            raise AdapterError("timeout", stage="execute")
        return outcome, False

    def _inspect(self, context, inp, site: SiteRecord, operation: str, forward: dict[str, Any], artifact: dict[str, Any]) -> None:
        def reject(code: str, details: dict[str, Any] | None = None) -> None:
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

    def _verify_token(self, context, inp, site: SiteRecord, artifact: dict[str, Any], reject: Callable[..., None]) -> None:
        token = inp["planToken"]
        issued = self.store.get_token_issued_at(site.tenant_id, token)
        expected = self._token(context["tenantId"], artifact["integrity"]["contentHash"], sha(self._export(site)))
        if issued is None or token != expected or self.now - issued > PLAN_TOKEN_TTL:
            reject("plan_token_invalid")

    def _execute_all(
        self,
        site: SiteRecord,
        artifact: dict[str, Any],
        steps: list[dict[str, Any]],
        pcs: list[dict[str, Any]],
        stages: list[dict[str, str]],
        finish: Callable[..., None],
        pre_hash: str,
        timed_out: dict[str, bool],
        op_id: str,
        lock_key: str,
        operation: str = "apply",
        counterpart: dict[str, Any] | None = None,
        guard: Callable[[], None] | None = None,
    ) -> None:
        if self._take_fault("prepare"):
            stages.append({"stage": "prepare", "status": "failed"})
            finish("failed_clean", AdapterError("engine_unavailable", stage="prepare").to_error())
            return

        self.store.save_prepare_intent(
            op_id,
            site.tenant_id,
            artifact["artifactId"],
            {"lockKey": lock_key, "operation": operation, "stepCount": len(artifact["steps"])},
        )
        journal: list[dict[str, Any]] = []
        stages.append({"stage": "prepare", "status": "done"})
        failure: AdapterError | None = None
        comp_fault = False

        if self._lock_hook:
            hook, self._lock_hook = self._lock_hook, None
            hook()

        for step, entry in zip(artifact["steps"], steps):
            seq = step["seq"]
            entry_j = {
                "artifactId": artifact["artifactId"],
                "seq": seq,
                "step": step,
                "executed": False,
                "before": self._read_prop(site, step),
            }
            journal.append(entry_j)
            if self._take_fault("deadline", seq):
                timed_out["v"] = True
            fault = self._take_fault("execute", seq)
            if fault:
                entry["status"] = "failed"
                failure = AdapterError("engine_unavailable", {"stepSeq": seq}, stage="execute")
                comp_fault = bool(fault["comp"])
                break
            if guard is not None:
                guard()  # before the journal entry: a step that never ran must not appear as run
            self.store.append_journal(site.tenant_id, artifact["artifactId"], seq, "execute")
            try:
                self._exec(site, step, persist_storage=True, guard=guard)
            except _LeaseLost:
                raise
            except Exception as exc:
                entry["status"] = "failed"
                err_code = getattr(exc, "code", None)
                err_details = getattr(exc, "details", None)
                if not isinstance(err_code, str):
                    err_code = "engine_unavailable"
                    err_details = {}
                failure = AdapterError(err_code, {"stepSeq": seq, **(err_details or {})}, stage="execute")
                if self.frappe_backend is not None:
                    comp_fault = err_code == "recovery_required" or not bool(getattr(exc, "side_effect_free", False))
                else:
                    comp_fault = err_code == "recovery_required"
                break
            entry_j["executed"] = True
            entry["status"] = "applied"

        stages.append({"stage": "execute", "status": "failed" if failure else "done"})
        doc = self._export(site)

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
            self._compensate(site, steps, stages, finish, journal, pre_hash, failure, comp_fault, counterpart, guard)
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
            site.applied = {
                "artifactId": artifact["artifactId"],
                "revision": copy.deepcopy(artifact["blueprint"]["target"]),
            }
            site.history.append(copy.deepcopy(site.applied))
        site.applied_ids.add(artifact["artifactId"])
        stages.append({"stage": "finalize", "status": "done"})
        finish("applied", None, sha(self._export(site)))

    @staticmethod
    def _read_prop(site: SiteRecord, step: dict[str, Any]) -> Any:
        if step["kind"] != "settings.set":
            return None
        cur: Any = site.config["settings"].get(_segs(step["pointer"])[0], {})
        for seg in _segs(step["params"]["property"]):
            cur = cur.get(seg, _MISSING) if isinstance(cur, dict) else _MISSING
        return _MISSING if cur is _MISSING else copy.deepcopy(cur)

    @staticmethod
    def _undo_for(entry: dict[str, Any], counterpart: dict[str, Any] | None, used: set[int]) -> dict[str, Any]:
        step = entry["step"]
        if counterpart is not None:
            key = (step["pointer"], step["params"].get("property"))
            for cand in counterpart["steps"]:
                if id(cand) not in used and (cand["pointer"], cand["params"].get("property")) == key:
                    used.add(id(cand))
                    return cand
            raise RuntimeError("missing stored inverse step for " + step["pointer"])
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

    def _compensate(
        self,
        site: SiteRecord,
        steps: list[dict[str, Any]],
        stages: list[dict[str, str]],
        finish: Callable[..., None],
        journal: list[dict[str, Any]],
        pre_hash: str,
        failure: AdapterError,
        comp_fault: bool,
        counterpart: dict[str, Any] | None,
        guard: Callable[[], None] | None = None,
    ) -> None:
        used: set[int] = set()
        try:
            for entry in reversed(journal):
                if comp_fault:
                    raise RuntimeError("compensation fault")
                status = next(s for s in steps if s["seq"] == entry["seq"])
                if entry["executed"]:
                    if guard is not None:
                        guard()
                    self.store.append_journal(site.tenant_id, entry["artifactId"], entry["seq"], "compensate")
                    self._exec(site, self._undo_for(entry, counterpart, used), persist_storage=True, guard=guard)
                    status["status"] = "compensated"
                else:
                    status["status"] = "failed"
            if sha(self._export(site)) != pre_hash:
                raise RuntimeError("compensated state differs from pre-apply export")
        except _LeaseLost:
            raise
        except Exception:
            site.state = "recovery_required"
            stages.append({"stage": "compensate", "status": "failed"})
            finish("recovery_required", AdapterError("recovery_required", stage="compensate").to_error())
            return

        stages.append({"stage": "compensate", "status": "done"})
        finish("compensated", failure.to_error(), pre_hash)

    # ------------------------------------------------------------------ members
    def _op_sync_members(self, context, inp, site, audit):
        site = self._need_site(site)
        tenant = site.tenant_id
        op_id = self._new_id("op")
        status, stored = self._acquire(tenant, "sync_members", inp, op_id)
        if status == "replay":
            return stored, True
        try:
            # One sync per tenant at a time: the row lock on the site is held until the commit, and the members are read
            # after it. Two calls with different keys therefore cannot both start from the same snapshot, and a later
            # one cannot overwrite (for example re-enable) what an earlier one committed.
            with self.store.transaction():
                self.store.lock_site_row(tenant)
                site = self._need_site(self.store.get_site(tenant))  # re-read now that the key and the row lock are ours
                if inp["syncVersion"] <= site.sync_version:
                    raise AdapterError("stale_sync_version")

                active_roles = {e["id"] for e in site.config["roles"]}
                unknown = sorted({r for m in inp["members"] for r in m["roleIds"] if r not in active_roles})
                if unknown:
                    raise AdapterError("unknown_role", {"fields": ["/members/roleIds"]})

                members = self.store.get_members(tenant)
                created = updated = disabled = unchanged = 0
                listed: set[str] = set()
                for m in inp["members"]:
                    listed.add(m["memberRef"])
                    new = {
                        "status": m["status"],
                        "roleIds": sorted(m["roleIds"]),
                        "displayName": m.get("displayName"),
                        "canAuthenticate": False,
                        "emailSent": False,
                    }
                    old = members.get(m["memberRef"])
                    if old is None:
                        created += 1
                    elif (
                        old["status"] == new["status"]
                        and old["roleIds"] == new["roleIds"]
                        and old["displayName"] == new["displayName"]
                    ):
                        unchanged += 1
                    else:
                        updated += 1
                        disabled += int(old["status"] == "active" and new["status"] == "disabled")
                    members[m["memberRef"]] = new

                if inp["mode"] == "full":
                    for ref, member in members.items():
                        if ref not in listed and member["status"] == "active":
                            member["status"] = "disabled"
                            disabled += 1

                if self.frappe_backend is not None:
                    self.frappe_backend.sync_members(tenant, inp["members"], inp["mode"], members)

                result = {
                    "syncVersion": inp["syncVersion"],
                    "created": created,
                    "updated": updated,
                    "disabled": disabled,
                    "unchanged": unchanged,
                }
                # version (compare and set), members and key commit together; a lost key rolls all three back
                self._complete_or_refuse(tenant, "sync_members", inp, op_id, result)
                if not self.store.set_sync_version(tenant, inp["syncVersion"]):
                    raise AdapterError("stale_sync_version")
                self.store.replace_members(tenant, members)
            site.sync_version = inp["syncVersion"]
            if self.frappe_backend is not None:
                self.frappe_backend.persist_site_state(tenant, self._site_snapshot(site))
            return result, False
        except BaseException:
            self._release_on_error(tenant, "sync_members", inp, op_id)
            raise


__all__ = [
    "ADAPTER_ID",
    "ADAPTER_VERSION",
    "AdapterError",
    "ChangeEngineAdapter",
    "HooksDisabled",
]
