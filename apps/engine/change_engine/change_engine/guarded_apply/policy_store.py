"""
Change Engine Policy Persistence Store (CE-SEC-003)

Site-isolated persistence, revision tracking and audit logging for runtime policies.

Security properties:
- The site comes only from `frappe.local.site` under Frappe; a different caller-supplied site
  is refused.
- Every database read or write error raises PolicyStoreError; nothing falls back to an empty
  list, so enforcement denies instead of skipping persisted policies (fail closed).
- The tables are created by the migration patch `change_engine.patches.ce_sec_003_create_policy_tables`,
  never from a request or validate hook (DDL would commit the open transaction).
- The revision is read with SELECT ... FOR UPDATE in the same transaction as the write.
- The audit table is append-only in this code (no update or delete path). The database does
  not enforce immutability; that would need grants or triggers and is not claimed here.
"""

import copy
import datetime
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import frappe
except ImportError:
    frappe = None

from .policy_enforcer import PolicyType, RuntimePolicy, normalize_stage


def _db_datetime(value: Optional[str]) -> Optional[str]:
    """An ISO timestamp as a naive UTC 'YYYY-MM-DD HH:MM:SS.ffffff' string for a DATETIME(6) column."""
    if not value:
        return None
    parsed = datetime.datetime.fromisoformat(str(value))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return parsed.strftime("%Y-%m-%d %H:%M:%S.%f")


class PolicyStoreError(RuntimeError):
    """The policy store could not be read or written. Callers must deny, never skip."""


def _frappe_site() -> Optional[str]:
    """The request's site from Frappe (or the test double installed on the endpoints module)."""
    if frappe is not None:
        try:
            site = getattr(frappe.local, "site", None)
        except Exception:
            site = None
        if site:
            return str(site)
    try:
        from change_engine.api import endpoints
        fake = getattr(endpoints, "frappe", None)
        site = getattr(getattr(fake, "local", None), "site", None) if fake is not None else None
        if site:
            return str(site)
    except Exception:
        pass
    return None


def get_current_site_id(explicit_site: Optional[str] = None) -> str:
    """The current site. Under Frappe only `frappe.local.site` counts.

    An explicit site is accepted only in standalone tests (no Frappe site) or when it equals
    the Frappe site; anything else is refused, so one tenant cannot address another.
    """
    site = _frappe_site()
    if site:
        if explicit_site and explicit_site != site:
            raise PermissionError("Site mismatch: the site comes from the request context only")
        return site
    if frappe is not None and getattr(frappe, "db", None) is not None:
        raise PermissionError("No site in the request context")
    return explicit_site or "default"


class PolicyStore:
    """Durable per-site storage for runtime policies with revision and audit trail.

    Supports live Frappe database runtime and standalone test runtime with
    deterministic site isolation.
    """

    POLICY_TABLE = "tabChange Engine Policy"
    AUDIT_TABLE = "tabChange Engine Policy Audit"

    def __init__(self, frappe_module: Any = None):
        self._frappe = frappe_module if frappe_module is not None else frappe
        # Standalone per-site in-memory stores: site_id -> {policy_id: RuntimePolicy}
        self._sites: Dict[str, Dict[str, RuntimePolicy]] = {}
        # Standalone per-site audit journals: site_id -> [audit_record]
        self._audits: Dict[str, List[Dict[str, Any]]] = {}
        # Standalone per-site revision history: site_id -> {policy_id: [snapshot_dict]}
        self._revisions: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    @property
    def is_live_frappe(self) -> bool:
        return (
            self._frappe is not None
            and hasattr(self._frappe, "db")
            and getattr(self._frappe.db, "sql", None) is not None
        )

    def get_policy(
        self, policy_id: str, site_id: Optional[str] = None, for_update: bool = False
    ) -> Optional[RuntimePolicy]:
        """Retrieves a single policy by ID for the site. Raises PolicyStoreError on a read error."""
        site = get_current_site_id(site_id)
        if self.is_live_frappe:
            lock = " FOR UPDATE" if for_update else ""
            try:
                res = self._frappe.db.sql(
                    f"""
                    SELECT policy_id, doctype, policy_type, target_field,
                           governance_tier, condition_expr, required_role,
                           error_message, active, stage, revision,
                           created_by, created_at, updated_by, updated_at
                    FROM `{self.POLICY_TABLE}`
                    WHERE site_id = %s AND policy_id = %s
                    LIMIT 1""" + lock,
                    (site, policy_id),
                    as_dict=True,
                )
                if res and len(res) > 0:
                    row = res[0]
                    return RuntimePolicy(
                        policy_id=row["policy_id"],
                        doctype=row["doctype"],
                        policy_type=row["policy_type"],
                        target_field=row["target_field"],
                        governance_tier=int(row["governance_tier"] or 1),
                        condition_expr=row["condition_expr"],
                        required_role=row["required_role"],
                        error_message=row["error_message"] or "",
                        active=bool(row["active"]),
                        stage=row["stage"],
                        revision=int(row["revision"] or 1),
                        created_by=row.get("created_by"),
                        created_at=str(row["created_at"]) if row.get("created_at") else None,
                        updated_by=row.get("updated_by"),
                        updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
                    )
            except Exception as exc:
                raise PolicyStoreError(f"Policy read failed: {exc}") from exc
            return None

        # Standalone in-memory fallback
        site_store = self._sites.get(site, {})
        policy = site_store.get(policy_id)
        return copy.deepcopy(policy) if policy else None

    def get_policies(
        self,
        doctype: Optional[str] = None,
        stage: Optional[str] = None,
        active_only: bool = True,
        site_id: Optional[str] = None,
    ) -> List[RuntimePolicy]:
        """Retrieves policies for a site with optional doctype, stage, and active filters."""
        site = get_current_site_id(site_id)
        norm_stage = normalize_stage(stage)

        if self.is_live_frappe:
            try:
                query = f"""
                    SELECT policy_id, doctype, policy_type, target_field,
                           governance_tier, condition_expr, required_role,
                           error_message, active, stage, revision,
                           created_by, created_at, updated_by, updated_at
                    FROM `{self.POLICY_TABLE}`
                    WHERE site_id = %s
                """
                params: List[Any] = [site]
                if doctype:
                    query += " AND doctype = %s"
                    params.append(doctype)
                if active_only:
                    query += " AND active = 1"

                rows = self._frappe.db.sql(query, tuple(params), as_dict=True) or []
                policies: List[RuntimePolicy] = []
                for row in rows:
                    pol = RuntimePolicy(
                        policy_id=row["policy_id"],
                        doctype=row["doctype"],
                        policy_type=row["policy_type"],
                        target_field=row["target_field"],
                        governance_tier=int(row["governance_tier"] or 1),
                        condition_expr=row["condition_expr"],
                        required_role=row["required_role"],
                        error_message=row["error_message"] or "",
                        active=bool(row["active"]),
                        stage=row["stage"],
                        revision=int(row["revision"] or 1),
                        created_by=row.get("created_by"),
                        created_at=str(row["created_at"]) if row.get("created_at") else None,
                        updated_by=row.get("updated_by"),
                        updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
                    )
                    from .policy_enforcer import is_policy_applicable_to_stage
                    if not stage or is_policy_applicable_to_stage(pol, norm_stage):
                        policies.append(pol)
                return policies
            except Exception as exc:
                raise PolicyStoreError(f"Policy read failed: {exc}") from exc

        # Standalone in-memory fallback
        site_store = self._sites.get(site, {})
        from .policy_enforcer import is_policy_applicable_to_stage
        matched = []
        for pol in site_store.values():
            if doctype and pol.doctype != doctype:
                continue
            if active_only and not pol.active:
                continue
            if stage and not is_policy_applicable_to_stage(pol, norm_stage):
                continue
            matched.append(copy.deepcopy(pol))
        return matched

    def save_policy(
        self,
        policy: RuntimePolicy,
        actor: str = "System",
        site_id: Optional[str] = None,
    ) -> Tuple[RuntimePolicy, Dict[str, Any]]:
        """Saves (creates or updates) a policy for the site, incrementing revision and logging audit."""
        if policy.policy_id.upper().startswith("TIER0_") or policy.governance_tier != 1:
            raise PermissionError("Only Tier 1 policies are stored; Tier 0 invariants are built in")
        site = get_current_site_id(site_id)
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now_dt.isoformat()

        # Locks the row (live database) so two writers cannot both compute the same revision.
        existing = self.get_policy(policy.policy_id, site_id=site, for_update=True)
        payload_before = existing.to_dict() if existing else None

        if existing:
            revision = (existing.revision or 1) + 1
            created_at = existing.created_at or now_iso
            created_by = existing.created_by or actor
            action = "DEACTIVATED" if (existing.active and not policy.active) else "UPDATED"
        else:
            revision = 1
            created_at = now_iso
            created_by = actor
            action = "CREATED"

        saved_policy = RuntimePolicy(
            policy_id=policy.policy_id,
            doctype=policy.doctype,
            policy_type=policy.policy_type,
            target_field=policy.target_field,
            governance_tier=policy.governance_tier,
            condition_expr=policy.condition_expr,
            required_role=policy.required_role,
            error_message=policy.error_message,
            active=policy.active,
            stage=policy.stage,
            revision=revision,
            created_by=created_by,
            created_at=created_at,
            updated_by=actor,
            updated_at=now_iso,
        )

        audit_id = f"aud_pol_{uuid.uuid4().hex[:12]}"
        audit_record = {
            "audit_id": audit_id,
            "site_id": site,
            "policy_id": saved_policy.policy_id,
            "doctype": saved_policy.doctype,
            "revision": revision,
            "action": action,
            "changed_by": actor,
            "payload_before": payload_before,
            "payload_after": saved_policy.to_dict(),
            "timestamp": now_iso,
        }

        if self.is_live_frappe:
            name = f"{site}::{saved_policy.policy_id}"
            try:
                self._frappe.db.sql(
                    f"""
                    INSERT INTO `{self.POLICY_TABLE}` (
                        name, policy_id, site_id, doctype, policy_type,
                        target_field, governance_tier, condition_expr,
                        required_role, error_message, stage, active, revision,
                        created_by, created_at, updated_by, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    ON DUPLICATE KEY UPDATE
                        doctype = VALUES(doctype),
                        policy_type = VALUES(policy_type),
                        target_field = VALUES(target_field),
                        governance_tier = VALUES(governance_tier),
                        condition_expr = VALUES(condition_expr),
                        required_role = VALUES(required_role),
                        error_message = VALUES(error_message),
                        stage = VALUES(stage),
                        active = VALUES(active),
                        revision = VALUES(revision),
                        updated_by = VALUES(updated_by),
                        updated_at = VALUES(updated_at)
                    """,
                    (
                        name,
                        saved_policy.policy_id,
                        site,
                        saved_policy.doctype,
                        saved_policy.policy_type,
                        saved_policy.target_field,
                        saved_policy.governance_tier,
                        saved_policy.condition_expr,
                        saved_policy.required_role,
                        saved_policy.error_message,
                        saved_policy.stage,
                        1 if saved_policy.active else 0,
                        saved_policy.revision,
                        saved_policy.created_by,
                        _db_datetime(saved_policy.created_at),
                        saved_policy.updated_by,
                        _db_datetime(saved_policy.updated_at),
                    ),
                )
                audit_name = f"{site}::{audit_id}"
                self._frappe.db.sql(
                    f"""
                    INSERT INTO `{self.AUDIT_TABLE}` (
                        name, audit_id, site_id, policy_id, doctype, revision,
                        action, changed_by, payload_before, payload_after, timestamp
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        audit_name,
                        audit_id,
                        site,
                        saved_policy.policy_id,
                        saved_policy.doctype,
                        revision,
                        action,
                        actor,
                        json.dumps(payload_before) if payload_before else None,
                        json.dumps(saved_policy.to_dict()),
                        now_dt.strftime("%Y-%m-%d %H:%M:%S.%f"),
                    ),
                )
            except Exception as e:
                raise PolicyStoreError(f"Database policy persistence failed: {e}") from e
            return saved_policy, audit_record

        # Standalone in-memory fallback
        site_store = self._sites.setdefault(site, {})
        site_store[saved_policy.policy_id] = copy.deepcopy(saved_policy)

        audits = self._audits.setdefault(site, [])
        audits.append(audit_record)

        rev_hist = self._revisions.setdefault(site, {}).setdefault(saved_policy.policy_id, [])
        rev_hist.append(saved_policy.to_dict())

        return saved_policy, audit_record

    def delete_policy(
        self,
        policy_id: str,
        actor: str = "System",
        site_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Deletes a policy from site storage and records an audit record."""
        site = get_current_site_id(site_id)
        existing = self.get_policy(policy_id, site_id=site, for_update=True)
        if not existing:
            return None

        now_dt = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now_dt.isoformat()
        audit_id = f"aud_pol_{uuid.uuid4().hex[:12]}"
        audit_record = {
            "audit_id": audit_id,
            "site_id": site,
            "policy_id": policy_id,
            "doctype": existing.doctype,
            "revision": existing.revision,
            "action": "DELETED",
            "changed_by": actor,
            "payload_before": existing.to_dict(),
            "payload_after": None,
            "timestamp": now_iso,
        }

        if self.is_live_frappe:
            try:
                self._frappe.db.sql(
                    f"DELETE FROM `{self.POLICY_TABLE}` WHERE site_id = %s AND policy_id = %s",
                    (site, policy_id),
                )
                audit_name = f"{site}::{audit_id}"
                self._frappe.db.sql(
                    f"""
                    INSERT INTO `{self.AUDIT_TABLE}` (
                        name, audit_id, site_id, policy_id, doctype, revision,
                        action, changed_by, payload_before, payload_after, timestamp
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        audit_name,
                        audit_id,
                        site,
                        policy_id,
                        existing.doctype,
                        existing.revision,
                        "DELETED",
                        actor,
                        json.dumps(existing.to_dict()),
                        None,
                        now_dt.strftime("%Y-%m-%d %H:%M:%S.%f"),
                    ),
                )
            except Exception as e:
                raise PolicyStoreError(f"Database policy deletion failed: {e}") from e
            return audit_record

        # Standalone in-memory fallback
        site_store = self._sites.get(site, {})
        site_store.pop(policy_id, None)

        audits = self._audits.setdefault(site, [])
        audits.append(audit_record)

        rev_hist = self._revisions.setdefault(site, {}).setdefault(policy_id, [])
        deleted_marker = copy.deepcopy(existing.to_dict())
        deleted_marker["deleted"] = True
        rev_hist.append(deleted_marker)

        return audit_record

    def get_audit_trail(
        self,
        policy_id: Optional[str] = None,
        doctype: Optional[str] = None,
        site_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Returns the audit trail for policies on a site."""
        site = get_current_site_id(site_id)
        if self.is_live_frappe:
            try:
                query = f"""
                    SELECT audit_id, site_id, policy_id, doctype, revision,
                           action, changed_by, payload_before, payload_after, timestamp
                    FROM `{self.AUDIT_TABLE}`
                    WHERE site_id = %s
                """
                params: List[Any] = [site]
                if policy_id:
                    query += " AND policy_id = %s"
                    params.append(policy_id)
                if doctype:
                    query += " AND doctype = %s"
                    params.append(doctype)
                query += " ORDER BY timestamp ASC"

                rows = self._frappe.db.sql(query, tuple(params), as_dict=True) or []
                res = []
                for r in rows:
                    rec = dict(r)
                    if isinstance(rec.get("payload_before"), str):
                        try:
                            rec["payload_before"] = json.loads(rec["payload_before"])
                        except Exception:
                            pass
                    if isinstance(rec.get("payload_after"), str):
                        try:
                            rec["payload_after"] = json.loads(rec["payload_after"])
                        except Exception:
                            pass
                    rec["timestamp"] = str(rec["timestamp"])
                    res.append(rec)
                return res
            except Exception as exc:
                raise PolicyStoreError(f"Audit read failed: {exc}") from exc

        site_audits = self._audits.get(site, [])
        matched = []
        for a in site_audits:
            if policy_id and a["policy_id"] != policy_id:
                continue
            if doctype and a["doctype"] != doctype:
                continue
            matched.append(copy.deepcopy(a))
        return matched

    def get_policy_revisions(self, policy_id: str, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns the historical revisions of a policy."""
        site = get_current_site_id(site_id)
        audits = self.get_audit_trail(policy_id=policy_id, site_id=site)
        revisions = []
        for a in audits:
            if a.get("payload_after"):
                revisions.append(a["payload_after"])
        return revisions

    def reset_store(self, site_id: Optional[str] = None) -> None:
        """Resets in-memory storage (used in test fixtures)."""
        if site_id:
            self._sites.pop(site_id, None)
            self._audits.pop(site_id, None)
            self._revisions.pop(site_id, None)
        else:
            self._sites.clear()
            self._audits.clear()
            self._revisions.clear()


# Default singleton instance
policy_store = PolicyStore()
