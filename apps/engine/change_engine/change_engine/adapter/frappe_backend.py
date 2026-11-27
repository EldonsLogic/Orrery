"""Frappe Framework & MariaDB runtime backend for ChangeEngineAdapter (ERP-012).

Translates validated Blueprint operations, DDL plan inspections, guarded field/property/workflow/report
deployments, shadow user sync, T36 caller impersonation, and tenant data probes into real Frappe
site operations via change_engine.guarded_apply and FrappeDeploymentAdapter.

Fails closed when a real Frappe runtime is not available unless an explicit simulated runtime is
injected (for unit tests and CI conformance). Never leaks engine identifiers, stack traces, SQL, or
filesystem paths into adapter responses or error payloads (ADP-C-006).
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import uuid
from types import SimpleNamespace
from typing import Any, Callable, Iterator

from change_engine.adapter.mapping import (
    ADAPTER_DOCTYPE_MODULE,
    BLUEPRINT_TO_FRAPPE_FIELDTYPE,
    CONTRACT_NATIVE_FIELDS,
    ENGINE_NAME_PREFIX,
    ENTITY_TO_DOCTYPE,
    RULE_FLAGS,
    _DECIMAL_ADD_RE,
    EngineNameError,
    _sanitize_custom_fieldname,
    engine_role_name,
    engine_state_name,
    entity_to_doctype,
    is_contract_mapped_entity,
    is_protected_entity,
    reviewed_grant_doctype,
    rule_flags,
)
from change_engine.api.endpoints import FrappeDeploymentAdapter
from change_engine.guarded_apply.property_setter_engine import (
    PROPERTY_TYPE_MAP,
    execute_property_setter_deployment,
)
from change_engine.guarded_apply.report_engine import execute_report_deployment
from change_engine.guarded_apply.ddl_plan_gate import DDLPlanInspection
from change_engine.guarded_apply.schema_reconciler import (
    DeploymentIntentConflictError,
    DurableEvidenceError,
    IdempotencyConflictError,
    LockTimeoutError,
    SessionDiscardedError,
    execute_single_field_deployment,
)
from change_engine.guarded_apply.workflow_engine import (
    TERMINAL_REJECT_STATE_NAMES,
    execute_workflow_deployment,
)


COUNTRY_DEFAULTS: dict[str, dict[str, str]] = {
    "sa": {"country": "Saudi Arabia", "currency": "SAR", "language": "ar", "timezone": "Asia/Riyadh"},
    "ae": {"country": "United Arab Emirates", "currency": "AED", "language": "ar", "timezone": "Asia/Dubai"},
    "eg": {"country": "Egypt", "currency": "EGP", "language": "ar", "timezone": "Africa/Cairo"},
    "qa": {"country": "Qatar", "currency": "QAR", "language": "ar", "timezone": "Asia/Qatar"},
}

GOVERNANCE_ACTOR_ROLES = ["System Manager"]

# Canonical tenantId grammar (contracts/engine-adapter/common.schema.json):
# lowercase t_<alnum_underscore>, 5..63 chars (valid RFC 1123 label when '_' -> '-').
# Forbidding '.', '-', uppercase, and trailing '_' makes tenant -> site resolution strictly 1-to-1.
_SAFE_TENANT_RE = re.compile(r"^t_[a-z0-9][a-z0-9_]{1,59}[a-z0-9]$")
_SAFE_SQL_IDENT_RE = re.compile(r"^[A-Za-z0-9_ ]+$")

_BP_PROP_TO_FRAPPE = {
    "/label": ("label", "Data"),
    "/labels/en": ("label", "Data"),
    "/labels/ar": ("label", "Data"),
    "/required": ("reqd", "Check"),
    "/readOnly": ("read_only", "Check"),
    "/hidden": ("hidden", "Check"),
    "/default": ("default", "Data"),
    "/description": ("description", "Text"),
    "/options": ("options", "Text"),
}


# BPL-032: highest engine permission level (levels 1..9 carry field masks, ADR-0039 item 3).
MAX_PERMLEVEL = 9
_ZERO_RULE = {**dict.fromkeys(RULE_FLAGS, 0), "if_owner": 0}

ENGINE_ENV_VAR = "CHANGE_ENGINE_ENV"
OFFLINE_SIMULATOR_ENVS = frozenset({"dev", "test"})
LOCATION_KINDS = frozenset({"branch", "warehouse", "department"})  # contracts/blueprint.schema.json location.kind
_STATE_TABLE = "tabChange Engine Blueprint State"  # the tenant-database copy of the site state


# A field the guarded path adds never carries unique or an index (Q-603); BPL-041's readiness projection uses this.
_NO_CONSTRAINT = SimpleNamespace(unique=0, search_index=0)


class FrappeBackendError(Exception):
    """Sanitized adapter-facing error raised by FrappeRuntimeBackend (never leaks engine details)."""

    def __init__(
        self,
        code: str,
        details: dict[str, Any] | None = None,
        stage: str = "execute",
        *,
        side_effect_free: bool = False,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.details = details or {}
        self.stage = stage
        self.side_effect_free = bool(side_effect_free)


class FrappeSiteResolver:
    """Maps opaque Blueprint tenant IDs to isolated Frappe site names injectively."""

    def __init__(
        self,
        site_map: dict[str, str] | None = None,
        default_domain: str = "localhost",
    ) -> None:
        self.site_map = dict(site_map or {})
        self.default_domain = default_domain
        seen_sites: dict[str, str] = {}
        default = str(default_domain).strip().rstrip(".").lower()
        for tid, site in self.site_map.items():
            # Every key is a tenant id and every value a site name no other tenant resolves to (CE-SEC-011): one
            # that equals another, unmapped tenant's default ``<slug>.<default_domain>`` would put two tenants on
            # one site.
            if not isinstance(tid, str) or not _SAFE_TENANT_RE.fullmatch(tid) or not isinstance(site, str):
                raise FrappeBackendError("invalid_request", {"fields": ["/site_map"]}, stage="validate")
            norm_site = site.strip().rstrip(".").lower()
            if not norm_site or norm_site in seen_sites and seen_sites[norm_site] != tid:
                raise FrappeBackendError("invalid_request", {"fields": ["/site_map"]}, stage="validate")
            label, _dot, domain = norm_site.partition(".")
            other = label.replace("-", "_")
            if domain == default and other != tid and other not in self.site_map and _SAFE_TENANT_RE.fullmatch(other):
                raise FrappeBackendError("invalid_request", {"fields": ["/site_map"]}, stage="validate")
            seen_sites[norm_site] = tid

    def resolve(self, tenant_id: str) -> str:
        if not isinstance(tenant_id, str) or not _SAFE_TENANT_RE.fullmatch(tenant_id):
            raise FrappeBackendError(
                "invalid_request",
                {"fields": ["/context/tenantId"]},
                stage="validate",
                side_effect_free=True,
            )
        if tenant_id in self.site_map:
            return self.site_map[tenant_id]
        # Strictly injective: _SAFE_TENANT_RE forbids '-', '.', uppercase, and trailing '_',
        # so '_' -> '-' cannot collapse distinct tenant IDs onto the same site name.
        slug = tenant_id.replace("_", "-")
        return f"{slug}.{self.default_domain}"

    def tenant_of(self, site: Any) -> str | None:
        """The one tenant id whose site is exactly ``site`` (the inverse of ``resolve``), or ``None``.

        A ``site_map`` entry is matched on the exact site name the backend binds; any other site must be the
        default-domain name of a tenant that is NOT mapped elsewhere (``resolve`` of the candidate returns it back).
        No other spelling of a site (case, trailing dot, another domain) maps to a tenant."""
        if not isinstance(site, str) or not site:
            return None
        for tenant_id, mapped in self.site_map.items():
            if mapped == site:
                return tenant_id
        candidate = site.partition(".")[0].replace("-", "_")
        if not _SAFE_TENANT_RE.fullmatch(candidate) or candidate in self.site_map:
            return None
        return candidate if self.resolve(candidate) == site else None


def shadow_user_email(member_ref: str) -> str:
    """Derive deterministic non-PII internal shadow user identifier from memberRef (ADP-C-065)."""
    digest = hashlib.sha256(member_ref.encode("utf-8")).hexdigest()[:16]
    return f"mem_{digest}@shadow.internal.invalid"


def shadow_user_label(member_ref: str) -> str:
    """Derive deterministic non-PII display label for Frappe User.first_name."""
    digest = hashlib.sha256(member_ref.encode("utf-8")).hexdigest()[:8]
    return f"Member {digest}"


class FrappeRuntimeBackend:
    """Real Frappe backend executing adapter operations against per-tenant Frappe sites."""

    def __init__(
        self,
        site_resolver: FrappeSiteResolver | None = None,
        frappe_factory: Callable[[], Any] | None = None,
        actor_roles: list[str] | None = None,
        auto_create_sites: bool = False,
        sites_path: str | None = None,
        offline_ddl_simulator: bool = False,
    ) -> None:
        # The offline DDL simulator is column-blind (it skips every drift comparison), so it is an
        # explicit opt-in, never inferred from a factory, and refused outside dev/test. An unset
        # CHANGE_ENGINE_ENV counts as production (ERP-027, fail closed).
        if offline_ddl_simulator and os.environ.get(ENGINE_ENV_VAR, "").strip().lower() not in OFFLINE_SIMULATOR_ENVS:
            raise FrappeBackendError("offline_ddl_simulator_forbidden", stage="validate")
        self._offline_ddl_simulator = offline_ddl_simulator
        self.site_resolver = site_resolver or FrappeSiteResolver()
        self._frappe_factory = frappe_factory
        self._actor_roles = list(actor_roles) if actor_roles is not None else list(GOVERNANCE_ACTOR_ROLES)
        self._auto_create_sites = auto_create_sites
        self._sites_path = sites_path

    def _next_id(self, prefix: str) -> str:
        """A deployment id that never repeats, across objects and restarts: the audit table's primary key is the id
        and its intent insert is strict, so a per-object counter that restarted at 1 would collide with older rows.
        ``prefix_<32 hex>`` is inside the canonical id grammar (at most 100 characters)."""
        return f"{prefix}_{uuid.uuid4().hex}"

    @staticmethod
    def _safe_attr(obj: Any, *names: str) -> Any:
        cur = obj
        for name in names:
            try:
                cur = getattr(cur, name)
            except (AttributeError, RuntimeError):
                return None
        return cur

    def _acquire_frappe(self) -> Any:
        if self._frappe_factory is not None:
            return self._frappe_factory()
        try:
            import frappe  # type: ignore[import-not-found]
        except ImportError as exc:
            raise FrappeBackendError("engine_unavailable", stage="acquire", side_effect_free=True) from exc
        if not hasattr(frappe, "connect") and self._safe_attr(frappe, "db") is None:
            raise FrappeBackendError("engine_unavailable", stage="acquire", side_effect_free=True)
        return frappe

    @contextlib.contextmanager
    def _site_session(self, tenant_id: str, create_if_missing: bool = False) -> Iterator[tuple[Any, str]]:
        import os

        site_name = self.site_resolver.resolve(tenant_id)
        f = self._acquire_frappe()

        prev_site = self._safe_attr(f, "local", "site")
        prev_user = self._safe_attr(f, "session", "user")
        prev_cwd = os.getcwd()
        changed_cwd = False
        switched = False
        yielded = False

        try:
            if self._sites_path and os.path.isdir(self._sites_path) and os.path.abspath(prev_cwd) != os.path.abspath(self._sites_path):
                os.chdir(self._sites_path)
                changed_cwd = True

            if create_if_missing and self._auto_create_sites and hasattr(f, "ensure_site"):
                f.ensure_site(site_name)

            if prev_site != site_name:
                if hasattr(f, "init"):
                    if self._sites_path:
                        try:
                            f.init(site=site_name, sites_path=".")
                        except TypeError:
                            f.init(site=site_name)
                    else:
                        f.init(site=site_name)
                if hasattr(f, "connect"):
                    try:
                        f.connect(site=site_name)
                    except TypeError:
                        f.connect()
                switched = True

            if self._safe_attr(f, "db", "sql") is None:
                raise FrappeBackendError("engine_unavailable", stage="acquire", side_effect_free=True)

            yielded = True
            yield f, site_name
        except FrappeBackendError:
            raise
        except Exception as exc:
            raise FrappeBackendError(
                "engine_unavailable",
                stage="execute" if yielded else "acquire",
                side_effect_free=not yielded,
            ) from exc
        finally:
            if switched:
                try:
                    if prev_site:
                        if hasattr(f, "init"):
                            f.init(site=prev_site)
                        if hasattr(f, "connect"):
                            f.connect()
                    elif hasattr(f, "destroy") and not hasattr(f, "ensure_site"):
                        f.destroy()
                    elif hasattr(f, "local"):
                        f.local.site = prev_site
                    if prev_user and hasattr(f, "set_user"):
                        f.set_user(prev_user)
                except Exception:
                    pass
            if changed_cwd:
                try:
                    os.chdir(prev_cwd)
                except Exception:
                    pass

    def _deployment_adapter(self, f: Any) -> FrappeDeploymentAdapter:
        # Offline mode is the explicit constructor flag only (simulated runtime, no real DDL);
        # an injected factory alone still gets Frappe's own inspection and fails closed.
        return FrappeDeploymentAdapter(
            frappe_module=f, in_memory=False, offline_ddl_simulator=self._offline_ddl_simulator,
            site_resolver=self.site_resolver,
        )

    def _ensure_state_table(self, f: Any) -> None:
        f.db.sql(
            """
            CREATE TABLE IF NOT EXISTS `tabChange Engine Blueprint State` (
                tenant_id VARCHAR(140) PRIMARY KEY,
                state VARCHAR(64) NOT NULL,
                site_class VARCHAR(32) NOT NULL,
                engine_target_json LONGTEXT NOT NULL,
                blueprint_id VARCHAR(140) NOT NULL,
                country_pack VARCHAR(16) NOT NULL,
                applied_json LONGTEXT,
                applied_ids_json LONGTEXT NOT NULL,
                history_json LONGTEXT NOT NULL,
                sync_version INT NOT NULL DEFAULT 0,
                config_json LONGTEXT NOT NULL,
                retained_json LONGTEXT NOT NULL,
                write_token VARCHAR(64) NULL
            )
            """
        )
        # BPL-033: a table made before the token column existed gets it on first touch
        if not f.db.sql(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
            (_STATE_TABLE, "write_token"),
        ):
            f.db.sql(f"ALTER TABLE `{_STATE_TABLE}` ADD COLUMN IF NOT EXISTS write_token VARCHAR(64) NULL")

    def _ensure_audit_table(self, f: Any) -> None:
        self._deployment_adapter(f)._ensure_audit_table()

    # ------------------------------------------------------------------ lifecycle & health
    def provision_tenant_site(self, tenant_id: str, params: dict[str, Any], site_state: dict[str, Any]) -> None:
        with self._site_session(tenant_id, create_if_missing=True) as (f, _site_name):
            f.db.sql("SELECT 1")
            self._ensure_audit_table(f)
            self._ensure_state_table(f)

            # Apply ADR-0033, Q-23, and E0-7 #4 safe defaults when ERPNext settings DocTypes exist
            pack = str(params.get("countryPack", "sa")).lower()
            defaults = COUNTRY_DEFAULTS.get(pack, COUNTRY_DEFAULTS["sa"])

            if hasattr(f.db, "exists") and f.db.exists("Stock Settings"):
                f.db.set_value("Stock Settings", "Stock Settings", "valuation_method", "Moving Average")
                f.db.set_value("Stock Settings", "Stock Settings", "allow_negative_stock", 0)

            if hasattr(f.db, "exists") and f.db.exists("System Settings"):
                f.db.set_value("System Settings", "System Settings", "rounding_method", "Commercial Rounding")
                f.db.set_value("System Settings", "System Settings", "language", defaults["language"])
                f.db.set_value("System Settings", "System Settings", "time_zone", defaults["timezone"])
                f.db.set_value("System Settings", "System Settings", "country", defaults["country"])

            if hasattr(f.db, "exists") and f.db.exists("Accounts Settings"):
                f.db.set_value("Accounts Settings", "Accounts Settings", "enable_immutable_ledger", 1)

            # E0-7 #4: Mask Item.valuation_rate (permlevel=1) so low-privilege Sales roles cannot read item costs
            if hasattr(f, "get_meta"):
                try:
                    item_meta = f.get_meta("Item")
                    if item_meta and item_meta.get_field("valuation_rate"):
                        if hasattr(f, "make_property_setter"):
                            f.make_property_setter(
                                {
                                    "doctype": "Item",
                                    "fieldname": "valuation_rate",
                                    "property": "permlevel",
                                    "value": 1,
                                    "property_type": "Int",
                                }
                            )
                except Exception:
                    pass

            if hasattr(f.db, "commit"):
                f.db.commit()

            self.persist_site_state(tenant_id, site_state)

    def persist_site_state(self, tenant_id: str, site_state: dict[str, Any]) -> bool:
        """Write the tenant-database copy of the site state; the operation store stays the source of truth (BPL-033).

        `write_token` tags the write. With an `expect_token` key the write is a compare-and-set: it replaces the copy only
        while the copy still carries that token (None: a copy with no token, or no copy at all); otherwise it changes
        nothing and returns False, so a writer that was overtaken cannot put an older state over a newer one. Without
        `expect_token` the write is unconditional: provisioning, and the operation that still holds the site lock."""
        with self._site_session(tenant_id) as (f, _):
            self._ensure_state_table(f)
            if "expect_token" in site_state:
                # the row lock lasts until the commit below, so the check and the write are one step for other writers
                rows = f.db.sql(
                    f"SELECT write_token FROM `{_STATE_TABLE}` WHERE tenant_id = %s FOR UPDATE", (tenant_id,), as_dict=True
                )
                row = rows[0] if rows else None
                current = (row.get("write_token") if isinstance(row, dict) else row[0]) if row is not None else None
                if (row is None and site_state["expect_token"] is not None) or (
                    row is not None and current != site_state["expect_token"]
                ):
                    if hasattr(f.db, "commit"):
                        f.db.commit()  # nothing changed; release the row lock
                    return False
            f.db.sql(
                f"""
                INSERT INTO `{_STATE_TABLE}` (
                    tenant_id, state, site_class, engine_target_json, blueprint_id,
                    country_pack, applied_json, applied_ids_json, history_json,
                    sync_version, config_json, retained_json, write_token
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    state = VALUES(state),
                    site_class = VALUES(site_class),
                    engine_target_json = VALUES(engine_target_json),
                    blueprint_id = VALUES(blueprint_id),
                    country_pack = VALUES(country_pack),
                    applied_json = VALUES(applied_json),
                    applied_ids_json = VALUES(applied_ids_json),
                    history_json = VALUES(history_json),
                    sync_version = VALUES(sync_version),
                    config_json = VALUES(config_json),
                    retained_json = VALUES(retained_json),
                    write_token = VALUES(write_token)
                """,
                (
                    tenant_id,
                    site_state["state"],
                    site_state["site_class"],
                    json.dumps(site_state["engine_target"]),
                    site_state["blueprint_id"],
                    site_state["country_pack"],
                    json.dumps(site_state["applied"]) if site_state["applied"] is not None else None,
                    json.dumps(sorted(site_state["applied_ids"])),
                    json.dumps(site_state["history"]),
                    int(site_state["sync_version"]),
                    json.dumps(site_state["config"]),
                    json.dumps(site_state["retained"]),
                    site_state.get("write_token"),
                ),
            )
            if hasattr(f.db, "commit"):
                f.db.commit()
        return True

    def load_site_state(self, tenant_id: str) -> dict[str, Any] | None:
        try:
            with self._site_session(tenant_id, create_if_missing=False) as (f, _):
                self._ensure_state_table(f)  # adds the token column to a table made before it existed
                rows = f.db.sql(
                    f"""
                    SELECT tenant_id, state, site_class, engine_target_json, blueprint_id,
                           country_pack, applied_json, applied_ids_json, history_json,
                           sync_version, config_json, retained_json, write_token
                    FROM `{_STATE_TABLE}`
                    WHERE tenant_id = %s
                    """,
                    (tenant_id,),
                    as_dict=True,
                )
        except Exception:
            return None
        if not rows:
            return None
        row = rows[0]
        if not isinstance(row, dict):
            keys = (
                "tenant_id",
                "state",
                "site_class",
                "engine_target_json",
                "blueprint_id",
                "country_pack",
                "applied_json",
                "applied_ids_json",
                "history_json",
                "sync_version",
                "config_json",
                "retained_json",
                "write_token",
            )
            row = dict(zip(keys, row))
        return {
            "tenant_id": row["tenant_id"],
            "state": row["state"],
            "site_class": row["site_class"],
            "engine_target": json.loads(row["engine_target_json"]),
            "blueprint_id": row["blueprint_id"],
            "country_pack": row["country_pack"],
            "applied": json.loads(row["applied_json"]) if row.get("applied_json") else None,
            "applied_ids": set(json.loads(row["applied_ids_json"])),
            "history": json.loads(row["history_json"]),
            "sync_version": int(row["sync_version"]),
            "config": json.loads(row["config_json"]),
            "retained": json.loads(row["retained_json"]),
            "write_token": row.get("write_token"),
        }

    def check_health(self, tenant_id: str, site_state_value: str | None = None) -> list[dict[str, str]]:
        if tenant_id == "platform":
            try:
                f = self._acquire_frappe()
                return [
                    {"name": "database", "status": "ok" if f is not None else "down"},
                    {"name": "workers", "status": "ok"},
                ]
            except FrappeBackendError:
                return [{"name": "database", "status": "down"}, {"name": "workers", "status": "down"}]

        with self._site_session(tenant_id) as (f, site_name):
            db_ok = False
            lock_ok = False
            recovery_blocked = site_state_value == "recovery_required"

            try:
                res = f.db.sql("SELECT 1")
                db_ok = bool(res)
            except Exception:
                db_ok = False

            try:
                dep = self._deployment_adapter(f)
                probe_lock = f"ce:health:{hashlib.sha256(site_name.encode()).hexdigest()[:24]}"
                got = dep.acquire_advisory_lock(probe_lock, wait_seconds=1)
                if got == 1:
                    lock_ok = True
                    dep.release_advisory_lock(probe_lock)
            except Exception:
                lock_ok = False

            try:
                self._ensure_audit_table(f)
                # E0-7 #2: Flag both RECOVERY_REQUIRED and stale unfinalized PREPARED rows
                rows = f.db.sql(
                    "SELECT COUNT(*) FROM `tabChange Engine Audit` WHERE status IN ('RECOVERY_REQUIRED', 'PREPARED')"
                )
                if rows and rows[0][0] > 0:
                    recovery_blocked = True
            except Exception:
                pass

            return [
                {"name": "database", "status": "ok" if db_ok else "down"},
                {"name": "site_lock", "status": "ok" if lock_ok else "degraded"},
                {"name": "recovery", "status": "down" if recovery_blocked else "ok"},
            ]

    # ------------------------------------------------------------------ plan inspection
    def inspect_step_plan(self, tenant_id: str, step: dict[str, Any], is_retained: bool) -> tuple[str, str] | None:
        """Inspect live Frappe column metadata and DDL plan gate for additive field steps."""
        if step.get("kind") != "field.add" or is_retained:
            return None

        subject = step.get("subject") or {}
        parents = subject.get("parents") or []
        entity_id = str(parents[0]["id"]) if parents else "entity"
        defn = (step.get("params") or {}).get("definition") or {}
        if not isinstance(defn, dict):
            return None

        doctype = entity_to_doctype(entity_id)
        fieldname = _sanitize_custom_fieldname(str(defn.get("id") or subject.get("id") or "field"))
        bp_type = defn.get("type", "string")
        if bp_type not in BLUEPRINT_TO_FRAPPE_FIELDTYPE:
            return ("blocked", "unsupported_value_type")

        frappe_field_def = self._to_frappe_field_def(doctype, fieldname, defn)
        with self._site_session(tenant_id) as (f, _):
            dep = self._deployment_adapter(f)
            if dep.is_target_in_recovery_required(tenant_id, doctype):
                return ("blocked", "recovery_required")
            if getattr(f.db, "table_exists", None) and f.db.table_exists(doctype):
                plan = dep.inspect_ddl_plan(doctype, frappe_field_def)
                is_approved = plan.inspectable and plan.is_approved_additive_only
                if (
                    not is_approved
                    and plan.inspectable
                    and not defn.get("unique")
                    and not defn.get("indexed")
                    and len(plan.statements) == 1
                    and _DECIMAL_ADD_RE.match(plan.statements[0])
                ):
                    is_approved = True
                if not is_approved:
                    reason = "unique_or_index" if (defn.get("unique") or defn.get("indexed")) else "storage_not_additive"
                    return ("gated", reason)
        return None

    def _to_frappe_field_def(self, doctype: str, fieldname: str, defn: dict[str, Any]) -> dict[str, Any]:
        bp_type = defn.get("type", "string")
        frappe_type = BLUEPRINT_TO_FRAPPE_FIELDTYPE.get(bp_type, "Data")
        labels = defn.get("labels") if isinstance(defn.get("labels"), dict) else {}
        label = labels.get("en") or labels.get("ar") or str(defn.get("id") or fieldname).replace("_", " ").title()

        options = None
        if frappe_type == "Select" and isinstance(defn.get("options"), list):
            options = "\n".join(str(o.get("value") or o.get("id") or "") for o in defn["options"] if isinstance(o, dict))
        elif frappe_type == "Link" and defn.get("target"):
            options = entity_to_doctype(str(defn["target"]))

        return {
            "fieldname": fieldname,
            "fieldtype": frappe_type,
            "label": label,
            "reqd": 1 if defn.get("required") else 0,
            "read_only": 1 if defn.get("readOnly") else 0,
            "unique": 1 if defn.get("unique") else 0,
            "search_index": 1 if defn.get("indexed") else 0,
            "precision": defn.get("precision"),
            "length": defn.get("maxLength"),
            "options": options,
            "default": defn.get("default"),
        }

    # ------------------------------------------------------------------ step execution
    def execute_step(self, tenant_id: str, step: dict[str, Any]) -> None:
        kind = step["kind"]
        pointer = step["pointer"]
        subject = step["subject"]
        params = step.get("params") or {}
        segs = [s.replace("~1", "/").replace("~0", "~") for s in pointer.split("/")[1:]]

        with self._site_session(tenant_id) as (f, _site_name):
            dep = self._deployment_adapter(f)
            try:
                if kind == "entity.add":
                    entity_id = str(subject.get("id") or (segs[1] if len(segs) > 1 else "entity"))
                    self._refuse_protected_entity(entity_id)
                    doctype = entity_to_doctype(entity_id)
                    self._add_entity(f, dep, tenant_id, entity_id, doctype, params.get("definition") or {})

                elif kind == "entity.quarantine":
                    entity_id = str(subject.get("id") or (segs[1] if len(segs) > 1 else "entity"))
                    if is_contract_mapped_entity(entity_id):
                        self._quarantine_entity_fields(f, dep, tenant_id, entity_to_doctype(entity_id))

                elif kind in ("field.add", "relation.add"):
                    parents = subject.get("parents") or []
                    entity_id = str(parents[0]["id"]) if parents else (segs[1] if len(segs) > 1 else "entity")
                    self._refuse_protected_entity(entity_id)
                    doctype = entity_to_doctype(entity_id)
                    defn = params.get("definition") or {"id": subject.get("id") or "field", "type": "string"}
                    if kind == "relation.add":
                        defn = {**defn, "type": "link", "id": defn.get("id") or subject.get("id") or "rel"}
                    fieldname = _sanitize_custom_fieldname(str(defn.get("id") or subject.get("id") or "field"))
                    if (defn.get("unique") or defn.get("indexed")) and not self._held_fields(f, doctype, [fieldname], set(), {}):
                        raise self._refuse("unique_or_index")  # before `_ensure_doctype_exists` writes; Q-603
                    self._ensure_doctype_exists(f, doctype, {})
                    self._apply_or_restore_custom_field(f, dep, tenant_id, doctype, fieldname, defn)

                elif kind in ("field.quarantine", "relation.quarantine"):
                    parents = subject.get("parents") or []
                    entity_id = str(parents[0]["id"]) if parents else (segs[1] if len(segs) > 1 else "entity")
                    doctype = entity_to_doctype(entity_id)
                    fieldname = _sanitize_custom_fieldname(str(subject.get("id") or segs[-1]))
                    self._quarantine_field(dep, tenant_id, doctype, fieldname)

                elif kind in ("field.set_property", "relation.set_property"):
                    parents = subject.get("parents") or []
                    entity_id = str(parents[0]["id"]) if parents else (segs[1] if len(segs) > 1 else "entity")
                    doctype = entity_to_doctype(entity_id)
                    fieldname = _sanitize_custom_fieldname(str(subject.get("id") or segs[-1]))
                    prop_ptr = str(params.get("property") or "")
                    mapped = _BP_PROP_TO_FRAPPE.get(prop_ptr)
                    if prop_ptr in ("/unique", "/indexed"):
                        # Unique and index are DDL this backend deploys nowhere (Q-603), so the step applies only when the
                        # engine field already holds exactly the requested value, and then there is nothing to write.
                        meta = f.get_meta(doctype)
                        named = (fieldname, str(subject.get("id") or segs[-1]))
                        holders = [x for x in (meta.get_field(n) for n in named) if x is not None]
                        wanted = bool(params.get("after"))
                        if not holders or any(self._has_constraint(x, prop_ptr) != wanted for x in holders):
                            raise self._refuse("unique_or_index")
                    elif mapped:
                        frappe_prop, frappe_ptype = mapped
                        if "after" not in params or params.get("after") is None:
                            self._delete_property_setter(dep, doctype, fieldname, frappe_prop)
                        else:
                            val = params["after"]
                            if frappe_prop == "options" and isinstance(val, list):
                                val = "\n".join(
                                    str(o.get("value") or o.get("id") or "")
                                    if isinstance(o, dict)
                                    else str(o)
                                    for o in val
                                )
                            self._apply_property_setter(dep, tenant_id, doctype, fieldname, frappe_prop, val, frappe_ptype)

                elif kind == "workflow.upsert":
                    defn = params.get("definition") or {}
                    self._deploy_workflow(f, dep, tenant_id, defn)

                elif kind == "workflow.disable":
                    wf_id = str(subject.get("id") or segs[-1])
                    if hasattr(f.db, "exists") and f.db.exists("Workflow", wf_id):
                        wf_dt = f.db.get_value("Workflow", wf_id, "document_type") if hasattr(f.db, "get_value") else None
                        f.db.set_value("Workflow", wf_id, "is_active", 0)
                        if hasattr(f.db, "commit"):
                            f.db.commit()
                        if wf_dt:
                            dep.clear_doctype_cache(str(wf_dt))

                elif kind == "report.upsert":
                    defn = params.get("definition") or {}
                    self._deploy_report(f, dep, tenant_id, defn)

                elif kind == "report.disable":
                    rep_id = str(subject.get("id") or segs[-1])
                    if hasattr(f.db, "exists") and f.db.exists("Report", rep_id):
                        rep_dt = f.db.get_value("Report", rep_id, "ref_doctype") if hasattr(f.db, "get_value") else None
                        f.db.set_value("Report", rep_id, "disabled", 1)
                        if hasattr(f.db, "commit"):
                            f.db.commit()
                        if rep_dt:
                            dep.clear_doctype_cache(str(rep_dt))

                elif kind == "role.upsert":
                    defn = params.get("definition")
                    # The gated subject, the pointer and the definition must name one role (ADR-0051).
                    if not (
                        isinstance(defn, dict)
                        and isinstance(subject, dict)
                        and segs[:1] == ["roles"]
                        and len(segs) == 2
                        and subject.get("id") == segs[1] == defn.get("id")
                    ):
                        raise self._refuse("definition_conflict")
                    self._upsert_role(f, defn["id"], defn)

                elif kind == "role.disable":
                    self._disable_role(f, subject.get("id") or segs[-1])

                elif kind == "location.upsert":
                    defn = params.get("definition") or {}
                    # BPL-033: dispatch on the Blueprint location kind. A branch or a department has no engine record
                    # yet (engine-adapter open question 11), so it is an explicit no-op, never a Warehouse.
                    if self._location_kind(defn.get("kind")) == "warehouse":
                        wh_name = str(defn.get("id") or subject.get("id"))
                        explicit_company = defn.get("company") or params.get("company")
                        existing, company = self._find_warehouse(
                            f,
                            wh_name,
                            company_name=explicit_company if isinstance(explicit_company, str) else None,
                            require_company=True,
                        )
                        if existing:
                            f.db.set_value("Warehouse", existing, "disabled", 0)
                        else:
                            doc = {"doctype": "Warehouse", "warehouse_name": wh_name, "disabled": 0}
                            if company:
                                doc["company"] = company
                            f.get_doc(doc).insert(ignore_permissions=True)
                        if hasattr(f.db, "commit"):
                            f.db.commit()

                elif kind == "location.disable":
                    loc_id = str(subject.get("id") or segs[-1])
                    defn = params.get("definition") if isinstance(params.get("definition"), dict) else {}
                    explicit_company = params.get("company") or defn.get("company")
                    # BPL-033 (review of PR #301): the kind is required. A disable never defaults to a Warehouse, because
                    # the Blueprint location may be a branch or department that shares the id; unresolved fails closed.
                    if self._location_kind(defn.get("kind")) == "warehouse":
                        existing, _company = self._find_warehouse(
                            f,
                            loc_id,
                            company_name=explicit_company if isinstance(explicit_company, str) else None,
                            require_company=False,
                        )
                        if existing:
                            f.db.set_value("Warehouse", existing, "disabled", 1)
                            if hasattr(f.db, "commit"):
                                f.db.commit()

                elif kind == "settings.set":
                    has_after = "after" in params and params.get("after") is not None
                    self._sync_settings(
                        f,
                        tenant_id,
                        segs[0] if segs else "",
                        str(params.get("property") or ""),
                        params.get("after") if has_after else None,
                        unset=not has_after,
                    )
            except Exception:
                if hasattr(f, "db") and hasattr(f.db, "rollback"):
                    try:
                        f.db.rollback()
                    except Exception:
                        pass
                raise

    @staticmethod
    def _location_kind(kind: Any) -> str:
        """The Blueprint location kind (branch, warehouse, department). Anything else, including none, is refused before
        any write."""
        if not isinstance(kind, str) or kind not in LOCATION_KINDS:  # a list or dict kind is unhashable: test the type first
            raise FrappeBackendError(
                "invalid_request", {"fields": ["/params/definition/kind"]}, stage="execute", side_effect_free=True
            )
        return str(kind)

    def check_ready(self, tenant_id: str, steps: list[dict[str, Any]]) -> None:
        """Read-only readiness check before the first step of an apply or rollback (BPL-033, contract 5.6.1).

        Refuses with a side-effect-free error when the engine site cannot take the artifact: its database does not
        answer, a location upsert or disable step has no kind the adapter knows, or a warehouse step has no resolvable company. The
        engine turns the refusal into ``failed_clean`` (nothing ran) instead of compensating committed steps."""
        self._check_step_shapes(steps)
        with self._site_session(tenant_id) as (f, _site_name):
            try:
                f.db.sql("SELECT 1")
            except Exception as exc:
                raise FrappeBackendError("engine_unavailable", stage="prepare", side_effect_free=True) from exc
            for step in steps:
                if step.get("kind") not in ("location.upsert", "location.disable"):
                    continue
                params = step.get("params") or {}
                defn = params.get("definition") if isinstance(params.get("definition"), dict) else {}
                if self._location_kind(defn.get("kind")) != "warehouse" or step["kind"] == "location.disable":
                    continue
                explicit_company = defn.get("company") or params.get("company")
                subject = step.get("subject") or {}
                self._find_warehouse(
                    f,
                    str(defn.get("id") or subject.get("id")),
                    company_name=explicit_company if isinstance(explicit_company, str) else None,
                    require_company=True,
                )
            self._check_entity_refusals(f, steps)

    @staticmethod
    def _check_step_shapes(steps: list[dict[str, Any]]) -> None:
        """A step whose shape the checks below cannot read is a side-effect-free invalid_request (the code `_location_kind`
        uses), never a generic engine_unavailable (BPL-041 review round 1)."""
        for i, step in enumerate(steps):
            bad = None if isinstance(step, dict) else f"/steps/{i}"
            if bad is None and step.get("kind") in ("entity.add", "field.add", "relation.add"):
                params, subject = step.get("params"), step.get("subject")
                defn = params.get("definition") if isinstance(params, dict) else None
                parents = subject.get("parents") if isinstance(subject, dict) else None
                fields = defn.get("fields") if isinstance(defn, dict) else None
                for ok, where in (
                    (params is None or isinstance(params, dict), "params"),
                    (subject is None or isinstance(subject, dict), "subject"),
                    (defn is None or isinstance(defn, dict), "params/definition"),
                    (fields is None or (isinstance(fields, list) and all(isinstance(x, dict) for x in fields)), "params/definition/fields"),
                    (parents is None or (isinstance(parents, list) and all(isinstance(x, dict) and "id" in x for x in parents)), "subject/parents"),
                ):
                    if not ok:
                        bad = f"/steps/{i}/{where}"
                        break
            if bad:
                raise FrappeBackendError("invalid_request", {"fields": [bad]}, stage="prepare", side_effect_free=True)

    def _check_entity_refusals(self, f: Any, steps: list[dict[str, Any]]) -> None:
        """BPL-041: the BPL-031 refusals of entity.add, field.add and relation.add, found before the first step runs.

        Same checks, error type and reason codes as the execute path (``protected_subject``, ``subject_missing``,
        ``unique_or_index``), read-only, in step order. Each step is judged against the engine as it is now plus an
        in-memory projection of what the steps before it will create, as execute would see it: ``made`` maps (type, field)
        to the field an earlier step adds (types an earlier step creates appear in ``made_types``). The execute-time
        checks stay as a second line."""
        made_types: set[str] = set()
        made: dict[tuple[str, str], Any] = {}
        for step in steps:
            kind = step.get("kind")
            if kind not in ("entity.add", "field.add", "relation.add"):
                continue
            subject = step.get("subject") or {}
            params = step.get("params") or {}
            segs = [s.replace("~1", "/").replace("~0", "~") for s in str(step.get("pointer") or "").split("/")[1:]]
            if kind == "entity.add":
                entity_id = str(subject.get("id") or (segs[1] if len(segs) > 1 else "entity"))
                self._refuse_protected_entity(entity_id)
                self._check_entity_add(f, entity_id, entity_to_doctype(entity_id), params.get("definition") or {}, made_types, made)
                continue
            parents = subject.get("parents") or []
            entity_id = str(parents[0]["id"]) if parents else (segs[1] if len(segs) > 1 else "entity")
            self._refuse_protected_entity(entity_id)
            doctype = entity_to_doctype(entity_id)
            defn = params.get("definition") or {"id": subject.get("id") or "field", "type": "string"}
            fieldname = _sanitize_custom_fieldname(str(defn.get("id") or subject.get("id") or ("rel" if kind == "relation.add" else "field")))
            held = self._held_fields(f, doctype, [fieldname], made_types, made)
            if held:
                if any(self._lacks_constraint(x, defn.get("unique"), defn.get("indexed")) for x in held):
                    raise self._refuse("unique_or_index")
            else:  # execute creates the type if it is missing (`_ensure_doctype_exists`), then the field, never with a constraint
                if defn.get("unique") or defn.get("indexed"):  # no field holds it, so it would be added without it (Q-603)
                    raise self._refuse("unique_or_index")
                self._project_new_type(f, doctype, made_types, made, [])
                made[(doctype, fieldname)] = _NO_CONSTRAINT

    def _held_fields(self, f: Any, doctype: str, names: list[str], made_types: set[str], made: dict[tuple[str, str], Any]) -> list[Any]:
        """The fields of these names the type holds: on the engine now, or added by an earlier step of the plan."""
        held = []
        if doctype not in made_types and self._doctype_exists(f, doctype):
            # get_meta may fill the engine's own metadata cache on a miss; that is not a business-data write, and the
            # execute path reads the same way, so readiness stays as read-only as execute's own checks.
            meta = f.get_meta(doctype)
            held += [x for x in (meta.get_field(n) for n in names) if x is not None]
        return held + [made[(doctype, n)] for n in names if (doctype, n) in made]

    def _project_new_type(self, f: Any, doctype: str, made_types: set[str], made: dict[tuple[str, str], Any],
                          fields: list[dict[str, Any]]) -> None:
        """Record the type `_ensure_doctype_exists` would create. It never carries a unique or index constraint (BPL-043)."""
        if doctype in made_types or self._doctype_exists(f, doctype):
            return
        made_types.add(doctype)
        known = [fld for fld in fields if fld.get("type", "string") in BLUEPRINT_TO_FRAPPE_FIELDTYPE]
        for fld in known:
            made[(doctype, _sanitize_custom_fieldname(str(fld.get("id") or "field")))] = _NO_CONSTRAINT
        if not known:
            made[(doctype, "title")] = _NO_CONSTRAINT

    def _check_entity_add(self, f: Any, entity_id: str, doctype: str, defn: dict[str, Any], made_types: set[str],
                          made: dict[tuple[str, str], Any]) -> None:
        """The refusals `_add_entity` raises, without its writes, and the type and fields it would leave behind."""
        fields = [fld for fld in defn.get("fields") or [] if isinstance(fld, dict)]
        exists = doctype in made_types or self._doctype_exists(f, doctype)
        if not is_contract_mapped_entity(entity_id):
            if exists and doctype not in made_types and not self._adapter_owns_doctype(f, doctype):
                raise self._refuse("protected_subject")
            self._refuse_constrained_fields(fields)
            self._project_new_type(f, doctype, made_types, made, fields)
            return
        if not exists:
            raise self._refuse("subject_missing")
        if any(fld.get("type", "string") not in BLUEPRINT_TO_FRAPPE_FIELDTYPE for fld in fields):
            raise self._refuse("unsupported_value_type")
        added: dict[tuple[str, str], Any] = {}  # every field is judged against the state before this step, as execute does
        for fld in fields:
            names = [_sanitize_custom_fieldname(str(fld.get("id") or "field")), str(fld.get("id"))]
            holders = self._held_fields(f, doctype, names, made_types, made)
            if holders:
                if any(self._lacks_constraint(x, fld.get("unique"), fld.get("indexed")) for x in holders):
                    raise self._refuse("unique_or_index")
            elif fld.get("unique") or fld.get("indexed"):
                raise self._refuse("unique_or_index")
            else:
                added[(doctype, names[0])] = _NO_CONSTRAINT
        made.update(added)

    def _find_warehouse(
        self,
        f: Any,
        wh_name: str,
        *,
        company_name: str | None = None,
        require_company: bool = True,
    ) -> tuple[str | None, str | None]:
        """Return (existing warehouse name, company) for a Blueprint warehouse id (BPL-027).

        The engine requires a company on a warehouse and names it "<warehouse_name> - <abbr>", so a lookup by the
        bare id misses it and an insert without a company fails.

        Company resolution is fail-closed:
        - If ``company_name`` is explicitly provided (in the Blueprint definition or step params), verify it exists
          on the site; otherwise raise ``site_not_ready``.
        - Otherwise, if more than one Company exists on the site, refuse to guess (never silently pick a global
          default or the oldest company) and raise ``site_not_ready``.
        - If exactly one Company exists, use it.
        - If no Company exists: raise ``site_not_ready`` when ``require_company=True`` (``location.upsert``), or
          return ``(None, None)`` when ``require_company=False`` (``location.disable`` is a documented no-op because
          zero companies means no company-scoped warehouse exists to disable).
        """
        meta = f.get_meta("Warehouse") if hasattr(f, "get_meta") else None
        company_field = meta.get_field("company") if meta is not None else None
        if company_field is None:
            if hasattr(f.db, "exists") and f.db.exists("Warehouse", wh_name):
                return wh_name, None
            return None, None
        companies = [str(c) for c in f.get_all("Company", pluck="name", order_by="creation asc") if c]
        explicit = company_name.strip() if isinstance(company_name, str) and company_name.strip() else None
        if explicit is not None:
            if explicit not in companies:
                raise FrappeBackendError("site_not_ready", stage="execute", side_effect_free=True)
            company = explicit
        elif len(companies) > 1:
            raise FrappeBackendError("site_not_ready", stage="execute", side_effect_free=True)
        elif len(companies) == 1:
            company = companies[0]
        else:
            if require_company:
                raise FrappeBackendError("site_not_ready", stage="execute", side_effect_free=True)
            return None, None
        existing = f.db.get_value("Warehouse", {"warehouse_name": wh_name, "company": company}, "name")
        return (str(existing) if existing else None), company

    def _refuse_protected_entity(self, entity_id: str) -> None:
        """No field or type is added to a protected or locked entity, or to a reserved internal name, whatever the plan
        said (SEC-022, ADR-0051; BPL-031 review). Raised before any write."""
        if is_protected_entity(entity_id):
            raise self._refuse("protected_subject")

    def _add_entity(self, f: Any, dep: FrappeDeploymentAdapter, tenant_id: str, entity_id: str, doctype: str,
                    defn: dict[str, Any]) -> None:
        """entity.add (BPL-031). The rule comes from the mapping contract and ADR-0051 item 3:
        - an entity the contract maps to a built-in type gets the Blueprint's fields as custom fields on that type,
          through the guarded field path; a missing built-in is refused, never created under its name;
        - an entity with no mapping becomes one adapter-owned custom type (custom=1 in the adapter's module); if the
          derived name is already an engine type the adapter did not make, it is refused instead of applying nothing.
        Every refusal is raised before any write."""
        exists = self._doctype_exists(f, doctype)
        if not is_contract_mapped_entity(entity_id):
            if exists and not self._adapter_owns_doctype(f, doctype):
                raise self._refuse("protected_subject")
            self._ensure_doctype_exists(f, doctype, defn)
            return
        if not exists:
            raise self._refuse("subject_missing")
        fields = [fld for fld in defn.get("fields") or [] if isinstance(fld, dict)]
        if any(fld.get("type", "string") not in BLUEPRINT_TO_FRAPPE_FIELDTYPE for fld in fields):
            raise self._refuse("unsupported_value_type")
        meta = f.get_meta(doctype)
        journaled = self._journaled_fields(f, doctype)
        add: list[tuple[str, dict[str, Any]]] = []
        restore: list[tuple[str, dict[str, Any]]] = []
        present: list[str] = []
        for fld in fields:
            fieldname = _sanitize_custom_fieldname(str(fld.get("id") or "field"))
            held = meta.get_field(fieldname)
            holders = [x for x in (held, meta.get_field(str(fld.get("id")))) if x is not None]
            if holders:
                # A field the type already holds (a native field of the same name, or one added earlier) is left alone, but
                # only if it already enforces what the definition asks for: skipping it must never apply the field without
                # its unique or index constraint (Q-603). The exception is a field this adapter added that a rollback hid:
                # re-applying the entity restores it.
                if any(self._lacks_constraint(x, fld.get("unique"), fld.get("indexed")) for x in holders):
                    raise self._refuse("unique_or_index")
                present.append(fieldname)
                if held is not None and fieldname in journaled and int(getattr(held, "hidden", 0) or 0):
                    restore.append((fieldname, fld))
                continue
            if fld.get("unique") or fld.get("indexed"):
                # The guarded field path cannot deploy unique or index DDL here (it queues it for a controlled admin
                # deployment and the gate approval is not passed to the backend), so the field is never added without
                # its constraint: refuse the entity before any write (Q-603).
                raise self._refuse("unique_or_index")
            add.append((fieldname, fld))
        # Intent first, so a rollback finds every field this step may have created; a row becomes "created" only once this
        # call has created the field itself, and one whose field appeared without us is dropped, never adopted.
        if add or present:
            self._record_entity_fields(f, doctype, [name for name, _ in add], present)
        for fieldname, fld in add:
            if self._apply_or_restore_custom_field(f, dep, tenant_id, doctype, fieldname, fld):
                self._confirm_entity_field(f, doctype, fieldname)
        for fieldname, fld in restore:
            self._apply_or_restore_custom_field(f, dep, tenant_id, doctype, fieldname, fld)

    @staticmethod
    def _has_constraint(field: Any, prop_ptr: str) -> bool:
        """Does the engine field carry unique (/unique) or an index (/indexed; a unique field is indexed)?"""
        is_unique = bool(int(getattr(field, "unique", 0) or 0))
        return is_unique if prop_ptr == "/unique" else is_unique or bool(int(getattr(field, "search_index", 0) or 0))

    @classmethod
    def _lacks_constraint(cls, field: Any, unique: Any, indexed: Any) -> bool:
        """True when a definition asks for unique or index and this engine field does not carry it."""
        return bool((unique and not cls._has_constraint(field, "/unique")) or (indexed and not cls._has_constraint(field, "/indexed")))

    _ENTITY_FIELD_TABLE = "Change Engine Entity Field"

    def _journaled_fields(self, f: Any, doctype: str) -> set[str]:
        """Custom fields this adapter created for an entity.add on this existing type (never native, earlier or pending)."""
        if not f.db.table_exists(self._ENTITY_FIELD_TABLE):
            return set()
        rows = f.db.sql(
            f"SELECT fieldname FROM `tab{self._ENTITY_FIELD_TABLE}` WHERE doctype = %s AND status = 'created'", (doctype,)
        )
        return {str(r[0]) for r in rows or []}

    def _record_entity_fields(self, f: Any, doctype: str, fieldnames: list[str], present: list[str]) -> None:
        """Journal the intent to create fieldnames as pending; drop a stale pending row of a field that now exists."""
        if fieldnames:
            f.db.sql(
                f"CREATE TABLE IF NOT EXISTS `tab{self._ENTITY_FIELD_TABLE}` ("
                "doctype VARCHAR(140) NOT NULL, fieldname VARCHAR(140) NOT NULL, "
                "status VARCHAR(16) NOT NULL DEFAULT 'pending', PRIMARY KEY (doctype, fieldname))"
            )
        if f.db.table_exists(self._ENTITY_FIELD_TABLE):
            for fieldname in present:
                f.db.sql(
                    f"DELETE FROM `tab{self._ENTITY_FIELD_TABLE}` WHERE doctype = %s AND fieldname = %s AND status = 'pending'",
                    (doctype, fieldname),
                )
        for fieldname in fieldnames:
            f.db.sql(
                f"INSERT IGNORE INTO `tab{self._ENTITY_FIELD_TABLE}` (doctype, fieldname, status) VALUES (%s, %s, 'pending')",
                (doctype, fieldname),
            )
        if hasattr(f.db, "commit"):
            f.db.commit()

    def _confirm_entity_field(self, f: Any, doctype: str, fieldname: str) -> None:
        f.db.sql(
            f"UPDATE `tab{self._ENTITY_FIELD_TABLE}` SET status = 'created' "
            "WHERE doctype = %s AND fieldname = %s AND status = 'pending'",
            (doctype, fieldname),
        )
        if hasattr(f.db, "commit"):
            f.db.commit()

    def _quarantine_entity_fields(self, f: Any, dep: FrappeDeploymentAdapter, tenant_id: str, doctype: str) -> None:
        """entity.quarantine on a built-in type: hide exactly the custom fields its entity.add created; data stays."""
        meta = f.get_meta(doctype)
        for fieldname in sorted(self._journaled_fields(f, doctype)):
            if fieldname.startswith("custom_") and meta.get_field(fieldname) is not None:
                self._quarantine_field(dep, tenant_id, doctype, fieldname)

    @staticmethod
    def _doctype_exists(f: Any, doctype: str) -> bool:
        if f.db.exists("DocType", doctype):
            return True
        return bool(getattr(f.db, "table_exists", None) and f.db.table_exists(doctype))

    @staticmethod
    def _adapter_owns_doctype(f: Any, doctype: str) -> bool:
        row = f.db.get_value("DocType", doctype, ["name", "custom", "module"])  # a failed read raises
        return bool(row) and str(row[0]) == doctype and int(row[1] or 0) == 1 and row[2] == ADAPTER_DOCTYPE_MODULE

    def _refuse_constrained_fields(self, fields: list[Any]) -> None:
        """BPL-043 (Q-603): a type this adapter makes never carries `unique` or `indexed` fields, with or without a gate
        approval: creating one would deploy constraint DDL outside the guarded DDL gate. Refused before any write."""
        if any(isinstance(fld, dict) and (fld.get("unique") or fld.get("indexed")) for fld in fields):
            raise self._refuse("unique_or_index")

    def _ensure_doctype_exists(self, f: Any, doctype: str, defn: dict[str, Any]) -> None:
        self._refuse_constrained_fields(defn.get("fields") or [])
        if getattr(f.db, "table_exists", None) and f.db.table_exists(doctype):
            return
        fields = []
        for fld in defn.get("fields", []):
            if not isinstance(fld, dict):
                continue
            bp_t = fld.get("type", "string")
            if bp_t not in BLUEPRINT_TO_FRAPPE_FIELDTYPE:
                continue
            fname = _sanitize_custom_fieldname(str(fld.get("id") or "field"))
            fields.append(self._to_frappe_field_def(doctype, fname, fld))
        if not fields:
            fields = [{"fieldname": "title", "fieldtype": "Data", "label": "Title"}]
        doc = f.get_doc({"doctype": "DocType", "name": doctype, "module": ADAPTER_DOCTYPE_MODULE, "custom": 1, "fields": fields})
        doc.insert(ignore_permissions=True)
        if hasattr(f.db, "commit"):
            f.db.commit()

    @staticmethod
    def _has_docfield(dep: FrappeDeploymentAdapter, doctype: str, fieldname: str) -> bool:
        """Does the type's own definition declare the field? Read on the snapshot's connection; a failed read raises,
        it is never "absent"."""
        return bool(dep._frappe.db.sql(
            "SELECT name FROM `tabDocField` WHERE parent = %s AND fieldname = %s", (doctype, fieldname)
        ))

    def _apply_or_restore_custom_field(
        self,
        f: Any,
        dep: FrappeDeploymentAdapter,
        tenant_id: str,
        doctype: str,
        fieldname: str,
        defn: dict[str, Any],
    ) -> bool:
        """Create the custom field, or restore a quarantined one; True only when this call created it."""
        dep_id = self._next_id("dep_cf")
        snap = dep.take_snapshot(doctype, fieldname, expected_deployment_id=dep_id)
        has_meta = snap.has_meta
        # BPL-044: the fields of a type this adapter made are DocField rows, not Custom Field rows, so both are read. An
        # errored snapshot keeps its own refusal below.
        if not snap.error_code and self._has_docfield(dep, doctype, fieldname):
            # Fail closed: one name held by both is ambiguous, and a DocField of a type the adapter did not make is not
            # a field it may restore.
            if has_meta or not self._adapter_owns_doctype(f, doctype):
                raise FrappeBackendError("recovery_required", stage="execute")
            has_meta = True
        if has_meta and snap.has_col:
            # Non-destructive restore of a quarantined field (preserve column & existing rows!). The field exists, so a
            # unique or index request is only accepted if it already carries it (it is never added here, Q-603).
            if self._lacks_constraint(f.get_meta(doctype).get_field(fieldname), defn.get("unique"), defn.get("indexed")):
                raise self._refuse("unique_or_index")
            self._apply_property_setter(dep, tenant_id, doctype, fieldname, "hidden", 0, "Check")
            self._apply_property_setter(dep, tenant_id, doctype, fieldname, "reqd", 1 if defn.get("required") else 0, "Check")
            self._apply_property_setter(dep, tenant_id, doctype, fieldname, "read_only", 1 if defn.get("readOnly") else 0, "Check")
            dep.clear_doctype_cache(doctype)
            return False

        if has_meta != snap.has_col:
            raise FrappeBackendError("recovery_required", stage="execute")

        frappe_field_def = self._to_frappe_field_def(doctype, fieldname, defn)
        base_rev = dep.get_doctype_revision_hash(doctype)
        ddl_plan = dep.inspect_ddl_plan(doctype, frappe_field_def)
        is_decimal_additive = (
            ddl_plan.inspectable
            and not defn.get("unique")
            and not defn.get("indexed")
            and len(ddl_plan.statements) == 1
            and bool(_DECIMAL_ADD_RE.match(ddl_plan.statements[0]))
        )
        # The decimal phantom-MODIFY case supplies its own judged plan; everything else (both locks, the fresh read
        # view, the idempotency and recovery lookups, the timeout before the intent, the journal, finalization) is
        # the one guarded sequence.
        approved_plan = (
            DDLPlanInspection(inspectable=True, statements=list(ddl_plan.statements), is_approved_additive_only=True)
            if is_decimal_additive and not ddl_plan.is_approved_additive_only
            else None
        )
        try:
            outcome = execute_single_field_deployment(
                db=dep,
                deployment_id=dep_id,
                idempotency_key=f"idemp-{dep_id}",
                site_id=tenant_id,
                doctype=doctype,
                base_revision_hash=base_rev,
                field_def=frappe_field_def,
                approved_plan=approved_plan,
            )
        except SessionDiscardedError:
            raise FrappeBackendError("recovery_required", stage="execute") from None
        except (IdempotencyConflictError, DeploymentIntentConflictError, DurableEvidenceError, LockTimeoutError):
            # A clean refusal with no effect: the deployment id or key is already bound to something else, or
            # the durable evidence or the timeout could not be established. The details stay in the log.
            raise FrappeBackendError("engine_unavailable", stage="execute") from None
        status = outcome.get("status")
        if status == "RECOVERY_REQUIRED":
            raise FrappeBackendError("recovery_required", stage="execute")
        if status not in ("APPLIED", "ALREADY_APPLIED"):
            raise FrappeBackendError("engine_unavailable", stage="execute")
        return status == "APPLIED"

    def _quarantine_field(self, dep: FrappeDeploymentAdapter, tenant_id: str, doctype: str, fieldname: str) -> None:
        self._apply_property_setter(dep, tenant_id, doctype, fieldname, "hidden", 1, "Check")
        self._apply_property_setter(dep, tenant_id, doctype, fieldname, "reqd", 0, "Check")
        dep.clear_doctype_cache(doctype)

    def _delete_property_setter(
        self,
        dep: FrappeDeploymentAdapter,
        doctype: str,
        fieldname: str,
        property_name: str,
    ) -> None:
        if property_name not in PROPERTY_TYPE_MAP:
            return
        dep.delete_property_setter(doctype, fieldname, property_name)
        dep.clear_doctype_cache(doctype)

    def _apply_property_setter(
        self,
        dep: FrappeDeploymentAdapter,
        tenant_id: str,
        doctype: str,
        fieldname: str,
        property_name: str,
        value: Any,
        property_type: str,
    ) -> None:
        if property_name not in PROPERTY_TYPE_MAP:
            return
        dep_id = self._next_id("dep_ps")
        outcome = execute_property_setter_deployment(
            db=dep,
            deployment_id=dep_id,
            site_id=tenant_id,
            doctype=doctype,
            fieldname=fieldname,
            property_name=property_name,
            value=value,
            property_type=property_type,
            user_roles=self._actor_roles,
            idempotency_key=f"idemp-{dep_id}",
        )
        status = outcome.get("status")
        if status == "RECOVERY_REQUIRED":
            raise FrappeBackendError("recovery_required", stage="execute")
        if status not in ("APPLIED", "ALREADY_APPLIED"):
            raise FrappeBackendError("engine_unavailable", stage="execute")

    def _deploy_workflow(self, f: Any, dep: FrappeDeploymentAdapter, tenant_id: str, defn: dict[str, Any]) -> None:
        wf_id = str(defn.get("id") or "workflow")
        entity_id = str(defn.get("entity") or "sales_order")
        doctype = entity_to_doctype(entity_id)
        transitions = defn.get("transitions") or []
        states_raw = defn.get("states") or []
        draft_sources = {t.get("from") for t in transitions if isinstance(t, dict)}

        # SEC-022 (ADR-0051): states and roles get adapter-owned names; refuse, before any write, a name that is not
        # a Blueprint id or that the engine already holds under another spelling (it matches names without case).
        state = self._managed_state_name
        state_names = {state(s.get("id")) for s in states_raw}
        state_names |= {state(t.get(k)) for t in transitions for k in ("from", "to")}
        for name in sorted(state_names):  # a failed read raises: no lookup error is taken as "no collision"
            stored = f.db.get_value("Workflow State", name, "name")
            if stored and str(stored) != name:
                raise self._refuse("protected_subject")
        # Every transition names its roles (the Blueprint requires at least one); none falls back to a default.
        if not all(isinstance(t, dict) and isinstance(t.get("allowedRoles"), list) and t["allowedRoles"] for t in transitions):
            raise self._refuse("unsupported_value_type")
        role = {r: self._managed_role(f, r)[0] for t in transitions for r in t["allowedRoles"]}

        self._ensure_doctype_exists(f, doctype, {})

        # Ensure initial state is first and map doc_status cleanly without direct 0->2 jumps
        ordered_states = sorted(
            states_raw,
            key=lambda s: 0 if s.get("kind") == "initial" else 1,
        )
        state_kind_map = {s["id"]: s.get("kind", "normal") for s in ordered_states}

        wf_states: list[dict[str, Any]] = []
        for s in ordered_states:
            sid = str(s["id"])
            skind = s.get("kind", "normal")
            is_reject = sid.strip().lower() in TERMINAL_REJECT_STATE_NAMES
            if skind == "final":
                # If reachable from a draft state or named cancel/reject, keep doc_status=0 terminal (Frappe 0->2 constraint)
                came_from_non_final = any(
                    t.get("to") == sid and state_kind_map.get(t.get("from")) != "final"
                    for t in transitions
                )
                doc_status = 0 if (is_reject and came_from_non_final) else 1
                is_terminal = True
                style = "Danger" if is_reject else "Success"
            else:
                doc_status = 0
                is_terminal = sid not in draft_sources and skind != "initial"
                style = "Warning" if skind == "normal" else "Primary"

            allow_edit = "System Manager"
            for t in transitions:
                if t.get("from") == sid:
                    allow_edit = role[t["allowedRoles"][0]]
                    break

            wf_states.append(
                {
                    "state": state(sid),
                    "doc_status": doc_status,
                    "allow_edit": allow_edit,
                    "style": style,
                    "is_terminal": is_terminal,
                }
            )

        wf_transitions: list[dict[str, Any]] = []
        for t in transitions:
            action_labels = t.get("actionLabels") if isinstance(t.get("actionLabels"), dict) else {}
            action = str(action_labels.get("en") or t.get("id") or "Proceed")
            # The Workflow Action Master is created by the engine, after the intent and under the locks.
            for r in t["allowedRoles"]:
                wf_transitions.append(
                    {
                        "state": state(t["from"]),
                        "action": action,
                        "next_state": state(t["to"]),
                        "allowed": role[r],
                        "allow_self_approval": False,
                    }
                )

        wf_payload = {
            "workflow_name": wf_id,
            "document_type": doctype,
            "is_active": True,
            "workflow_state_field": "workflow_state",
            "states": wf_states,
            "transitions": wf_transitions,
            "send_email_alert": False,
        }
        dep_id = self._next_id("dep_wf")
        outcome = execute_workflow_deployment(
            db=dep,
            deployment_id=dep_id,
            site_id=tenant_id,
            doctype=doctype,
            workflow_def=wf_payload,
            user_roles=self._actor_roles,
            idempotency_key=f"idemp-{dep_id}",
        )
        status = outcome.get("status")
        if status == "RECOVERY_REQUIRED":
            raise FrappeBackendError("recovery_required", stage="execute")
        if outcome.get("disposition") == "WORKFLOW_STATE_NAME_COLLISION":  # a state appeared since the check above
            raise FrappeBackendError("plan_rejected", {"reasonCode": "protected_subject"}, stage="execute")
        if status != "APPLIED":
            raise FrappeBackendError("engine_unavailable", stage="execute")

    def _deploy_report(self, f: Any, dep: FrappeDeploymentAdapter, tenant_id: str, defn: dict[str, Any]) -> None:
        report_id = str(defn.get("id") or "report")
        entity_id = str(defn.get("entity") or "sales_order")
        doctype = entity_to_doctype(entity_id)
        # SEC-022 (ADR-0051): validate the roles before any write; no roles is refused, never "All" (fail closed).
        visible = defn.get("visibleToRoles")
        if not isinstance(visible, list) or not visible:
            raise self._refuse("unsupported_value_type")
        roles = [self._managed_role(f, r)[0] for r in visible]
        self._ensure_doctype_exists(f, doctype, {})

        columns: list[dict[str, Any]] = []
        for m in defn.get("metrics") or []:
            if not isinstance(m, dict):
                continue
            for gb in m.get("groupBy") or []:
                clean_gb = re.sub(r"[^a-zA-Z0-9_]", "_", str(gb))
                if clean_gb:
                    columns.append({"fieldname": clean_gb, "label": clean_gb.replace("_", " ").title()})
        if not columns:
            columns = [{"fieldname": "name", "label": "ID"}]

        rep_payload = {
            "report_name": report_id,
            "ref_doctype": doctype,
            "columns": columns,
            "filters": [],
            "roles": roles,
        }
        dep_id = self._next_id("dep_rep")
        outcome = execute_report_deployment(
            db=dep,
            deployment_id=dep_id,
            site_id=tenant_id,
            doctype=doctype,
            report_def=rep_payload,
            user_roles=self._actor_roles,
            idempotency_key=f"idemp-{dep_id}",
        )
        status = outcome.get("status")
        if status == "RECOVERY_REQUIRED":
            raise FrappeBackendError("recovery_required", stage="execute")
        if status != "APPLIED":
            raise FrappeBackendError("engine_unavailable", stage="execute")

    def _resolve_country_defaults(self, f: Any, tenant_id: str) -> dict[str, str]:
        pack = "sa"
        try:
            rows = f.db.sql(
                "SELECT country_pack FROM `tabChange Engine Blueprint State` WHERE tenant_id = %s",
                (tenant_id,),
                as_dict=True,
            )
            if rows:
                first = rows[0]
                raw_pack = first.get("country_pack") if isinstance(first, dict) else first[0]
                if isinstance(raw_pack, str) and raw_pack:
                    pack = raw_pack.lower()
        except Exception:
            pass
        return COUNTRY_DEFAULTS.get(pack, COUNTRY_DEFAULTS["sa"])

    def _sync_settings(
        self,
        f: Any,
        tenant_id: str,
        section: str,
        prop: str,
        value: Any,
        *,
        unset: bool = False,
    ) -> None:
        if section == "i18n" and prop == "/defaultLocale":
            target_lang = self._resolve_country_defaults(f, tenant_id)["language"] if unset else value
            if isinstance(target_lang, str) and hasattr(f.db, "exists") and f.db.exists("System Settings"):
                f.db.set_value("System Settings", "System Settings", "language", target_lang)
        elif section == "compliance" and prop == "/country":
            if unset:
                defaults = self._resolve_country_defaults(f, tenant_id)
            else:
                defaults = COUNTRY_DEFAULTS.get(value.lower()) if isinstance(value, str) else None
            if defaults and hasattr(f.db, "exists") and f.db.exists("System Settings"):
                f.db.set_value("System Settings", "System Settings", "country", defaults["country"])
                f.db.set_value("System Settings", "System Settings", "time_zone", defaults["timezone"])
        if hasattr(f.db, "commit"):
            f.db.commit()

    # ------------------------------------------------------------------ roles and permission rules (SEC-022, BPL-032)
    @staticmethod
    def _refuse(reason: str) -> FrappeBackendError:
        """A step the adapter will not apply, raised before any write (plan reason code in details)."""
        return FrappeBackendError("plan_rejected", {"reasonCode": reason}, stage="execute", side_effect_free=True)

    def _managed_state_name(self, state_id: Any) -> str:
        try:
            return engine_state_name(state_id)
        except EngineNameError:
            raise self._refuse("unsupported_value_type") from None

    def _managed_role(self, f: Any, role_id: Any) -> tuple[str, int | None]:
        """(managed name, disabled flag or None when absent) for a Blueprint role id (ADR-0051).

        The engine matches names without case; when its lookup returns a record under another spelling, that
        record is not ours (a built-in or someone else's role) and the step is refused."""
        try:
            name = engine_role_name(role_id)
        except EngineNameError:
            raise self._refuse("unsupported_value_type") from None
        row = f.db.get_value("Role", name, ["name", "disabled"])
        if not row:
            return name, None
        if str(row[0]) != name:
            raise self._refuse("protected_subject")
        return name, int(row[1] or 0)

    def _upsert_role(self, f: Any, role_id: Any, defn: dict[str, Any]) -> None:
        """Create or re-enable the managed role and reconcile its rules; every check runs before the first write."""
        name, disabled = self._managed_role(f, role_id)
        grants = self._role_grants(f, defn)
        plans = [self._plan_rules(f, dt, name, grants.get(dt)) for dt in sorted(set(grants) | self._rule_doctypes(f, name))]
        if disabled is None:
            f.get_doc({"doctype": "Role", "role_name": name, "desk_access": 0, "disabled": 0}).insert(ignore_permissions=True)
        elif disabled:
            f.db.set_value("Role", name, "disabled", 0)
        for plan in plans:
            self._write_rules(f, plan)
        if hasattr(f.db, "commit"):
            f.db.commit()

    def _disable_role(self, f: Any, role_id: Any) -> None:
        """A disabled role keeps its record and holds no rules (ADR-0039 RM-008)."""
        name, disabled = self._managed_role(f, role_id)
        if disabled is None:
            return
        for plan in [self._plan_rules(f, dt, name, None, revoking=True) for dt in sorted(self._rule_doctypes(f, name))]:
            self._write_rules(f, plan)
        f.db.set_value("Role", name, "disabled", 1)
        if hasattr(f.db, "commit"):
            f.db.commit()

    def can_grant_own_doctype(self, tenant_id: str, entity: str) -> bool:
        """Plan-time check: True only when an unmapped entity's derived doctype is adapter-owned or not yet created."""
        if is_protected_entity(entity) or entity in ENTITY_TO_DOCTYPE:
            return False
        doctype = entity_to_doctype(entity)
        if not _SAFE_SQL_IDENT_RE.fullmatch(doctype):
            return False
        with self._site_session(tenant_id) as (f, _):
            row = f.db.get_value("DocType", doctype, ["name", "custom", "module"])
            if row:
                return str(row[0]) == doctype and int(row[1] or 0) == 1 and row[2] == ADAPTER_DOCTYPE_MODULE
            if getattr(f.db, "table_exists", None) and f.db.table_exists(doctype):
                return False
            return True

    def _role_grants(self, f: Any, defn: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """ADR-0051 grant table: {doctype: {"flags", "hidden"}} for one Blueprint role; refuses or withholds, never widens."""
        scope = defn.get("scope").get("type") if isinstance(defn.get("scope"), dict) else None
        if scope == "assigned_records":
            raise self._refuse("unsupported_value_type")
        perms = defn.get("permissions") or []
        if not isinstance(perms, list) or not all(isinstance(p, dict) for p in perms):
            raise self._refuse("unsupported_value_type")
        resolved: dict[str, dict[str, Any]] = {}
        for p in perms:
            entity = p.get("entity")
            if not isinstance(entity, str):
                raise self._refuse("unsupported_value_type")
            doctype = self._grant_doctype(f, entity)
            if doctype in resolved:
                raise self._refuse("definition_conflict")
            resolved[doctype] = p
        if scope not in ("company", "own_records"):
            return {}  # branch, warehouse, department: withheld until record scoping on holders exists (ADR-0051)
        grants: dict[str, dict[str, Any]] = {}
        for doctype, p in resolved.items():
            meta = f.get_meta(doctype)
            fieldnames = {getattr(d, "fieldname", None) for d in meta.fields}
            hidden = self._hidden_fields(meta, fieldnames, p["entity"], p.get("hiddenFields") or [])
            if hidden is None:
                continue  # a hidden field that cannot be masked where its data lives: withhold the grant
            flags = rule_flags(
                p.get("actions"),
                masked=bool(p.get("hiddenFields") or p.get("readOnlyFields")),
                submittable=bool(int(getattr(meta, "is_submittable", 0) or 0)),
            )
            if flags:
                grants[doctype] = {"flags": {**flags, "if_owner": int(scope == "own_records")}, "hidden": hidden}
        return grants

    @staticmethod
    def _hidden_fields(meta: Any, fieldnames: set[Any], entity: str, hidden_fields: list[Any]) -> list[str] | None:
        """Engine fields the adapter lays out on permission levels for a grant's hiddenFields; None withholds the grant.

        Fail closed: a hidden Blueprint field is masked on EVERY engine field that can hold its data, or the grant is
        withheld. The representations are the contract's native field (CONTRACT_NATIVE_FIELDS: cost_price is
        valuation_rate), a native field of the Blueprint's own name (customer_name, the contract's same-name mapping),
        and the custom twin entity.add or field.add materialised (custom_<id>). The adapter never moves a native field,
        so each native one must already sit above level 0 (tenant provisioning puts valuation_rate on level 1); one the
        contract keeps on another record (None) or does not find on the type cannot be masked here. The custom twin, when
        it exists, is laid out on a protected level. A field with no representation at all cannot be masked either."""
        layout: set[str] = set()
        for h in hidden_fields:
            hid = str(h)
            natives = {hid} & fieldnames
            if (entity, hid) in CONTRACT_NATIVE_FIELDS:
                contract = CONTRACT_NATIVE_FIELDS[(entity, hid)]
                if contract is None or contract not in fieldnames:
                    return None
                natives.add(contract)
            if any(int(getattr(meta.get_field(n), "permlevel", 0) or 0) < 1 for n in natives):
                return None
            custom = _sanitize_custom_fieldname(hid)
            if custom in fieldnames:
                layout.add(custom)
            elif not natives:
                return None
        return sorted(layout)

    def _grant_doctype(self, f: Any, entity: str) -> str:
        """Allowlist (ADR-0051 item 3): the reviewed mapping minus protected entities, or a document type the adapter
        created for an unmapped entity (custom=1 in the adapter's module, stored under exactly that name)."""
        if is_protected_entity(entity):
            raise self._refuse("protected_subject")
        reviewed = reviewed_grant_doctype(entity)
        if reviewed is not None:
            exists = f.db.table_exists(reviewed) if hasattr(f.db, "table_exists") else f.db.exists("DocType", reviewed)
            if not exists:
                raise self._refuse("subject_missing")
            return reviewed
        doctype = entity_to_doctype(entity)
        if entity in ENTITY_TO_DOCTYPE or not _SAFE_SQL_IDENT_RE.fullmatch(doctype):
            raise self._refuse("protected_subject")
        row = f.db.get_value("DocType", doctype, ["name", "custom", "module"])  # a failed read raises
        if not row or str(row[0]) != doctype or int(row[1] or 0) != 1 or row[2] != ADAPTER_DOCTYPE_MODULE:
            raise self._refuse("protected_subject")
        return doctype

    @staticmethod
    def _rule_doctypes(f: Any, role_name: str) -> set[str]:
        return {str(r.get("parent")) for r in f.get_all("Custom DocPerm", filters={"role": role_name}, fields=["parent"])}

    @staticmethod
    def _rule_rows(f: Any, doctype: str) -> list[dict[str, Any]]:
        rows = []
        for r in f.get_all("Custom DocPerm", filters={"parent": doctype}, fields=["name"]):
            d = f.get_doc("Custom DocPerm", r.get("name"))
            rows.append({
                "name": r.get("name"),
                "role": str(getattr(d, "role", "") or ""),
                "permlevel": int(getattr(d, "permlevel", 0) or 0),
                **{k: int(getattr(d, k, 0) or 0) for k in (*RULE_FLAGS, "if_owner")},
            })
        return rows

    def _plan_rules(
        self,
        f: Any,
        doctype: str,
        role_name: str,
        grant: dict[str, Any] | None,
        *,
        revoking: bool = False,
    ) -> dict[str, Any]:
        """Target rules and field levels on one document type after this role's change (ADR-0039 item 3).

        Other managed roles' field visibility is read back from their rules, so the result does not depend on the
        order roles are applied in. Fields are grouped by the set of reading managed roles that hide them; each
        group keeps the level it holds or takes the lowest free one. A level holding a field the adapter did not
        place, or a rule of a role it does not own, is never used."""
        rows = self._rule_rows(f, doctype)
        foreign = [r["permlevel"] for r in rows if not r["role"].startswith(ENGINE_NAME_PREFIX)]
        if not rows:
            foreign = [int(r.get("permlevel") or 0) for r in f.get_all("DocPerm", filters={"parent": doctype}, fields=["permlevel"])]
        managed = [r for r in rows if r["role"].startswith(ENGINE_NAME_PREFIX)]
        level_of = {d.fieldname: int(getattr(d, "permlevel", 0) or 0) for d in f.get_meta(doctype).fields if getattr(d, "fieldname", None)}
        ours = {r["permlevel"] for r in managed if r["permlevel"] >= 1}
        reading = {r["role"]: (r["write"], r["if_owner"]) for r in managed if r["permlevel"] == 0 and r["read"] and r["role"] != role_name}
        if grant:
            reading[role_name] = (grant["flags"]["write"], grant["flags"]["if_owner"])
        reads_at = {(r["role"], r["permlevel"]) for r in managed if r["read"]}
        hidden = set(grant["hidden"]) if grant else set()
        # Only fields the adapter placed may sit on a level it owns: a custom_ field it moved with a level setter.
        # Any other field (or foreign role rule) on an owned level is drift and is never adopted or moved: grant and
        # upsert paths refuse (fail closed), while revocation proceeds without touching the foreign field.
        placed = {
            (str(r.get("field_name")), int(str(r.get("value"))))
            for r in f.get_all(
                "Property Setter",
                filters={"doc_type": doctype, "property": "permlevel"},
                fields=["field_name", "value"],
            )
            if r.get("value") is not None and str(r.get("value")).isdigit()
        }
        adapter_placed = {fn for fn, lvl in level_of.items() if fn.startswith("custom_") and (fn, lvl) in placed}
        drifted = {lvl for lvl in foreign if lvl in ours} | {
            lvl for fn, lvl in level_of.items() if lvl in ours and fn not in adapter_placed
        }
        if drifted and not revoking:
            raise self._refuse("protected_subject")
        layout = {fn for fn, lvl in level_of.items() if lvl in ours and fn in adapter_placed} | {
            fn for fn in hidden if level_of[fn] in ours | {0}
        }
        reserved = (
            {lvl for fn, lvl in level_of.items() if lvl >= 1 and fn not in layout}
            | {lvl for lvl in foreign if lvl >= 1}
            | drifted
        )
        sig = {}
        for fn in layout:
            lvl = level_of[fn]
            hiders = {y for y in reading if y != role_name and lvl >= 1 and (y, lvl) not in reads_at}
            sig[fn] = tuple(sorted(hiders | ({role_name} if fn in hidden else set())))
        level_for: dict[tuple[str, ...], int] = {}
        groups = sorted({s for s in sig.values() if s})
        for s in groups:
            held = sorted(
                {level_of[fn] for fn in layout if sig[fn] == s and level_of[fn] in ours}
                - set(level_for.values())
                - reserved
            )
            if held:
                level_for[s] = held[0]
        for s in groups:
            if s not in level_for:
                free = [lvl for lvl in range(1, MAX_PERMLEVEL + 1) if lvl not in reserved and lvl not in level_for.values()]
                if not free:
                    if revoking:
                        by_key_only: dict[tuple[str, int], list[dict[str, Any]]] = {}
                        for r in managed:
                            by_key_only.setdefault((r["role"], r["permlevel"]), []).append(r)
                        return {
                            "doctype": doctype,
                            "custom": bool(rows),
                            "target": {},
                            "rows": by_key_only,
                            "clear": [r for r in managed if r["role"] == role_name],
                            "setters": [],
                        }
                    raise FrappeBackendError("limit_exceeded", {"limit": "permission_levels"}, stage="execute", side_effect_free=True)
                level_for[s] = free[0]
        target: dict[tuple[str, int], dict[str, int]] = {}
        if grant:
            target[(role_name, 0)] = dict(grant["flags"])
        for s, lvl in level_for.items():
            for y, (write, if_owner) in reading.items():
                read = int(y not in s)
                target[(y, lvl)] = {**_ZERO_RULE, "read": read, "write": int(read and write), "if_owner": if_owner}
        by_key: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for r in managed:
            by_key.setdefault((r["role"], r["permlevel"]), []).append(r)
        clear = [r for key, rs in by_key.items() for i, r in enumerate(rs)
                 if key not in target and (key[0] == role_name or key[1] >= 1) or key in target and i > 0]
        setters = sorted((fn, level_for.get(sig[fn], 0)) for fn in layout if level_for.get(sig[fn], 0) != level_of[fn])
        return {"doctype": doctype, "custom": bool(rows), "target": target, "rows": by_key, "clear": clear, "setters": setters}

    @staticmethod
    def _set_rule(f: Any, row: dict[str, Any], values: dict[str, int]) -> None:
        if any(int(row.get(k) or 0) != v for k, v in values.items()):
            doc = f.get_doc("Custom DocPerm", row["name"])
            doc.update(values)
            doc.save(ignore_permissions=True)

    def _write_rules(self, f: Any, plan: dict[str, Any]) -> None:
        """Apply a _plan_rules result: narrow first, then move fields, then write the target rules."""
        doctype = plan["doctype"]
        if not (plan["target"] or plan["clear"] or plan["setters"]):
            return
        if not plan["custom"]:
            # The engine ignores standard rules once a custom rule exists, so copy them first, through its own API.
            perms_api = getattr(f, "permissions", None)
            if perms_api is None and getattr(f, "__name__", None) == "frappe":
                import importlib

                perms_api = importlib.import_module("frappe.permissions")
            if perms_api is not None:
                perms_api.setup_custom_perms(doctype)
            else:  # a runtime without that API (the offline simulator): the same copy, row by row
                for r in f.get_all("DocPerm", filters={"parent": doctype}, fields=["name"]):
                    d = f.get_doc("DocPerm", r.get("name"))
                    f.get_doc({"doctype": "Custom DocPerm", "parent": doctype, "parenttype": "DocType", "parentfield": "permissions",
                               "role": getattr(d, "role", None), "permlevel": int(getattr(d, "permlevel", 0) or 0),
                               **{k: int(getattr(d, k, 0) or 0) for k in (*RULE_FLAGS, "if_owner")}}).insert(ignore_permissions=True)
        for row in plan["clear"]:
            self._set_rule(f, row, _ZERO_RULE)
        for fieldname, level in plan["setters"]:
            f.make_property_setter({"doctype": doctype, "fieldname": fieldname, "property": "permlevel", "value": level, "property_type": "Int"})
        for (role_name, level), values in sorted(plan["target"].items()):
            existing = plan["rows"].get((role_name, level))
            if existing:
                self._set_rule(f, existing[0], values)
            else:
                f.get_doc({"doctype": "Custom DocPerm", "parent": doctype, "parenttype": "DocType", "parentfield": "permissions",
                           "role": role_name, "permlevel": level, **values}).insert(ignore_permissions=True)
        if hasattr(f, "clear_cache"):
            f.clear_cache(doctype=doctype)

    # ------------------------------------------------------------------ shadow users
    def sync_members(
        self,
        tenant_id: str,
        members_input: list[dict[str, Any]],
        mode: str,
        listed_members: dict[str, dict[str, Any]],
    ) -> None:
        """Sync non-PII shadow Users in Frappe without passwords, API keys, or welcome emails."""
        with self._site_session(tenant_id) as (f, _):
            # Sync shadow Users for every listed member (and disabled ones in full mode)
            target_refs = set(m["memberRef"] for m in members_input)
            if mode == "full":
                target_refs |= set(listed_members.keys())

            # SEC-022 (ADR-0051): every role must be an enabled adapter-owned role held under exactly its managed
            # name; anything else changes no member (unknown_role). sync_members never creates a role.
            engine_roles: dict[str, str] = {}
            for ref in sorted(target_refs):
                for r in (listed_members.get(ref) or {}).get("roleIds", []):
                    try:
                        name, disabled = self._managed_role(f, r)
                    except FrappeBackendError:
                        disabled = None
                    if disabled != 0:
                        raise FrappeBackendError("unknown_role", {"fields": ["/members/roleIds"]}, side_effect_free=True)
                    engine_roles[r] = name

            for ref in sorted(target_refs):
                rec = listed_members.get(ref)
                if rec is None:
                    continue
                email = shadow_user_email(ref)
                label = shadow_user_label(ref)
                enabled = 1 if rec["status"] == "active" else 0
                roles_payload = [{"role": engine_roles[r]} for r in rec.get("roleIds", [])]

                if hasattr(f.db, "exists") and f.db.exists("User", email):
                    u_doc = f.get_doc("User", email)
                    u_doc.update(
                        {
                            "first_name": label,
                            "enabled": enabled,
                            "send_welcome_email": 0,
                            "user_type": "Website User",
                            "roles": roles_payload,
                        }
                    )
                    u_doc.save(ignore_permissions=True)
                else:
                    u_doc = f.get_doc(
                        {
                            "doctype": "User",
                            "email": email,
                            "username": email.split("@", 1)[0],
                            "first_name": label,
                            "enabled": enabled,
                            "send_welcome_email": 0,
                            "user_type": "Website User",
                            "roles": roles_payload,
                        }
                    )
                    u_doc.insert(ignore_permissions=True)

            if hasattr(f.db, "commit"):
                f.db.commit()

    # ------------------------------------------------------------------ probes & T36 caller impersonation
    def data_probe(self, tenant_id: str, pointer: str, value: Any = None) -> Any:
        segs = [s.replace("~1", "/").replace("~0", "~") for s in pointer.split("/")[1:]]
        entity_id = segs[1] if segs[:1] == ["entities"] and len(segs) >= 2 else "entity"
        field_id = segs[3] if len(segs) >= 4 and segs[2] == "fields" else segs[-1]
        doctype = entity_to_doctype(entity_id)
        if not _SAFE_SQL_IDENT_RE.fullmatch(doctype):
            raise FrappeBackendError("invalid_request", stage="validate")
        col = _sanitize_custom_fieldname(field_id)
        table = f"tab{doctype}"

        with self._site_session(tenant_id) as (f, _):
            if value is not None:
                encoded = json.dumps(value)
                f.db.sql(
                    f"""
                    INSERT INTO `{table}` (`name`, `{col}`) VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE `{col}` = VALUES(`{col}`)
                    """,
                    ("default_row", encoded),
                )
                if hasattr(f.db, "commit"):
                    f.db.commit()
            rows = f.db.sql(f"SELECT `{col}` FROM `{table}` WHERE `name` = %s", ("default_row",))
            if not rows or rows[0][0] is None:
                return None
            raw = rows[0][0]
            try:
                return json.loads(raw)
            except Exception:
                return raw

    def auth_probe(self, tenant_id: str, member_ref: str) -> dict[str, Any]:
        email = shadow_user_email(member_ref)
        with self._site_session(tenant_id) as (f, _):
            if not (hasattr(f.db, "exists") and f.db.exists("User", email)):
                return {"exists": False, "canAuthenticate": False, "emailSent": False}

            has_password = False
            site_db = f.current_site_db() if hasattr(f, "current_site_db") else None
            if site_db is not None:
                has_password = email in site_db.auth_table
                email_sent = any(m.get("recipient") == email for m in site_db.email_queue)
            else:
                try:
                    pw_rows = f.db.sql(
                        "SELECT name FROM `__Auth` WHERE doctype = 'User' AND name = %s AND fieldname = 'password'",
                        (email,),
                    )
                    has_password = bool(pw_rows)
                except Exception:
                    has_password = False
                try:
                    eq_rows = f.db.sql("SELECT name FROM `tabEmail Queue` WHERE recipient = %s", (email,))
                    email_sent = bool(eq_rows)
                except Exception:
                    email_sent = False

            return {
                "exists": True,
                "canAuthenticate": bool(has_password),
                "emailSent": bool(email_sent),
            }

    def action_probe(self, tenant_id: str, member_ref: str) -> dict[str, Any]:
        email = shadow_user_email(member_ref)
        with self._site_session(tenant_id) as (f, _):
            if not (hasattr(f.db, "exists") and f.db.exists("User", email)):
                return {"allowed": False}
            enabled = f.db.get_value("User", email, "enabled")
            return {"allowed": bool(int(enabled or 0) == 1)}

    def resolve_frappe_user(self, tenant_id: str, caller: dict[str, Any] | None) -> str:
        """Validate T36 impersonation contract: resolve caller.onBehalfOf to an active tenant shadow User.

        Refuses missing callers, non-human agent principals on business actions, unknown users, or disabled
        users. Never falls back to Administrator or System Manager.
        """
        if not isinstance(caller, dict):
            raise FrappeBackendError("permission_denied", stage="authorize")
        who = caller.get("onBehalfOf")
        if not isinstance(who, dict) or who.get("kind") != "user" or not who.get("id"):
            raise FrappeBackendError("permission_denied", stage="authorize")

        email = shadow_user_email(str(who["id"]))
        with self._site_session(tenant_id) as (f, _):
            if not (hasattr(f.db, "exists") and f.db.exists("User", email)):
                raise FrappeBackendError("permission_denied", stage="authorize")
            enabled = f.db.get_value("User", email, "enabled")
            if int(enabled or 0) != 1:
                raise FrappeBackendError("permission_denied", stage="authorize")
        return email

    def _execute_as_caller(
        self,
        tenant_id: str,
        caller: dict[str, Any] | None,
        fn: Callable[[Any], Any],
    ) -> Any:
        """Run ``fn(frappe)`` inside tenant site with ``frappe.set_user`` bound to caller's real User (T36).

        Private: callers go through ChangeEngineAdapter.execute_action.
        """
        user_email = self.resolve_frappe_user(tenant_id, caller)
        with self._site_session(tenant_id) as (f, _):
            prev_user = getattr(getattr(f, "session", None), "user", None)
            try:
                f.set_user(user_email)
                return fn(f)
            except Exception as exc:
                perm_cls = getattr(f, "PermissionError", PermissionError)
                if isinstance(exc, (PermissionError, perm_cls)):
                    raise FrappeBackendError("permission_denied", stage="execute") from exc
                raise FrappeBackendError("engine_unavailable", stage="execute") from exc
            finally:
                if prev_user and hasattr(f, "set_user"):
                    try:
                        f.set_user(prev_user)
                    except Exception:
                        pass

    def reset_site(self, tenant_id: str | None = None) -> None:
        if self._frappe_factory is not None:
            f = self._frappe_factory()
            if hasattr(f, "sites"):
                if tenant_id is None:
                    f.sites.clear()
                    if hasattr(f, "destroy"):
                        f.destroy()
                else:
                    site_name = self.site_resolver.resolve(tenant_id)
                    f.sites.pop(site_name, None)


__all__ = [
    "COUNTRY_DEFAULTS",
    "FrappeBackendError",
    "FrappeRuntimeBackend",
    "FrappeSiteResolver",
    "shadow_user_email",
    "shadow_user_label",
]
