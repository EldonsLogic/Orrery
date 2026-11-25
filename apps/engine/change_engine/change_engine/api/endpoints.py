"""
Change engine Whitelisted API Endpoints & Document Lifecycle Hooks
Implements supported Frappe REST and Desk RPC interfaces for the AI Control Plane.
"""

import hashlib
import hmac
import logging
import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Safe imports for standalone execution or Frappe runtime
try:
    import frappe
    from frappe import _
except ImportError:
    frappe = None

logger = logging.getLogger(__name__)

from change_engine.guarded_apply.schema_extractor import get_compact_doctype_schema
from change_engine.guarded_apply.safety_guardrails import (
    TIER_1_GOVERNANCE_ROLES,
    validate_mutation_safety,
    ZoneSafetyViolation,
)
from change_engine.guarded_apply.ddl_plan_gate import (
    ColumnDesc,
    DDLPlanInspection,
    MARIADB_TYPE_MAP,
    assess_applied_ddl,
    inspect_frappe_ddl_plan,
    SCHEMA_COLUMN_ATTRS,
    requires_ddl_check,
    ddl_batch_rejection,
    new_column_matches_plan,
)
from change_engine.guarded_apply.schema_reconciler import (
    DeploymentIntentConflictError,  # CE-SEC-008 (defined in schema_reconciler; re-exported here)
    DurableEvidenceError,
    ExhaustiveSnapshot,
    IdempotencyConflictError,
    InvalidDeploymentIdError,
    LockTimeoutError,
    MAX_IDEMPOTENCY_KEY_LENGTH,
    SessionDiscardedError,
    MAX_SITE_ID_LENGTH,
    caller_id_problem,
    evidence_namespace_problem,
    RevisionHashError,  # defined in schema_reconciler (shared with property_setter_engine); re-exported here
    Rev23DeploymentAdapter,
    compute_canonical_payload_hash,
    execute_single_field_deployment,
    make_bounded_lock_key,
)
from change_engine.guarded_apply.policy_enforcer import (
    PolicyType,
    RuntimePolicy,
    PolicyEvaluationResult,
    RuntimePolicyViolation,
    RuntimePolicyCatalog,
    policy_catalog,
)

from change_engine.guarded_apply.property_setter_engine import execute_property_setter_deployment
from change_engine.guarded_apply.rollback_engine import AUTHORIZED_ROLLBACK_ROLES, execute_rollback
from change_engine.guarded_apply.workflow_engine import (
    WorkflowDefinition,
    WorkflowStateModel,
    WorkflowTransitionModel,
    validate_workflow_state_machine,
    execute_workflow_deployment,
)
from change_engine.guarded_apply.report_engine import (
    ReportColumn,
    ReportFilter,
    ReportChartConfig,
    ReportDefinition,
    ReportValidationResult,
    validate_report_definition,
    get_report_preview_data,
    execute_report_deployment,
    AUTHORIZED_REPORT_ROLES,
)
from change_engine.guarded_apply.cross_doc_policy import (
    CrossDocPolicy,
    CrossDocPolicyCatalog,
    cross_doc_catalog,
)

AUTHORIZED_DEPLOYMENT_ROLES: Set[str] = {
    "System Manager",
    "Finance Director",
    "Operations Director",
}

AUTHORIZED_REPORT_DEPLOYMENT_ROLES: Set[str] = {
    "System Manager",
    "Finance Director",
    "Operations Director",
    "Sales Manager",
}


# Roles used when running outside Frappe (unit tests only). Empty by default: fail closed.
_STANDALONE_DEFAULT_ROLES: List[str] = []


def get_current_user_roles() -> list:
    """Roles of the authenticated Frappe user. Fails closed (no roles) on any error."""
    if frappe is not None and hasattr(frappe, "session") and getattr(frappe.session, "user", None):
        try:
            return list(frappe.get_roles(frappe.session.user))
        except Exception:
            return []
    return list(_STANDALONE_DEFAULT_ROLES)


def _resolve_caller_roles(kwargs: Optional[Dict[str, Any]] = None) -> list:
    """Caller roles for authorisation decisions.

    Inside Frappe the roles come ONLY from the authenticated session; any
    client-supplied `user_roles` / `caller_roles` is ignored (CE-SEC-001).
    Outside Frappe (unit tests) explicit roles are honoured. A Frappe context without a
    session user resolves to no roles, never to the caller's (CE-SEC-002).
    """
    if _in_frappe_request():
        return get_current_user_roles()
    kwargs = kwargs or {}
    explicit = kwargs.get("user_roles")
    if explicit is None:
        explicit = kwargs.get("caller_roles")
    if explicit is not None:
        return list(explicit)
    return get_current_user_roles()


# Request parameters a caller may never set on the policy endpoints (CE-SEC-003): the site,
# the roles and the actor come from the Frappe request context, the tier from the platform.
_FORBIDDEN_POLICY_PARAMS = ("site_id", "site", "user_roles", "caller_roles", "actor", "governance_tier")
# Policy fields a caller may set when registering a policy.
_REGISTRABLE_POLICY_FIELDS = (
    "policy_id", "doctype", "policy_type", "target_field", "condition_expr",
    "required_role", "error_message", "active", "stage",
)


def _in_frappe_request() -> bool:
    """True inside a Frappe runtime: a session user or a request site exists.

    Detected independently of the session, so a Frappe context with a missing or malformed
    session is still treated as Frappe (no roles, caller context refused), never as standalone.
    """
    if frappe is None:
        return False
    try:
        if getattr(getattr(frappe, "session", None), "user", None):
            return True
        return bool(getattr(getattr(frappe, "local", None), "site", None))
    except Exception:
        return True  # an unreadable Frappe context is treated as Frappe, with no identity


def _reject_caller_context(kwargs: Optional[Dict[str, Any]]) -> None:
    """Inside Frappe, refuse any caller-supplied site, roles, actor or tier (CE-SEC-003)."""
    if not _in_frappe_request():
        return  # standalone unit tests: no HTTP surface
    supplied = [k for k in _FORBIDDEN_POLICY_PARAMS if k in (kwargs or {})]
    if supplied:
        raise PermissionError(f"Not permitted: {', '.join(supplied)} cannot be supplied by the caller")


def _policy_caller_roles(kwargs: Optional[Dict[str, Any]]) -> list:
    """Session roles inside Frappe; explicit roles only in standalone unit tests."""
    if _in_frappe_request():
        return get_current_user_roles()
    return _resolve_caller_roles(kwargs)


def _require_authorized_caller(kwargs: Optional[Dict[str, Any]] = None) -> None:
    """Reject non-authorised callers on read endpoints (CE-SEC-003)."""
    _reject_caller_context(kwargs)
    if _in_frappe_request():
        roles = get_current_user_roles()
    elif kwargs and "caller_roles" in kwargs:
        roles = list(kwargs["caller_roles"])  # standalone unit tests only
    else:
        return  # standalone unit tests with no caller identity: no HTTP surface
    if not set(roles).intersection(AUTHORIZED_DEPLOYMENT_ROLES):
        raise PermissionError("Not permitted")


def _require_admin_caller(kwargs: Optional[Dict[str, Any]] = None) -> None:
    """Reject non-admin callers on policy registration and removal (CE-SEC-003). Fails closed."""
    _reject_caller_context(kwargs)
    if not set(_policy_caller_roles(kwargs)).intersection(AUTHORIZED_DEPLOYMENT_ROLES):
        raise PermissionError("Not permitted: admin permission required to register or modify runtime policies")


def _policy_actor(kwargs: Optional[Dict[str, Any]]) -> str:
    if _in_frappe_request():
        return str(getattr(getattr(frappe, "session", None), "user", None) or "Guest")
    return str((kwargs or {}).get("actor") or "System")


def _policy_from_request(policy_data: Union[str, Dict[str, Any], RuntimePolicy]) -> RuntimePolicy:
    """Build a Tier 1 policy from caller data, accepting only the registrable fields."""
    if isinstance(policy_data, RuntimePolicy):
        policy_data = {k: getattr(policy_data, k) for k in _REGISTRABLE_POLICY_FIELDS} | (
            {"governance_tier": policy_data.governance_tier} if policy_data.governance_tier != 1 else {}
        )
    if isinstance(policy_data, str):
        policy_data = json.loads(policy_data)
    if not isinstance(policy_data, dict):
        raise ValueError("policy_data must be an object")
    unknown = sorted(set(policy_data) - set(_REGISTRABLE_POLICY_FIELDS))
    if unknown:
        raise PermissionError(f"Not permitted: fields {', '.join(unknown)} cannot be set by the caller")
    return RuntimePolicy(**policy_data, governance_tier=1)



def propose_configuration_change(
    doctype: str,
    proposal_payload: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Whitelisted RPC method: validates a structured proposal against the guardrails and
    returns DDL plan evidence. Does NOT execute physical DDL or write to production tables.
    Natural-language planning lives outside the engine (AI services), never here.
    """
    if isinstance(proposal_payload, str):
        try:
            proposal_payload = json.loads(proposal_payload)
        except Exception:
            proposal_payload = None

    user_roles = _resolve_caller_roles(kwargs)

    # Raw proposal_payload execution flow
    if proposal_payload is None:
        proposal_payload = {}

    proposal_payload["target_doctype"] = doctype
    intent = proposal_payload.get("intent")
    if intent in ("create_workflow", "workflow_action", "workflow"):
        wf_data = proposal_payload.get("workflow_def") or proposal_payload.get("workflow") or proposal_payload
        if isinstance(wf_data, dict):
            wf_data = dict(wf_data)
            if "document_type" not in wf_data or not wf_data["document_type"]:
                wf_data["document_type"] = doctype
        val_result = validate_workflow_state_machine(wf_data, existing_roles=user_roles)
        return {
            "status": "PROPOSED" if val_result.is_valid else "REJECTED",
            "success": val_result.is_valid,
            "proposal": proposal_payload,
            "validation": {
                "is_valid": val_result.is_valid,
                "errors": val_result.errors,
                "warnings": val_result.warnings,
            },
            "mermaid_graph": val_result.mermaid_graph,
            "preview_fidelity_notice": (
                "Workflow state machine previewed with Mermaid diagram. "
                "Document transitions and permissions execute on active ERPNext records."
            ),
        }

    if intent in ("create_report", "report", "report_builder"):
        rep_data = proposal_payload.get("report_def") or proposal_payload.get("report") or proposal_payload
        if isinstance(rep_data, dict):
            rep_data = dict(rep_data)
            if "ref_doctype" not in rep_data or not rep_data["ref_doctype"]:
                rep_data["ref_doctype"] = doctype
            if "report_name" not in rep_data or not rep_data["report_name"]:
                rep_data["report_name"] = f"{doctype} Custom Report"
        adapter = kwargs.get("adapter") or kwargs.get("db")
        val_result = validate_report_definition(rep_data, db=adapter)
        preview_data = None
        if val_result.is_valid:
            preview_data = get_report_preview_data(rep_data, db=adapter)
            val_result.preview_data = preview_data

        return {
            "status": "PROPOSED" if val_result.is_valid else "REJECTED",
            "success": val_result.is_valid,
            "proposal": proposal_payload,
            "validation": {
                "is_valid": val_result.is_valid,
                "errors": val_result.errors,
                "warnings": val_result.warnings,
                "preview_data": preview_data,
            },
            "preview_data": preview_data,
            "preview_fidelity_notice": (
                "Report Builder configuration previewed with sample query results. "
                "Production data and role-based permissions apply when viewing in Desk."
            ),
        }

    # Step 1: Policy & Invariant Evaluation
    try:
        validation_result = validate_mutation_safety(proposal_payload)
    except ZoneSafetyViolation as exc:
        return {
            "status": "REJECTED",
            "success": False,
            "stage": "SAFETY_GUARDRAILS",
            "disposition": "ZONE_SAFETY_VIOLATION",
            "reason": str(exc),
            "proposal": proposal_payload,
            "ddl_plan": None,
        }

    # Step 2: DDL Plan Gate Inspection (Zero DDL executed)
    adapter = kwargs.get("adapter") or kwargs.get("db")
    if adapter is None and frappe is not None:
        # Frappe is importable: always the live adapter, even when frappe.db is missing or
        # disconnected. The gate then rejects (DDL_GATE_FRAPPE_UNAVAILABLE) instead of
        # silently falling back to the column-blind simulator (ERP-027 re-review H2).
        adapter = FrappeDeploymentAdapter()

    changes = proposal_payload.get("changes", [])
    ddl_plan_result = None
    existing_cols = (
        adapter.get_table_columns_description(doctype)
        if adapter is not None and hasattr(adapter, "get_table_columns_description")
        else None
    )
    try:
        base_revision_hash = (
            adapter.get_doctype_revision_hash(doctype)
            if adapter is not None and hasattr(adapter, "get_doctype_revision_hash")
            else "rev_default"
        )
    except RevisionHashError as exc:
        logger.error("DocType revision hash unreadable for %s", doctype, exc_info=exc)
        return {
            "status": "REJECTED",
            "success": False,
            "stage": "INSPECT",
            "disposition": "REVISION_HASH_UNAVAILABLE",
            "reason_code": "revision_unavailable",
            "reason": "Cannot read the DocType configuration revision.",
            "proposal": proposal_payload,
            "ddl_plan": None,
        }

    if proposal_payload.get("intent") == "add_custom_fields" and changes:
        all_statements: List[str] = []
        per_field: List[Dict[str, Any]] = []
        all_inspectable = True
        all_approved = True
        rejection_reasons: List[str] = []
        for field_def in changes:
            ddl_plan = inspect_frappe_ddl_plan(
                doctype,
                field_def,
                existing_columns_desc=existing_cols,
                # Simulator only when nothing live can exist (frappe not importable, so
                # adapter is None) or a test adapter explicitly asks for it.
                offline_simulator=adapter is None
                or bool(getattr(adapter, "in_memory", False) or getattr(adapter, "offline_ddl_simulator", False)),
            )
            all_statements.extend(ddl_plan.statements)
            per_field.append(
                {
                    "fieldname": field_def.get("fieldname"),
                    "inspectable": ddl_plan.inspectable,
                    "statements": ddl_plan.statements,
                    "is_approved_additive_only": ddl_plan.is_approved_additive_only,
                    "rejection_reason": ddl_plan.rejection_reason,
                }
            )
            if not ddl_plan.inspectable:
                all_inspectable = False
            if not ddl_plan.is_approved_additive_only:
                all_approved = False
                if ddl_plan.rejection_reason:
                    rejection_reasons.append(ddl_plan.rejection_reason)
        ddl_plan_result = {
            "inspectable": all_inspectable,
            "statements": all_statements,
            "is_approved_additive_only": all_approved,
            "rejection_reason": "; ".join(rejection_reasons) if rejection_reasons else None,
        }
        if len(per_field) > 1:
            ddl_plan_result["per_field"] = per_field
    elif proposal_payload.get("intent") in ("set_property", "quarantine_custom_field", "update_field_property", "property_setter"):
        ddl_plan_result = {
            "inspectable": True,
            "statements": ["-- Zero DDL (Metadata Mutation via Property Setter / Soft Quarantine) --"],
            "is_approved_additive_only": True,
            "rejection_reason": None,
        }

    preview_payload = {
        "doctype": doctype,
        "intent": intent,
        "base_revision_hash": base_revision_hash,
        "changes": changes,
        "statements": ddl_plan_result["statements"] if ddl_plan_result else [],
    }
    preview_digest = hashlib.sha256(
        json.dumps(preview_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    ddl_approved = (
        True
        if ddl_plan_result is None
        else bool(ddl_plan_result.get("inspectable") and ddl_plan_result.get("is_approved_additive_only"))
    )

    resp: Dict[str, Any] = {
        "status": "PROPOSED" if ddl_approved else "REJECTED",
        "success": ddl_approved,
        "proposal": proposal_payload,
        "validation": validation_result,
        "ddl_plan": ddl_plan_result,
        "preview_digest": preview_digest,
        "base_revision_hash": base_revision_hash,
        "preview": {
            "doctype": doctype,
            "intent": intent,
            "base_revision_hash": base_revision_hash,
            "preview_digest": preview_digest,
            "ddl_gate_passed": ddl_approved,
            "statements": preview_payload["statements"],
        },
        "preview_fidelity_notice": (
            "Layout, labels, and field controls previewed. "
            "ERPNext tax/pricing recalculations and server validations execute on real documents."
        ),
    }
    if not ddl_approved and ddl_plan_result is not None:
        resp["stage"] = "INSPECT"
        resp["disposition"] = "DDL_PLAN_REJECTED"
        resp["fallback_action"] = "QUEUE_FOR_CONTROLLED_ADMIN_DEPLOYMENT"
        resp["reason"] = ddl_plan_result.get("rejection_reason") or "DDL plan gate rejected proposal."
    return resp


# Frappe whitelisted decorator when running inside Frappe
if frappe and hasattr(frappe, "whitelist"):
    propose_configuration_change = frappe.whitelist()(propose_configuration_change)


_LOCK_SENTINEL = object()

# Ceiling for the DDL lock wait, refused beyond it before any SQL. An ALTER that waits for a metadata lock
# queues every later query on that table behind it, so any wait longer than a minute is a visible outage; the
# callers use 3 to 5 seconds. (MariaDB itself allows a year.)
_MAX_LOCK_WAIT_SECONDS = 60

# CE-SEC-008: durable deployment evidence lives in the existing audit table as append-only rows that
# share the evidence key ``<deployment_id>#evidence`` (so the idempotency lookup, which needs an outcome,
# and the recovery lookup, which needs PREPARED or RECOVERY_REQUIRED, never see them). Intent rows say
# what is about to happen; the deployment's completion truth is only the main row's final status and
# outcome written at Stage 6.
_EVIDENCE_BASELINE = "EVIDENCE_BASELINE"
_EVIDENCE_DISPATCH = "EVIDENCE_DDL_DISPATCH"
_EVIDENCE_COMPLETED = "EVIDENCE_DDL_COMPLETED"
_EVIDENCE_KINDS = {
    _EVIDENCE_BASELINE: "baseline",
    _EVIDENCE_DISPATCH: "dispatch_intent",
    _EVIDENCE_COMPLETED: "dispatch_completed",
}


# The audit table's leading columns, in declared order (``_ensure_audit_table``).
_AUDIT_ROW_COLUMNS = (
    "name", "deployment_id", "idempotency_key", "payload_hash", "site_id", "doctype", "fieldname",
    "base_revision_hash", "ddl_plan_statements", "status", "outcome_json",
)


# Every lookup and finalizer on the audit table is restricted to main rows with this predicate.
_MAIN_ROWS_ONLY = "status NOT IN ('EVIDENCE_BASELINE', 'EVIDENCE_DDL_DISPATCH', 'EVIDENCE_DDL_COMPLETED')"


def _require_main_row_id(deployment_id: Any) -> None:
    """Finalizers and lookups work on any existing main row (older ids may be longer or looser than a new
    deployment's), but never on a name inside the evidence namespace."""
    problem = evidence_namespace_problem(deployment_id)
    if problem:
        raise InvalidDeploymentIdError(f"deployment id {problem}")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _bind_digest(deployment_id: str, site_id: str, doctype: str, fieldname: str, payload_hash: str,
                 statements: List[str], baseline_blob: Any) -> str:
    """SHA-256 binding the approved plan and the baseline schema to the deployment's identity. It is stored in
    the main row's plan column, so editing the baseline, the plan or the identity (or deleting the baseline) is
    detected on load. UNKEYED: someone who can write the table AND recomputes it is not detected (a keyed MAC
    needs key management, CE-SEC-010); and truncating the journal's tail is not detected either."""
    return hashlib.sha256(_canonical_json({
        "v": 1, "deployment_id": deployment_id, "site_id": site_id, "doctype": doctype, "fieldname": fieldname,
        "payload_hash": payload_hash, "statements": list(statements), "baseline": baseline_blob,
    }).encode("utf-8")).hexdigest()


def _row_digest(main_digest: str, kind: str, seq: int, statement: str) -> str:
    """Binds one journal row to the main row's digest, its kind, its position and its statement."""
    return hashlib.sha256(_canonical_json(
        {"v": 1, "main": main_digest, "kind": kind, "seq": seq, "statement": statement}).encode("utf-8")).hexdigest()


def _stored_statements(blob: Any) -> List[str]:
    """The approved statements from a main row's plan column: a plain JSON list (non-DDL rows) or the envelope
    ``{"statements": [...], "evidence_sha256": ...}`` that physical-DDL rows carry."""
    try:
        data = json.loads(blob or "null")
    except ValueError as exc:
        raise DurableEvidenceError("stored approved plan is not valid JSON") from exc
    statements = data.get("statements") if isinstance(data, dict) else data
    if not isinstance(statements, list) or not all(isinstance(x, str) for x in statements):
        raise DurableEvidenceError("stored approved plan is not a list of statements")
    return statements


def _evidence_key(deployment_id: str) -> str:
    return f"{deployment_id}#evidence"


def _encode_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """JSON form of the whole-table fingerprint (sets and tuples become sorted lists)."""
    return {
        "columns": schema["columns"],
        "order": list(schema["order"]),
        "indexes": sorted(list(t) for t in schema["indexes"]),
        "constraints": sorted(list(t) for t in schema["constraints"]),
        "checks": sorted(list(t) for t in schema["checks"]),
        "triggers": sorted(list(t) for t in schema["triggers"]),
        "table": list(schema["table"]),
    }


def _decode_schema(blob: Any) -> Dict[str, Any]:
    """Inverse of ``_encode_schema``; anything that is not a complete fingerprint raises."""
    try:
        schema = {
            "columns": {str(k): {str(a): str(b) for a, b in v.items()} for k, v in blob["columns"].items()},
            "order": [str(x) for x in blob["order"]],
            "indexes": {tuple(str(x) for x in r) for r in blob["indexes"]},
            "constraints": {tuple(str(x) for x in r) for r in blob["constraints"]},
            "checks": {tuple(str(x) for x in r) for r in blob["checks"]},
            "triggers": {tuple(str(x) for x in r) for r in blob["triggers"]},
            "table": tuple(str(x) for x in blob["table"]),
        }
    except Exception as exc:
        raise DurableEvidenceError(f"stored baseline schema is malformed ({type(exc).__name__})") from exc
    if any(a not in d for d in schema["columns"].values() for a in SCHEMA_COLUMN_ATTRS):
        raise DurableEvidenceError("stored baseline schema is incomplete")
    return schema


class FrappeDeploymentAdapter:
    """
    ADR-001 Rev 2.3 Deployment Adapter for Frappe Framework (v15 LTS) & MariaDB (10.11 LTS).
    Implements Rev23DeploymentAdapter protocol.

    - Live Frappe runtime:
      Uses frappe.db.sql for GET_LOCK, RELEASE_LOCK, SET SESSION lock_wait_timeout,
      and schema reflection on information_schema.COLUMNS and tabCustom Field.
      Durably persists deployment and audit journal to tabChange Engine Audit.
      Inserts Custom Field documents natively via frappe.get_doc({...}).insert().
    - Standalone / Unit-Test runtime:
      Provides an in-memory, mockable implementation with deterministic state management,
      failure injection, and snapshot validation without requiring an active database or bench.
    """

    _shared_locks: Set[str] = set()
    _shared_audit_journal: Dict[str, Dict[str, Any]] = {}
    _shared_idempotency_store: Dict[Tuple[str, str], Dict[str, Any]] = {}
    _shared_custom_fields: Dict[Tuple[str, str], Dict[str, Any]] = {}
    _shared_property_setters: Dict[Tuple[str, Optional[str], str], Dict[str, Any]] = {}
    _shared_table_columns: Dict[str, List[ColumnDesc]] = {}
    _shared_revision_hashes: Dict[str, str] = {}
    _shared_workflows: Dict[str, Dict[str, Any]] = {}
    _shared_workflow_states: Dict[str, Dict[str, Any]] = {}
    _shared_reports: Dict[str, Dict[str, Any]] = {}
    _shared_documents: Dict[Tuple[str, str], Dict[str, Any]] = {}

    @classmethod
    def reset_in_memory_state(cls) -> None:
        """Resets all shared in-memory state between unit test runs."""
        cls._shared_locks.clear()
        cls._shared_audit_journal.clear()
        cls._shared_idempotency_store.clear()
        cls._shared_custom_fields.clear()
        cls._shared_property_setters.clear()
        cls._shared_table_columns.clear()
        cls._shared_revision_hashes.clear()
        cls._shared_workflows.clear()
        cls._shared_workflow_states.clear()
        cls._shared_reports.clear()
        cls._shared_documents.clear()

    def __init__(
        self,
        frappe_module: Any = None,
        in_memory: Optional[bool] = None,
        audit_table: str = "tabChange Engine Audit",
        lock_return: Any = _LOCK_SENTINEL,
        target_in_recovery: bool = False,
        before_snapshot: Optional[ExhaustiveSnapshot] = None,
        after_snapshot: Optional[ExhaustiveSnapshot] = None,
        ddl_plan: Optional[DDLPlanInspection] = None,
        existing_columns_desc: Optional[List[ColumnDesc]] = None,
        doctype_fields: Optional[List[Dict[str, Any]]] = None,
        simulate_prepare_error: bool = False,
        simulate_apply_error: bool = False,
        simulate_finalize_error: bool = False,
        use_shared_state: bool = True,
        offline_ddl_simulator: bool = False,
    ):
        # Explicit test/offline mode for the DDL plan gate (simulator instead of Frappe's own
        # MariaDBTable; no real DDL runs). Never set on a live bench (ERP-027 H2).
        self.offline_ddl_simulator = offline_ddl_simulator
        self._frappe = frappe_module if frappe_module is not None else frappe
        self.audit_table = audit_table
        self.lock_return = lock_return
        self.target_in_recovery = target_in_recovery
        self.before_snapshot_override = before_snapshot
        self.after_snapshot_override = after_snapshot
        self.ddl_plan_override = ddl_plan
        self.existing_columns_desc_override = existing_columns_desc
        self.doctype_fields_override = doctype_fields
        self.simulate_prepare_error = simulate_prepare_error
        self.simulate_apply_error = simulate_apply_error
        self.simulate_finalize_error = simulate_finalize_error
        self.use_shared_state = use_shared_state

        if in_memory is not None:
            self.in_memory = in_memory
        else:
            # In-memory only when Frappe cannot be imported at all. A Frappe runtime with a
            # missing or disconnected frappe.db is still LIVE and fails closed (ERP-027
            # re-review H2); tests that want the in-memory store pass in_memory=True.
            self.in_memory = self._frappe is None

        self.apply_called: bool = False
        self._request_site: Optional[str] = None
        self._previous_lock_wait_timeout: Optional[int] = None
        self._session_unusable = False
        self._discard_confirmed = False  # True only once the connection is really closed
        self._held_locks: Set[str] = set()
        # ERP-027: applied state per deployment (an adapter may be reused for several).
        self._applied_deployments: Set[str] = set()
        # ERP-027: approved plan vs what Frappe actually executed (live mode only).
        # CE-SEC-008: ``_dispatched_ddl`` is the intent (admitted and journalled durably just before it is
        # sent); ``_executed_ddl`` is what returned successfully, appended only after it took effect.
        self._approved_ddl: Dict[str, List[str]] = {}
        self._dispatched_ddl: Dict[str, List[str]] = {}
        self._executed_ddl: Dict[str, List[str]] = {}
        self._intent_context: Dict[str, Dict[str, Any]] = {}
        self._before_schema: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.cache_cleared: bool = False
        self.prepared_records: List[Dict[str, Any]] = []
        self.lock_wait_timeout_seconds: Optional[int] = None

        if self.use_shared_state:
            self.locks = self._shared_locks
            self.audit_journal = self._shared_audit_journal
            self.idempotency_store = self._shared_idempotency_store
            self.custom_fields = self._shared_custom_fields
            self.property_setters = self._shared_property_setters
            self.table_columns = self._shared_table_columns
            self.revision_hashes = self._shared_revision_hashes
            self.workflows = self._shared_workflows
            self.workflow_states = self._shared_workflow_states
            self.reports = self._shared_reports
            self.documents = self._shared_documents
        else:
            self.locks = set()
            self.audit_journal = {}
            self.idempotency_store = {}
            self.custom_fields = {}
            self.property_setters = {}
            self.table_columns = {}
            self.revision_hashes = {}
            self.workflows = {}
            self.workflow_states = {}
            self.reports = {}
            self.documents = {}

        if not self.in_memory:
            self._ensure_audit_table()

    def _ensure_audit_table(self) -> None:
        if self.in_memory:
            return
        try:
            self._frappe.db.sql(f"""
                CREATE TABLE IF NOT EXISTS `{self.audit_table}` (
                    name VARCHAR(140) PRIMARY KEY,
                    deployment_id VARCHAR(140),
                    idempotency_key VARCHAR(140),
                    payload_hash VARCHAR(64),
                    site_id VARCHAR(140),
                    doctype VARCHAR(140),
                    fieldname VARCHAR(140),
                    base_revision_hash VARCHAR(64),
                    ddl_plan_statements LONGTEXT,
                    status VARCHAR(64),
                    outcome_json LONGTEXT,
                    created_at DATETIME(6),
                    updated_at DATETIME(6),
                    INDEX idx_site_idemp (site_id, idempotency_key),
                    INDEX idx_site_doctype_status (site_id, doctype, status)
                ) ENGINE=InnoDB
            """)
        except Exception:
            pass

    def begin_fresh_read_view(self) -> None:
        """Start the locked reads on a fresh view WITHOUT touching anyone's work (CE-SEC-008).

        Called right after the advisory locks are granted: under REPEATABLE READ a view opened by an earlier
        read would not show a row another session committed while this one waited for the lock. Ending the
        transaction is only safe when it holds no writes. Everything fails closed: the write counter must exist
        and be a non-negative integer and be zero, and a rollback must be available (there is no commit
        fallback). Otherwise this raises, the deployment is blocked, and the caller's work is left as it is.

        Limit: Frappe's counter does not see every kind of write (for example ``REPLACE``). The robust fix is a
        dedicated deployment connection for the locked reads and the deployment's own writes (CE-SEC-011).
        """
        if self._session_unusable:
            raise DurableEvidenceError("the database session was discarded")
        if self.in_memory:
            return
        db = self._frappe.db
        counter = getattr(db, "transaction_writes", None)
        if isinstance(counter, bool) or not isinstance(counter, int) or counter < 0:
            raise DurableEvidenceError("cannot tell whether the transaction holds uncommitted writes")
        if counter:
            raise DurableEvidenceError("uncommitted writes are pending in this transaction; not touching them")
        rollback = getattr(db, "rollback", None)
        if not callable(rollback):
            raise DurableEvidenceError("no way to open a fresh read view")
        rollback()  # nothing is pending (checked above): this only ends the read-only transaction

    @property
    def session_unusable(self) -> bool:
        return self._session_unusable

    def mark_session_unusable(self) -> None:
        """A lock may still be held on this connection, or unknown writes may be pending on it: refuse further
        use and discard the connection, which frees every advisory lock and drops pending writes. Safe to call
        again: a discard that did not work is retried, and until one works nothing counts as released."""
        self._session_unusable = True
        self._held_locks.clear()
        if self.in_memory:
            self._discard_confirmed = True
            return
        try:
            self._frappe.db.close()
            self._discard_confirmed = True
        except Exception:
            logger.exception("could not close the unusable database session")

    def acquire_advisory_lock(self, lock_key: str, wait_seconds: int) -> Optional[int]:
        if self._session_unusable:
            return None
        if not self.in_memory:
            try:
                res = self._frappe.db.sql("SELECT GET_LOCK(%s, %s)", (lock_key, wait_seconds))
                if res and len(res) > 0 and len(res[0]) > 0:
                    val = res[0][0]
                    if val is not None and int(val) == 1:
                        self._held_locks.add(lock_key)
                    return int(val) if val is not None else None
                return None
            except Exception:
                return None

        # Standalone / in-memory mode
        if self.lock_return is not _LOCK_SENTINEL:
            return self.lock_return
        if lock_key in self.locks:
            return 0  # Lock wait timeout (contention)
        self.locks.add(lock_key)
        return 1

    def release_advisory_lock(self, lock_key: str) -> bool:
        """Release a lock and verify it (``RELEASE_LOCK`` answers 1). Never raises, so a deployment that has
        already run is never reported as failed because of its own cleanup. ``True`` means verified released
        (or the connection that held it is verifiably closed); a release that is not verified, or a discard whose
        close failed, returns ``False`` and keeps the session unusable."""
        if self.in_memory:
            self.locks.discard(lock_key)
            return True
        if self._session_unusable:
            if not self._discard_confirmed:
                self.mark_session_unusable()  # retry the close
            return self._discard_confirmed
        try:
            res = self._frappe.db.sql("SELECT RELEASE_LOCK(%s)", (lock_key,))
            if res and res[0] and res[0][0] == 1:
                self._held_locks.discard(lock_key)
                return True
            logger.error("RELEASE_LOCK did not confirm the release of %s", lock_key)
        except Exception:
            logger.exception("RELEASE_LOCK failed for %s", lock_key)
        self.mark_session_unusable()
        return False

    def bind_request_site(self, site_id: str) -> None:
        """The site identity of the request being served, so evidence loaded for a deployment id can be checked
        against it (an id reused for another site is refused)."""
        self._request_site = site_id

    def set_lock_wait_timeout(self, seconds: int) -> None:
        """Set the session ``lock_wait_timeout`` and read the effective value back (CE-SEC-008).

        The session's previous value is remembered (once) so ``restore_lock_wait_timeout`` can put it back.
        Raises ``LockTimeoutError`` when the value is not an integer from 1 to the ceiling, the statement fails,
        the read-back fails or is empty, or the effective value differs. Nothing is recorded as effective
        until the read-back matches.
        """
        self.lock_wait_timeout_seconds = None
        if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= _MAX_LOCK_WAIT_SECONDS:
            raise LockTimeoutError(f"lock_wait_timeout must be an integer from 1 to {_MAX_LOCK_WAIT_SECONDS}")
        if not self.in_memory:
            try:
                if self._previous_lock_wait_timeout is None:
                    previous = self._frappe.db.sql("SELECT @@SESSION.lock_wait_timeout")
                    self._previous_lock_wait_timeout = int(previous[0][0])
                self._frappe.db.sql(f"SET SESSION lock_wait_timeout = {seconds}")
                rows = self._frappe.db.sql("SELECT @@SESSION.lock_wait_timeout")
                effective = int(rows[0][0])
            except Exception as exc:
                raise LockTimeoutError(
                    f"lock_wait_timeout could not be set or read back ({type(exc).__name__})"
                ) from exc
            if effective != seconds:
                raise LockTimeoutError(f"lock_wait_timeout is {effective} after setting {seconds}")
        self.lock_wait_timeout_seconds = seconds

    def restore_lock_wait_timeout(self) -> bool:
        """Put the session's previous ``lock_wait_timeout`` back and verify it, so a short deployment timeout never
        leaks into the caller's session. A restore that cannot be verified discards the session. Never raises;
        ``True`` when nothing needed restoring or it was restored."""
        previous = self._previous_lock_wait_timeout
        self.lock_wait_timeout_seconds = None
        if previous is None or self.in_memory:
            self._previous_lock_wait_timeout = None
            return True
        if self._session_unusable:
            return False
        try:
            self._frappe.db.sql(f"SET SESSION lock_wait_timeout = {previous}")
            rows = self._frappe.db.sql("SELECT @@SESSION.lock_wait_timeout")
            if int(rows[0][0]) != previous:
                raise LockTimeoutError("the restored lock_wait_timeout did not take")
        except Exception:
            logger.exception("could not restore the session lock_wait_timeout; discarding the session")
            self.mark_session_unusable()
            return False
        self._previous_lock_wait_timeout = None
        return True

    def _verify_session_lock_timeout(self, sql: Any = None) -> None:
        try:
            rows = (sql or self._frappe.db.sql)("SELECT @@SESSION.lock_wait_timeout")
            effective = int(rows[0][0])
        except Exception as exc:
            raise LockTimeoutError("lock_wait_timeout could not be re-read before dispatch") from exc
        if effective != self.lock_wait_timeout_seconds:
            raise LockTimeoutError("lock_wait_timeout on the dispatching session is not the verified value")

    def mark_recovery_required(self, deployment_id: str, reason: str = "") -> None:
        """Best-effort recovery marker when Stage 6 finalization fails after DDL (main rows only)."""
        self._require_usable_session()
        _require_main_row_id(deployment_id)
        if not self.in_memory:
            try:
                self._ensure_audit_table()
                self._frappe.db.sql(f"""
                    UPDATE `{self.audit_table}`
                    SET status = 'RECOVERY_REQUIRED',
                        outcome_json = %s,
                        updated_at = NOW(6)
                    WHERE deployment_id = %s AND {_MAIN_ROWS_ONLY}
                """, (json.dumps({"deployment_id": deployment_id, "status": "RECOVERY_REQUIRED", "reason": reason}), deployment_id))
                self._commit_durable()
            except Exception:
                pass
        elif deployment_id in self.audit_journal:
            self.audit_journal[deployment_id]["status"] = "RECOVERY_REQUIRED"
            self.audit_journal[deployment_id]["outcome"] = {
                "deployment_id": deployment_id,
                "status": "RECOVERY_REQUIRED",
                "reason": reason,
            }

    def is_target_in_recovery_required(self, site_id: str, doctype: str) -> bool:
        if self.target_in_recovery:
            return True
        read_ids = _read_site_ids(site_id, self._frappe)
        if not self.in_memory:
            # CE-SEC-008: a database error propagates and blocks; it is never read as "not blocked".
            res = self._frappe.db.sql(f"""
                SELECT COUNT(*) FROM `{self.audit_table}`
                WHERE site_id IN ({", ".join(["%s"] * len(read_ids))}) AND doctype = %s
                AND status IN ('RECOVERY_REQUIRED', 'PREPARED') AND {_MAIN_ROWS_ONLY}
            """, (*read_ids, doctype))
            # An empty or odd-shaped answer is a failed read, never "no blocked deployment".
            try:
                count = res[0][0]
            except (IndexError, TypeError, KeyError):
                count = None
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise DurableEvidenceError("the recovery lookup returned no usable count")
            return count > 0
        for rec in self.audit_journal.values():
            if rec.get("site_id") in read_ids and rec.get("doctype") == doctype:
                if rec.get("status") in ("RECOVERY_REQUIRED", "PREPARED"):
                    return True
        return False

    def get_existing_deployment_by_idempotency(
        self, site_id: str, idempotency_key: str
    ) -> Optional[Dict[str, Any]]:
        read_ids = _read_site_ids(site_id, self._frappe)
        if not self.in_memory:
            # CE-SEC-008: a database error, a missing row shape or an unusable stored outcome propagates and
            # blocks; it is never read as "no earlier attempt". A main row without an outcome is an unfinished
            # deployment: the key is held, and the hold is what a matching request is told.
            res = self._frappe.db.sql(f"""
                SELECT payload_hash, outcome_json, status FROM `{self.audit_table}`
                WHERE site_id IN ({", ".join(["%s"] * len(read_ids))}) AND idempotency_key = %s
                AND {_MAIN_ROWS_ONLY}
            """, (*read_ids, idempotency_key))
            if not res:
                return None
            completed: List[Tuple[str, Dict[str, Any]]] = []
            held: List[str] = []
            for row in res:
                if not isinstance(row, (tuple, list)) or len(row) < 2 or not isinstance(row[0], str):
                    raise DurableEvidenceError("an idempotency row has an unexpected shape")
                payload_hash, outcome_json = row[0], row[1]
                status = row[2] if len(row) > 2 else None
                if outcome_json is None:
                    if status not in ("PREPARED", "RECOVERY_REQUIRED"):
                        raise DurableEvidenceError("an idempotency row has no outcome and no hold status")
                    held.append(payload_hash)
                    continue
                completed.append((payload_hash, self._parse_outcome(outcome_json)))
            if len({h for h, _ in completed} | set(held)) > 1:
                raise DurableEvidenceError("one idempotency key is bound to several payloads")
            if completed:
                return {"payload_hash": completed[0][0], "outcome": completed[0][1]}
            return {"payload_hash": held[0], "outcome": self._hold_outcome()}
        stored = next((self.idempotency_store[(sid, idempotency_key)] for sid in read_ids
                       if (sid, idempotency_key) in self.idempotency_store), None)
        if stored is not None and stored.get("outcome") is None:
            return {"payload_hash": stored.get("payload_hash"), "outcome": self._hold_outcome()}
        return stored

    @staticmethod
    def _parse_outcome(outcome_json: Any) -> Dict[str, Any]:
        """A stored outcome must be a non-empty JSON object that says what it was (a ``status`` string)."""
        if not isinstance(outcome_json, str) or not outcome_json.strip():
            raise DurableEvidenceError("a stored outcome is empty")
        try:
            outcome = json.loads(outcome_json)
        except ValueError as exc:
            raise DurableEvidenceError("a stored outcome is not valid JSON") from exc
        status = outcome.get("status") if isinstance(outcome, dict) else None
        if not isinstance(status, str) or not status:
            raise DurableEvidenceError("a stored outcome is not an object with a status")
        return outcome

    @staticmethod
    def _hold_outcome() -> Dict[str, Any]:
        return {
            "status": "RECOVERY_REQUIRED",
            "stage": "INSPECT",
            "reason_code": "idempotency_key_held",
            "reason": "An earlier deployment with this idempotency key is unfinished; it holds the key until recovered.",
        }

    def _get_default_columns(self, doctype: str) -> List[ColumnDesc]:
        return [
            ColumnDesc(name="name", type="varchar(140)", default=None),
            ColumnDesc(name="creation", type="datetime(6)", default=None),
            ColumnDesc(name="modified", type="datetime(6)", default=None),
            ColumnDesc(name="modified_by", type="varchar(140)", default=None),
            ColumnDesc(name="owner", type="varchar(140)", default=None),
            ColumnDesc(name="docstatus", type="int(1)", default="0"),
            ColumnDesc(name="idx", type="int(8)", default="0"),
        ]

    def _update_in_memory_revision_hash(self, doctype: str) -> None:
        cols = self.get_table_columns_description(doctype)
        payload = json.dumps([[c.name, c.type, c.default] for c in cols], sort_keys=True)
        self.revision_hashes[doctype] = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _read_nullability(self, table_name: str) -> Dict[str, bool]:
        """``{column_lower: is_nullable}`` from information_schema. Raises when unreadable."""
        rows = self._frappe.db.sql(
            """
            SELECT COLUMN_NAME, IS_NULLABLE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            """,
            (table_name,),
        )
        return {str(r[0]).lower(): str(r[1]).upper() != "NO" for r in rows}

    def _read_table_schema(self, doctype: str) -> Optional[Dict[str, Any]]:
        """Whole-table fingerprint used to prove what the apply changed (ERP-027 re-review H1).

        Columns (type, nullability, default, key, charset, collation, EXTRA, comment, generation
        expression) and their order, indexes, table constraints, CHECK constraints, triggers and
        table engine/collation/row format. ``None`` when any part is unreadable (fail closed).
        """
        table_name = f"tab{doctype}"
        sql = self._frappe.db.sql
        try:
            cols = sql(
                """
                SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_KEY,
                       CHARACTER_SET_NAME, COLLATION_NAME, EXTRA, COLUMN_COMMENT, GENERATION_EXPRESSION
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
                """,
                (table_name,),
            )
            idx = sql(
                """
                SELECT INDEX_NAME, COLUMN_NAME, NON_UNIQUE, SEQ_IN_INDEX, SUB_PART, INDEX_TYPE
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                """,
                (table_name,),
            )
            constraints = sql(
                """
                SELECT CONSTRAINT_NAME, CONSTRAINT_TYPE
                FROM information_schema.TABLE_CONSTRAINTS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                """,
                (table_name,),
            )
            checks = sql(
                """
                SELECT CONSTRAINT_NAME, CHECK_CLAUSE
                FROM information_schema.CHECK_CONSTRAINTS
                WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = %s
                """,
                (table_name,),
            )
            triggers = sql(
                """
                SELECT TRIGGER_NAME, EVENT_MANIPULATION, ACTION_TIMING, ACTION_STATEMENT
                FROM information_schema.TRIGGERS
                WHERE EVENT_OBJECT_SCHEMA = DATABASE() AND EVENT_OBJECT_TABLE = %s
                """,
                (table_name,),
            )
            table = sql(
                """
                SELECT ENGINE, TABLE_COLLATION, ROW_FORMAT
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                """,
                (table_name,),
            )
            if not cols or not table:
                return None
            return {
                "columns": {
                    str(r[0]): dict(zip(SCHEMA_COLUMN_ATTRS, (str(x) for x in r[1:])))
                    for r in cols
                },
                "order": [str(r[0]) for r in cols],
                "indexes": {tuple(str(x) for x in r) for r in idx},
                "constraints": {(str(r[0]), str(r[1])) for r in constraints},
                "checks": {(str(r[0]), str(r[1])) for r in checks},
                "triggers": {
                    (str(r[0]), str(r[1]), str(r[2]), hashlib.sha256(str(r[3]).encode("utf-8")).hexdigest())
                    for r in triggers
                },
                "table": tuple(str(x) for x in table[0]),
            }
        except Exception:
            logger.exception("could not read the whole-table fingerprint of %s", table_name)
            return None

    def get_table_columns_description(self, doctype: str) -> Optional[List[ColumnDesc]]:
        """Live column definitions. In live mode ``None`` when they cannot be read: the DDL
        plan gate then rejects (DDL_GATE_EXISTING_COLUMNS_MISSING) instead of inspecting
        against substituted columns (ERP-027 re-review M1)."""
        if self.existing_columns_desc_override is not None:
            return self.existing_columns_desc_override
        if not self.in_memory:
            table_name = f"tab{doctype}"
            try:
                # IS_NULLABLE is not part of Frappe's own description; the DDL plan gate only
                # normalises zero defaults on columns proven NOT NULL (ERP-027 M1).
                nullable_by_col = self._read_nullability(table_name)
                if hasattr(self._frappe, "db") and hasattr(self._frappe.db, "get_table_columns_description"):
                    raw_cols = self._frappe.db.get_table_columns_description(table_name)
                    out = []
                    for c in raw_cols:
                        cname = c["name"] if isinstance(c, dict) else getattr(c, "name")
                        out.append(
                            ColumnDesc(
                                name=cname,
                                type=c["type"] if isinstance(c, dict) else getattr(c, "type"),
                                default=c.get("default") if isinstance(c, dict) else getattr(c, "default", None),
                                index=int(c.get("index", 0) if isinstance(c, dict) else getattr(c, "index", 0)),
                                unique=int(c.get("unique", 0) if isinstance(c, dict) else getattr(c, "unique", 0)),
                                nullable=nullable_by_col.get(str(cname).lower()),
                            )
                        )
                    return out or None
                res = self._frappe.db.sql(
                    """
                    SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_DEFAULT
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                    ORDER BY ORDINAL_POSITION
                    """,
                    (table_name,),
                )
                return [
                    ColumnDesc(name=r[0], type=r[1], default=r[2], nullable=nullable_by_col.get(str(r[0]).lower()))
                    for r in res
                ] or None
            except Exception:
                logger.exception("could not read the live column definitions of %s", table_name)
                return None
        if doctype not in self.table_columns:
            self.table_columns[doctype] = self._get_default_columns(doctype)
        return list(self.table_columns[doctype])

    def get_doctype_revision_hash(self, doctype: str) -> str:
        if not self.in_memory:
            table_name = f"tab{doctype}"
            try:
                res = self._frappe.db.sql(
                    """
                    SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                    ORDER BY ORDINAL_POSITION
                    """,
                    (table_name,),
                )
                payload = json.dumps([list(c) for c in res], sort_keys=True)
                return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
            except Exception as exc:
                # No "rev_default" stand-in: a stand-in would compare equal on both sides.
                raise RevisionHashError(f"{type(exc).__name__}: {exc}") from exc
        if doctype not in self.revision_hashes:
            self._update_in_memory_revision_hash(doctype)
        return self.revision_hashes[doctype]

    def take_snapshot(
        self, doctype: str, fieldname: str, expected_deployment_id: str
    ) -> ExhaustiveSnapshot:
        if not self.apply_called and self.before_snapshot_override is not None:
            return self.before_snapshot_override
        if self.apply_called and self.after_snapshot_override is not None:
            return self.after_snapshot_override

        if not self.in_memory:
            table_name = f"tab{doctype}"
            try:
                self._require_usable_session()
                meta_row = self._frappe.db.sql(
                    "SELECT name, fieldtype FROM `tabCustom Field` WHERE dt = %s AND fieldname = %s",
                    (doctype, fieldname),
                )
                has_meta = bool(meta_row)

                col_row = self._frappe.db.sql(
                    """
                    SELECT COLUMN_NAME, COLUMN_TYPE
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
                    """,
                    (table_name, fieldname),
                )
                has_col = bool(col_row)
                rev_hash = self.get_doctype_revision_hash(doctype)
                schema = self._read_table_schema(doctype)
                indexes_unchanged = True
                definition_matches = True
                unapproved = False
                provenance = True  # offline mode: nothing ran, so there is nothing to attribute
                restarted_dispatched: Optional[List[str]] = None
                if self.offline_ddl_simulator:
                    pass  # explicit offline mode: no real DDL ran, nothing to compare
                else:
                    post_apply = expected_deployment_id in self._applied_deployments
                    restarted = False
                    if not post_apply:
                        # CE-SEC-008: a deployment with durable evidence is never re-baselined from the
                        # live (possibly post-DDL) schema: after a restart the committed baseline wins.
                        # A failed or malformed read raises and fails the snapshot closed.
                        try:
                            evidence = self.load_durable_evidence(expected_deployment_id)
                        except DurableEvidenceError:
                            raise
                        except Exception as exc:  # a database error: the evidence is unavailable, never "absent"
                            raise DurableEvidenceError("the durable evidence could not be read") from exc
                        main_row = evidence["main"]
                        if main_row is not None:
                            # The evidence must belong to THIS request: an id reused for another table, field or
                            # site is refused, not assessed against someone else's baseline.
                            if main_row.get("doctype") != doctype or main_row.get("fieldname") != fieldname:
                                raise DurableEvidenceError("the evidence belongs to another table or field")
                            if self._request_site is not None and str(main_row.get("site_id")) not in _read_site_ids(
                                self._request_site, self._frappe
                            ):
                                raise DurableEvidenceError("the evidence belongs to another site")
                        if evidence["main"] is not None or evidence["baseline"] is not None:
                            if evidence["baseline"] is None or evidence["approved"] is None:
                                raise DurableEvidenceError("durable baseline or approved plan is missing")
                            self._before_schema.setdefault((doctype, expected_deployment_id), evidence["baseline"])
                            self._approved_ddl.setdefault(expected_deployment_id, evidence["approved"])
                            restarted_dispatched = evidence["dispatched"]
                            post_apply = True
                            restarted = True
                    if not post_apply:
                        if schema is None:
                            raise RuntimeError("before-apply table schema unreadable")
                        self._before_schema[(doctype, expected_deployment_id)] = schema
                if not self.offline_ddl_simulator and post_apply:
                    # Provenance is computed, never assumed: this process vouches for the change only when it
                    # sent the statements itself and every one of them returned. After a restart the journal
                    # holds intent, not proof, so a restarted deployment is never attributable here and the
                    # reconciler classifies it RECOVERY_REQUIRED instead of APPLIED.
                    provenance = (
                        not restarted
                        and self._dispatched_ddl.get(expected_deployment_id) is not None
                        and self._dispatched_ddl.get(expected_deployment_id) == self._executed_ddl.get(expected_deployment_id)
                    )
                    # ERP-027: what ran must match the approved plan; unknown means unapproved.
                    before_schema = self._before_schema.get((doctype, expected_deployment_id))
                    approved = self._approved_ddl.get(expected_deployment_id)
                    dispatched = (
                        restarted_dispatched if restarted_dispatched is not None
                        else self._dispatched_ddl.get(expected_deployment_id)
                    )
                    # Assess what was dispatched (a superset of what is known to have returned): a
                    # statement that was sent may have taken effect even if it never reported back.
                    # Only when the live schema equals the baseline on every fingerprint key is it
                    # proven that nothing took effect, and then nothing counts as executed.
                    assessed = dispatched
                    if dispatched and before_schema is not None and schema is not None and before_schema == schema:
                        assessed = []
                    unapproved, _why = assess_applied_ddl(
                        doctype,
                        fieldname,
                        approved,
                        assessed,
                        before_schema,
                        schema,
                    )
                    if unapproved:
                        logger.warning("DDL apply on %s.%s has unapproved side effects: %s", doctype, fieldname, _why)
                    indexes_unchanged = (
                        before_schema is not None
                        and schema is not None
                        and before_schema.get("indexes") == schema.get("indexes")
                    )
                    # Only meaningful once the column exists; a clean failure never reads it.
                    definition_matches = (not has_col) or new_column_matches_plan(fieldname, approved, schema)
                return ExhaustiveSnapshot(
                    has_meta=has_meta,
                    has_col=has_col,
                    definition_matches=definition_matches,
                    indexes_unchanged=indexes_unchanged,
                    provenance_matches=provenance,
                    unapproved_side_effects=unapproved,
                    revision_hash=rev_hash,
                )
            except Exception as exc:
                logger.exception("live snapshot of %s.%s failed; failing closed", doctype, fieldname)
                return ExhaustiveSnapshot(
                    has_meta=False,
                    has_col=False,
                    definition_matches=False,
                    indexes_unchanged=False,
                    provenance_matches=False,
                    unapproved_side_effects=True,
                    revision_hash="rev_error",
                    error_code=(
                        "evidence_unavailable" if isinstance(exc, (DurableEvidenceError, SessionDiscardedError))
                        else "snapshot_unavailable"
                    ),
                )
        else:
            has_meta = (doctype, fieldname) in self.custom_fields
            cols = self.get_table_columns_description(doctype)
            has_col = any(c.name == fieldname for c in cols)
            rev_hash = self.get_doctype_revision_hash(doctype)
            return ExhaustiveSnapshot(
                has_meta=has_meta,
                has_col=has_col,
                definition_matches=True,
                indexes_unchanged=True,
                provenance_matches=True,
                unapproved_side_effects=False,
                revision_hash=rev_hash,
            )

    def inspect_ddl_plan(self, doctype: str, field_def: Dict[str, Any]) -> DDLPlanInspection:
        if self.ddl_plan_override is not None:
            return self.ddl_plan_override
        cols = self.get_table_columns_description(doctype)
        return inspect_frappe_ddl_plan(
            doctype=doctype,
            field_def=field_def,
            existing_columns_desc=cols,
            doctype_fields=self.doctype_fields_override,
            offline_simulator=bool(self.in_memory or self.offline_ddl_simulator),
        )

    # -- durable evidence (CE-SEC-008) ---------------------------------------------------
    def _require_usable_session(self) -> None:
        """Once a session is discarded nothing may commit, finalize or rely on a lock through this adapter."""
        if self._session_unusable:
            raise SessionDiscardedError("the database session was discarded")

    def _require_locks_held(self, sql: Any = None) -> None:
        """Every advisory lock this adapter took must still be this connection's (``IS_USED_LOCK`` is our
        ``CONNECTION_ID``); one that is not means the session is no longer the one that was serialised."""
        if self.in_memory or not self._held_locks:
            return
        run = sql or self._frappe.db.sql
        for key in sorted(self._held_locks):
            try:
                rows = run("SELECT IS_USED_LOCK(%s) = CONNECTION_ID()", (key,))
                held = bool(rows and rows[0] and rows[0][0] == 1)
            except Exception:
                logger.exception("could not verify advisory lock %s", key)
                held = False
            if not held:
                self.mark_session_unusable()
                raise SessionDiscardedError("an advisory lock is no longer held by this session")

    def _commit_durable(self) -> None:
        self._require_usable_session()
        commit = getattr(self._frappe.db, "commit", None)
        if not callable(commit):
            raise DurableEvidenceError("the database cannot commit; nothing was made durable")
        commit()

    def _rollback_durable(self) -> bool:
        """Roll the open transaction back. A rollback that fails leaves unknown writes pending on this
        connection, so the session is declared unusable and discarded (the caller then holds, never finalizes)."""
        try:
            if hasattr(self._frappe.db, "rollback"):
                self._frappe.db.rollback()
            return True
        except Exception:
            logger.exception("rollback after a failed durable write also failed; discarding the session")
            self.mark_session_unusable()
            return False

    def _insert_audit_row(
        self, *, name: str, deployment_id: str, idempotency_key: str, payload_hash: str, site_id: str,
        doctype: str, fieldname: str, base_revision_hash: str, blob: str, status: str, sql: Any = None,
    ) -> None:
        """A strict INSERT (no upsert) into the audit table; the caller commits."""
        (sql or self._frappe.db.sql)(f"""
            INSERT INTO `{self.audit_table}` (
                name, deployment_id, idempotency_key, payload_hash, site_id, doctype,
                fieldname, base_revision_hash, ddl_plan_statements, status, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(6), NOW(6))
        """, (name, deployment_id, idempotency_key, payload_hash, site_id, doctype, fieldname,
              base_revision_hash, blob, status))

    def _insert_evidence_row(self, deployment_id: str, suffix: str, status: str, payload: Dict[str, Any],
                             sql: Any = None) -> None:
        ctx = self._intent_context.get(deployment_id, {})
        self._insert_audit_row(
            name=f"{deployment_id}#{suffix}",
            deployment_id=f"{deployment_id}#{suffix}",
            idempotency_key=_evidence_key(deployment_id),
            payload_hash=ctx.get("payload_hash", "hash_default"),
            site_id=ctx.get("site_id", "default"),
            doctype=ctx.get("doctype", ""),
            fieldname=ctx.get("fieldname", ""),
            base_revision_hash=ctx.get("base_revision_hash", "rev_default"),
            blob=json.dumps(payload, sort_keys=True),
            status=status,
            sql=sql,
        )

    def _read_audit_row(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        """The main intent row, or ``None`` only when the database answered with no row. Raises on error."""
        res = self._frappe.db.sql(
            f"SELECT {', '.join(_AUDIT_ROW_COLUMNS)} FROM `{self.audit_table}` "
            f"WHERE deployment_id = %s AND {_MAIN_ROWS_ONLY}",
            (deployment_id,),
        )
        if not res:
            return None
        row = res[0]
        if isinstance(row, dict):
            return dict(row)
        return dict(zip(_AUDIT_ROW_COLUMNS, row))

    def load_durable_evidence(self, deployment_id: str) -> Dict[str, Any]:
        """What survives a crash for one deployment: the main row, the approved plan, the committed
        baseline, and the dispatch journal (``dispatched`` is intent, ``completed`` is what returned).

        Raises ``DurableEvidenceError`` for malformed or inconsistent evidence and lets database errors
        propagate: a failed or partial read is never an empty result. ``baseline`` is ``None`` only when
        no baseline row exists.
        """
        if self.in_memory:
            rec = self.audit_journal.get(deployment_id)
            return {
                "deployment_id": deployment_id, "main": dict(rec) if rec else None,
                "approved": list(rec.get("ddl_plan_statements", [])) if rec else None,
                "baseline": None, "dispatched": [], "completed": [],
            }
        main = self._read_audit_row(deployment_id)
        approved: Optional[List[str]] = None
        stored_digest: Optional[str] = None
        if main is not None:
            approved = _stored_statements(main.get("ddl_plan_statements"))
            envelope = json.loads(main["ddl_plan_statements"])
            if isinstance(envelope, dict):
                stored_digest = envelope.get("evidence_sha256")
                if not isinstance(stored_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", stored_digest):
                    raise DurableEvidenceError("the stored evidence digest is malformed")
            elif approved:
                raise DurableEvidenceError("a physical-DDL deployment row carries no evidence digest")
        rows = self._frappe.db.sql(
            f"SELECT name, status, ddl_plan_statements FROM `{self.audit_table}` WHERE idempotency_key = %s",
            (_evidence_key(deployment_id),),
        )
        if rows and main is None:
            raise DurableEvidenceError("evidence rows exist without their deployment row")
        baseline: Optional[Dict[str, Any]] = None
        baseline_blob: Any = None
        offline_baseline = False
        dispatched: Dict[int, str] = {}
        completed: Dict[int, str] = {}
        for row in rows or ():
            _name, status, blob = row[0], row[1], row[2]
            kind = _EVIDENCE_KINDS.get(status)
            try:
                payload = json.loads(blob)
            except (TypeError, ValueError) as exc:
                raise DurableEvidenceError(f"evidence row '{_name}' is not valid JSON") from exc
            if kind is None or not isinstance(payload, dict) or payload.get("kind") != kind:
                raise DurableEvidenceError(f"evidence row '{_name}' has an unknown or inconsistent kind")
            if kind == "baseline":
                if baseline is not None or offline_baseline:
                    raise DurableEvidenceError("more than one baseline row")
                if payload.get("schema") is None:
                    offline_baseline = True
                else:
                    baseline_blob = payload["schema"]
                    baseline = _decode_schema(baseline_blob)
            else:
                seq, statement = payload.get("seq"), payload.get("statement")
                table = dispatched if kind == "dispatch_intent" else completed
                if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1 or not isinstance(statement, str) or seq in table:
                    raise DurableEvidenceError(f"journal row '{_name}' is malformed or repeated")
                if stored_digest is None or payload.get("digest") != _row_digest(stored_digest, kind, seq, statement):
                    raise DurableEvidenceError(f"journal row '{_name}' does not match the deployment's digest")
                table[seq] = statement
        if stored_digest is not None:
            expected = _bind_digest(
                main["deployment_id"], main["site_id"], main["doctype"], main["fieldname"], main["payload_hash"],
                approved, baseline_blob)
            if not hmac.compare_digest(expected, stored_digest):
                raise DurableEvidenceError("the evidence (plan, baseline or identity) does not match its digest")
        if sorted(dispatched) != list(range(1, len(dispatched) + 1)):
            raise DurableEvidenceError("dispatch journal has a gap")
        for seq, statement in completed.items():
            if dispatched.get(seq) != statement:
                raise DurableEvidenceError("a completion has no matching dispatch intent")
        return {
            "deployment_id": deployment_id, "main": main, "approved": approved, "baseline": baseline,
            "offline_baseline": offline_baseline,
            "dispatched": [dispatched[i] for i in sorted(dispatched)],
            "completed": [completed[i] for i in sorted(completed)],
        }

    def _main_digest(self, deployment_id: str) -> str:
        return self._intent_context.get(deployment_id, {}).get("digest", "")

    def _journal_dispatch_intent(self, deployment_id: str, statement: str, seq: int, sql: Any) -> None:
        """Commit the intent to send ``statement`` BEFORE it is sent; a failure here means it is not sent."""
        try:
            self._insert_evidence_row(
                deployment_id, f"d{seq:04d}", _EVIDENCE_DISPATCH,
                {"kind": "dispatch_intent", "seq": seq, "statement": statement,
                 "digest": _row_digest(self._main_digest(deployment_id), "dispatch_intent", seq, statement)}, sql=sql)
            self._commit_durable()
        except Exception:
            self._rollback_durable()
            raise

    def _journal_completion(self, deployment_id: str, statement: str, seq: int, sql: Any) -> None:
        """Record that ``statement`` returned. Best effort: a missing completion row only ever reads as
        "dispatched, outcome unknown", the conservative state, so it never aborts an apply that took effect."""
        try:
            self._insert_evidence_row(
                deployment_id, f"c{seq:04d}", _EVIDENCE_COMPLETED,
                {"kind": "dispatch_completed", "seq": seq, "statement": statement,
                 "digest": _row_digest(self._main_digest(deployment_id), "dispatch_completed", seq, statement)}, sql=sql)
            self._commit_durable()
        except Exception:
            logger.exception("could not journal the completion of DDL statement %d of %s", seq, deployment_id)
            self._rollback_durable()

    @staticmethod
    def _intent_binding(record: Dict[str, Any]) -> Dict[str, str]:
        dep_id = record["deployment_id"]
        return {
            "idempotency_key": record.get("idempotency_key", f"idemp-{dep_id}"),
            "payload_hash": record.get("payload_hash", "hash_default"),
            "site_id": record.get("site_id", "default"),
            "doctype": record.get("doctype", ""),
            "fieldname": record.get("fieldname") or "",
        }

    def persist_prepare_and_audit_intent(self, record: Dict[str, Any]) -> None:
        """Stage 3: commit the intent, the approved plan and the baseline schema BEFORE any DDL.

        A strict INSERT: an existing record for this deployment id is never overwritten. It raises
        ``DeploymentIntentConflictError`` (``binding_mismatch`` or ``already_recorded``), and
        ``DurableEvidenceError`` when the live baseline is missing. On any failure nothing stays committed.
        """
        if self.simulate_prepare_error:
            raise RuntimeError("Fail-closed: Simulated audit prepare failure")
        self._require_usable_session()

        dep_id = record["deployment_id"]
        # A NEW deployment gets the strict canonical grammar (existing rows are not re-validated).
        if caller_id_problem(dep_id):
            raise InvalidDeploymentIdError("the deployment id is not canonical")
        if caller_id_problem(record.get("idempotency_key", f"idemp-{dep_id}"), MAX_IDEMPOTENCY_KEY_LENGTH):
            raise InvalidDeploymentIdError("the idempotency key is not canonical")
        if caller_id_problem(record.get("site_id", "default"), MAX_SITE_ID_LENGTH):
            raise InvalidDeploymentIdError("the site identity is not canonical")
        approved = list(record.get("ddl_plan_statements", []))
        binding = self._intent_binding(record)
        # Only physical DDL has a schema baseline and a dispatch journal. Property-setter, workflow and
        # report deployments carry no plan statements and keep the plain strict intent row.
        physical_ddl = bool(approved)

        if not self.in_memory:
            baseline = self._before_schema.get((binding["doctype"], dep_id)) if physical_ddl else None
            if physical_ddl and baseline is None and not self.offline_ddl_simulator:
                raise DurableEvidenceError("no baseline schema was captured before the intent; refusing to prepare")
            self._ensure_audit_table()
            baseline_blob = _encode_schema(baseline) if baseline is not None else None
            blob = json.dumps(approved)
            digest = ""
            if physical_ddl:
                digest = _bind_digest(dep_id, binding["site_id"], binding["doctype"], binding["fieldname"],
                                      binding["payload_hash"], approved, baseline_blob)
                blob = json.dumps({"statements": approved, "evidence_sha256": digest})
            self._intent_context[dep_id] = {
                **binding, "base_revision_hash": record.get("base_revision_hash", "rev_default"), "digest": digest}
            try:
                self._insert_audit_row(
                    name=dep_id, deployment_id=dep_id, blob=blob,
                    base_revision_hash=record.get("base_revision_hash", "rev_default"),
                    status=record.get("status", "PREPARED"), **binding)
                if physical_ddl:
                    self._insert_evidence_row(dep_id, "baseline", _EVIDENCE_BASELINE, {
                        "kind": "baseline", "doctype": binding["doctype"], "schema": baseline_blob,
                    })
                self._commit_durable()
            except Exception as exc:
                self._rollback_durable()
                self._intent_context.pop(dep_id, None)
                try:
                    existing = self._read_audit_row(dep_id)
                except Exception:
                    existing = None
                if existing is not None:
                    try:
                        stored = _stored_statements(existing.get("ddl_plan_statements"))
                    except DurableEvidenceError:
                        stored = None
                    same = (
                        all(str(existing.get(k)) == str(v) for k, v in binding.items()) and stored == approved
                    )
                    raise DeploymentIntentConflictError(
                        dep_id, "already_recorded" if same else "binding_mismatch") from exc
                logger.exception("could not persist the deployment intent for %s", dep_id)
                raise DurableEvidenceError("the deployment intent could not be persisted") from exc
            self._approved_ddl[dep_id] = approved
        else:
            if dep_id in self.audit_journal:
                existing = self.audit_journal[dep_id]
                same = self._intent_binding(existing) == binding and list(
                    existing.get("ddl_plan_statements", [])) == approved
                raise DeploymentIntentConflictError(dep_id, "already_recorded" if same else "binding_mismatch")
            self._approved_ddl[dep_id] = approved
            self.audit_journal[dep_id] = dict(record)
            self.prepared_records.append(record)
            self.idempotency_store[(record["site_id"], record["idempotency_key"])] = {
                "payload_hash": record["payload_hash"],
                "outcome": None,
            }

    def persist_final_outcome_and_audit(
        self, deployment_id: str, outcome_record: Dict[str, Any]
    ) -> None:
        if self.simulate_finalize_error:
            raise RuntimeError("Final audit persistence simulated failure")
        self._require_usable_session()
        _require_main_row_id(deployment_id)

        outcome = outcome_record.get("outcome", {})
        status = outcome.get("status", "COMPLETED")
        outcome_json = json.dumps(outcome)

        if not self.in_memory:
            self._ensure_audit_table()
            self._frappe.db.sql(f"""
                UPDATE `{self.audit_table}`
                SET status = %s, outcome_json = %s, updated_at = NOW(6)
                WHERE deployment_id = %s AND {_MAIN_ROWS_ONLY}
            """, (status, outcome_json, deployment_id))
            self._commit_durable()
        else:
            if deployment_id in self.audit_journal:
                self.audit_journal[deployment_id]["status"] = status
                self.audit_journal[deployment_id]["outcome"] = outcome
                rec = self.audit_journal[deployment_id]
                self.idempotency_store[(rec["site_id"], rec["idempotency_key"])] = outcome_record
            else:
                self.audit_journal[deployment_id] = {
                    "deployment_id": deployment_id,
                    "status": status,
                    "outcome": outcome,
                }

    def apply_native_custom_field(
        self, deployment_id: str, doctype: str, field_def: Dict[str, Any]
    ) -> None:
        self._require_usable_session()
        if not self.in_memory:
            self._require_locks_held()
        self.apply_called = True
        self._applied_deployments.add(deployment_id)
        if self.simulate_apply_error:
            raise TimeoutError("(1205, 'Lock wait timeout exceeded')")

        fieldname = field_def["fieldname"]
        cf_args = {
            "doctype": "Custom Field",
            "dt": doctype,
            "fieldname": fieldname,
            "label": field_def.get("label", fieldname),
            "fieldtype": field_def.get("fieldtype", "Data"),
            "options": field_def.get("options"),
            "reqd": field_def.get("reqd", 0),
            "read_only": field_def.get("read_only", 0),
            "description": field_def.get("description"),
            "insert_after": field_def.get("insert_after"),
            "default": field_def.get("default"),
        }
        if not self.in_memory:
            # Validate before dispatch: post-apply snapshots cannot undo a narrowing DDL
            # statement whose implicit commit already truncated customer data.
            dispatched = self._dispatched_ddl.setdefault(deployment_id, [])
            executed = self._executed_ddl.setdefault(deployment_id, [])
            db = self._frappe.db
            original_sql_ddl = getattr(db, "sql_ddl", None)
            original_sql = getattr(db, "sql", None)
            in_sql_ddl = [0]

            def _admit_ddl(query):
                """Check this batch prefix, then commit the dispatch intent, before the statement is sent.

                If the intent cannot be made durable the statement is not sent (CE-SEC-008).
                """
                statement = str(query)
                reason = ddl_batch_rejection(
                    doctype, fieldname, self._approved_ddl.get(deployment_id),
                    [*dispatched, statement], self._before_schema.get((doctype, deployment_id)),
                    complete=False,
                )
                if reason:
                    raise ValueError("DDL rejected before execution: " + reason)
                # The timeout verified when it was set must still hold on THIS session, the one that sends the
                # statement (a reconnect or a reset in between would otherwise let DDL wait unbounded).
                if self.lock_wait_timeout_seconds is not None:
                    self._verify_session_lock_timeout(original_sql)
                seq = len(dispatched) + 1
                self._journal_dispatch_intent(deployment_id, statement, seq, original_sql)
                dispatched.append(statement)
                return seq, statement

            def _completed_ddl(seq, statement):
                """Only after the statement returned: it is now recorded as executed."""
                executed.append(statement)
                self._journal_completion(deployment_id, statement, seq, original_sql)

            def _recording_sql_ddl(query, *a, **kw):
                seq, statement = _admit_ddl(query)
                in_sql_ddl[0] += 1
                try:
                    result = original_sql_ddl(query, *a, **kw)
                finally:
                    in_sql_ddl[0] -= 1
                _completed_ddl(seq, statement)
                return result

            def _recording_sql(query, *a, **kw):
                if not in_sql_ddl[0] and requires_ddl_check(str(query)):
                    seq, statement = _admit_ddl(query)
                    result = original_sql(query, *a, **kw)
                    _completed_ddl(seq, statement)
                    return result
                return original_sql(query, *a, **kw)

            if original_sql_ddl is not None:
                db.sql_ddl = _recording_sql_ddl
            if original_sql is not None:
                db.sql = _recording_sql
            try:
                # Re-verify the timeout on this session BEFORE the metadata insert: a refusal later (at the first
                # statement) would find the Custom Field row already written.
                if self.lock_wait_timeout_seconds is not None:
                    self._verify_session_lock_timeout(original_sql)
                cf_doc = self._frappe.get_doc(cf_args)
                cf_doc.insert(ignore_permissions=True)
            except Exception:
                if not dispatched:
                    # No statement was sent, so nothing the engine wrote during this apply may stay: roll the
                    # pending metadata back, or the finalization commit would persist an orphan Custom Field.
                    self._rollback_durable()
                raise
            finally:
                if original_sql_ddl is not None:
                    db.sql_ddl = original_sql_ddl
                if original_sql is not None:
                    db.sql = original_sql
            # The commit publishes the apply: only on a session that is still usable and still holds the lock.
            self._require_usable_session()
            self._require_locks_held()
            self._commit_durable()
        else:
            self.custom_fields[(doctype, fieldname)] = dict(cf_args)
            if doctype not in self.table_columns:
                self.table_columns[doctype] = self._get_default_columns(doctype)
            if not any(c.name == fieldname for c in self.table_columns[doctype]):
                t_info = MARIADB_TYPE_MAP.get(field_def.get("fieldtype", "Data"), ("varchar", "140"))
                type_str = f"{t_info[0]}({t_info[1]})" if t_info[1] else t_info[0]
                self.table_columns[doctype].append(
                    ColumnDesc(name=fieldname, type=type_str, default=field_def.get("default"))
                )
            self._update_in_memory_revision_hash(doctype)

    def clear_doctype_cache(self, doctype: str) -> None:
        self.cache_cleared = True
        if not self.in_memory:
            if hasattr(self._frappe, "clear_cache"):
                self._frappe.clear_cache(doctype=doctype)

    def apply_property_setter(
        self,
        doctype: str,
        fieldname: Optional[str],
        property_name: str,
        value: Any,
        property_type: str = "Data",
    ) -> None:
        self.apply_called = True
        if self.simulate_apply_error:
            raise TimeoutError("(1205, 'Lock wait timeout exceeded')")

        if self.in_memory:
            self.property_setters[(doctype, fieldname, property_name)] = {
                "name": f"ps-{doctype}-{fieldname or 'doc'}-{property_name}",
                "doc_type": doctype,
                "field_name": fieldname,
                "property": property_name,
                "value": value,
                "property_type": property_type,
            }
        else:
            if hasattr(self._frappe, "make_property_setter"):
                try:
                    self._frappe.make_property_setter({
                        "doctype": doctype,
                        "fieldname": fieldname,
                        "property": property_name,
                        "value": value,
                        "property_type": property_type,
                    })
                except TypeError:
                    self._frappe.make_property_setter(
                        doctype=doctype,
                        fieldname=fieldname,
                        property=property_name,
                        value=value,
                        property_type=property_type,
                    )
                self._commit_durable()

    def get_property_setter(
        self, doctype: str, fieldname: Optional[str], property_name: str
    ) -> Optional[Dict[str, Any]]:
        if self.in_memory:
            return self.property_setters.get((doctype, fieldname, property_name))
        try:
            if fieldname:
                res = self._frappe.db.sql(
                    "SELECT name, value, property_type FROM `tabProperty Setter` WHERE doc_type = %s AND field_name = %s AND property = %s",
                    (doctype, fieldname, property_name),
                    as_dict=True,
                )
            else:
                res = self._frappe.db.sql(
                    "SELECT name, value, property_type FROM `tabProperty Setter` WHERE doc_type = %s AND (field_name IS NULL OR field_name = '') AND property = %s",
                    (doctype, property_name),
                    as_dict=True,
                )
            if res:
                row = res[0]
                if isinstance(row, dict):
                    return row
                return {"name": row[0], "value": row[1], "property_type": row[2] if len(row) > 2 else "Data"}
            return None
        except Exception:
            return None

    def delete_property_setter(
        self, doctype: str, fieldname: Optional[str], property_name: str
    ) -> None:
        if self.in_memory:
            self.property_setters.pop((doctype, fieldname, property_name), None)
        else:
            try:
                if fieldname:
                    self._frappe.db.sql(
                        "DELETE FROM `tabProperty Setter` WHERE doc_type = %s AND field_name = %s AND property = %s",
                        (doctype, fieldname, property_name),
                    )
                else:
                    self._frappe.db.sql(
                        "DELETE FROM `tabProperty Setter` WHERE doc_type = %s AND (field_name IS NULL OR field_name = '') AND property = %s",
                        (doctype, property_name),
                    )
                self._commit_durable()
            except Exception:
                pass

    def get_deployment_record(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        """The main deployment row, or ``None`` when it does not exist (also for any id inside the evidence
        namespace). A failed read raises ``DurableEvidenceError``: it is never reported as "not found"."""
        if evidence_namespace_problem(deployment_id):
            return None
        if self.in_memory:
            return self.audit_journal.get(deployment_id)
        try:
            self._ensure_audit_table()
            res = self._frappe.db.sql(
                f"SELECT * FROM `{self.audit_table}` WHERE deployment_id = %s AND {_MAIN_ROWS_ONLY}",
                (deployment_id,),
                as_dict=True,
            )
        except Exception as exc:
            logger.exception("deployment record lookup failed for %s", deployment_id)
            raise DurableEvidenceError("the deployment record could not be read") from exc
        if not res:
            return None
        row = dict(res[0])
        if row.get("outcome_json") is not None:  # an empty string is a damaged outcome, not "none"
            extra = self._parse_outcome(row["outcome_json"])
            for k, v in extra.items():
                if k not in row or row[k] is None:
                    row[k] = v
        return row

    def update_deployment_status(
        self, deployment_id: str, status: str, outcome: Optional[Dict[str, Any]] = None
    ) -> None:
        outcome_record = {"outcome": outcome or {"status": status}}
        self.persist_final_outcome_and_audit(deployment_id, outcome_record)

    def get_effective_field_property(
        self, doctype: str, fieldname: str, property_name: str
    ) -> Any:
        ps = self.get_property_setter(doctype, fieldname, property_name)
        if ps is not None:
            return ps.get("value")
        if self.in_memory:
            if (doctype, fieldname) in self.custom_fields:
                return self.custom_fields[(doctype, fieldname)].get(property_name)
            if property_name in ("hidden", "reqd", "read_only", "in_list_view", "in_standard_filter", "bold"):
                return 0
            if property_name == "label":
                return fieldname.replace("_", " ").title()
            return None
        else:
            if hasattr(self._frappe, "get_meta"):
                try:
                    meta = self._frappe.get_meta(doctype)
                    df = meta.get_field(fieldname) if hasattr(meta, "get_field") else None
                    if df:
                        return getattr(df, property_name, None)
                except Exception:
                    pass
            return None

    def ensure_workflow_state(self, state_name: str, style: Optional[str] = None) -> None:
        if self.in_memory:
            self.workflow_states[state_name] = {
                "name": state_name,
                "workflow_state_name": state_name,
                "style": style or "Primary",
            }
        else:
            if hasattr(self._frappe, "db") and hasattr(self._frappe, "get_doc"):
                if not self._frappe.db.exists("Workflow State", state_name):
                    ws = self._frappe.get_doc({
                        "doctype": "Workflow State",
                        "workflow_state_name": state_name,
                        "style": style or "Primary",
                    })
                    ws.insert(ignore_permissions=True)
                    self._commit_durable()

    def get_workflow_state(self, state_name: str) -> Optional[Dict[str, Any]]:
        if self.in_memory:
            return self.workflow_states.get(state_name)
        if hasattr(self._frappe, "db") and hasattr(self._frappe.db, "get_value"):
            # SEC-022 (ADR-0051): a failed read raises; the state-collision gate never reads it as "no such state".
            return self._frappe.db.get_value(
                "Workflow State",
                state_name,
                ["name", "workflow_state_name", "style"],
                as_dict=True,
            )
        raise RuntimeError("workflow state lookup unavailable")

    def get_active_workflow(self, doctype: str) -> Optional[Dict[str, Any]]:
        if self.in_memory:
            for wf in self.workflows.values():
                if wf.get("document_type") == doctype and wf.get("is_active") in (1, True):
                    return dict(wf)
            return None
        if hasattr(self._frappe, "db") and hasattr(self._frappe.db, "get_value"):
            try:
                wf_name = self._frappe.db.get_value(
                    "Workflow", {"document_type": doctype, "is_active": 1}, "name"
                )
                if wf_name:
                    wf_doc = self._frappe.get_doc("Workflow", wf_name)
                    return wf_doc.as_dict()
            except Exception:
                return None
        return None

    def get_workflow(self, workflow_name: str) -> Optional[Dict[str, Any]]:
        if self.in_memory:
            wf = self.workflows.get(workflow_name)
            return dict(wf) if wf else None
        if hasattr(self._frappe, "db") and hasattr(self._frappe, "get_doc"):
            try:
                if self._frappe.db.exists("Workflow", workflow_name):
                    return self._frappe.get_doc("Workflow", workflow_name).as_dict()
            except Exception:
                return None
        return None

    def apply_workflow(self, doctype: str, workflow_data: Dict[str, Any]) -> None:
        self.apply_called = True
        wf_name = workflow_data.get("workflow_name")
        if self.in_memory:
            self.workflows[wf_name] = dict(workflow_data)
        else:
            if hasattr(self._frappe, "get_doc"):
                if self._frappe.db.exists("Workflow", wf_name):
                    w_doc = self._frappe.get_doc("Workflow", wf_name)
                    w_doc.update(workflow_data)
                    w_doc.is_active = 1
                    w_doc.save(ignore_permissions=True)
                else:
                    w_doc = self._frappe.get_doc(workflow_data)
                    w_doc.insert(ignore_permissions=True)
                self._commit_durable()

    def set_workflow_active(self, workflow_name: str, is_active: int) -> None:
        if self.in_memory:
            if workflow_name in self.workflows:
                self.workflows[workflow_name]["is_active"] = is_active
        else:
            if hasattr(self._frappe, "db") and hasattr(self._frappe.db, "set_value"):
                self._frappe.db.set_value("Workflow", workflow_name, "is_active", is_active)
                self._commit_durable()

    def get_report(self, report_name: str) -> Optional[Dict[str, Any]]:
        if self.in_memory:
            rep = self.reports.get(report_name)
            return dict(rep) if rep else None
        if hasattr(self._frappe, "db") and hasattr(self._frappe, "get_doc"):
            try:
                if self._frappe.db.exists("Report", report_name):
                    return self._frappe.get_doc("Report", report_name).as_dict()
            except Exception:
                return None
        return None

    def apply_report(self, report_name: str, report_doc: Dict[str, Any]) -> None:
        self.apply_called = True
        if self.in_memory:
            self.reports[report_name] = dict(report_doc)
        else:
            if hasattr(self._frappe, "get_doc"):
                if self._frappe.db.exists("Report", report_name):
                    r_doc = self._frappe.get_doc("Report", report_name)
                    r_doc.update(report_doc)
                    r_doc.save(ignore_permissions=True)
                else:
                    r_doc = self._frappe.get_doc(report_doc)
                    r_doc.insert(ignore_permissions=True)
                self._commit_durable()

    def set_report_disabled(self, report_name: str, disabled: int = 1) -> None:
        if self.in_memory:
            if report_name in self.reports:
                self.reports[report_name]["disabled"] = disabled
        else:
            if hasattr(self._frappe, "db") and hasattr(self._frappe.db, "set_value"):
                self._frappe.db.set_value("Report", report_name, "disabled", disabled)
                self._commit_durable()

    def get_document(self, doctype: str, name: str) -> Optional[Dict[str, Any]]:
        if self.in_memory:
            doc = self.documents.get((doctype, name))
            return dict(doc) if doc else None
        if hasattr(self._frappe, "db") and hasattr(self._frappe, "get_doc"):
            try:
                if self._frappe.db.exists(doctype, name):
                    return self._frappe.get_doc(doctype, name).as_dict()
            except Exception:
                return None
        return None

    def set_document(self, doctype: str, name: str, doc_data: Dict[str, Any]) -> None:
        if self.in_memory:
            self.documents[(doctype, name)] = dict(doc_data)
        else:
            if hasattr(self._frappe, "get_doc"):
                if self._frappe.db.exists(doctype, name):
                    doc = self._frappe.get_doc(doctype, name)
                    doc.update(doc_data)
                    doc.save(ignore_permissions=True)
                else:
                    doc_dict = dict(doc_data)
                    doc_dict["doctype"] = doctype
                    doc = self._frappe.get_doc(doc_dict)
                    doc.insert(ignore_permissions=True)
                self._commit_durable()



def _stable_reason_code(exc: BaseException) -> str:
    """A fixed, non-sensitive code for an exception that reaches an RPC response."""
    if isinstance(exc, DeploymentIntentConflictError):
        return "intent_conflict"
    if isinstance(exc, LockTimeoutError):
        return "lock_timeout_not_effective"
    if isinstance(exc, InvalidDeploymentIdError):
        return "invalid_deployment_id"
    return "engine_unavailable"


def _unexpected_failure(exc: BaseException, label: str, deployment_id: Any, start_time: float, **extra: Any) -> Dict[str, Any]:
    """The RPC response for an unhandled error: a stable code and fixed text only; the details stay in the log."""
    logger.error("%s raised an unhandled exception for %s", label, deployment_id, exc_info=exc)
    return {
        "deployment_id": deployment_id,
        "status": "FAILED_CLEAN",
        "success": False,
        "stage": "UNKNOWN",
        "disposition": "UNEXPECTED_ERROR",
        "reason_code": _stable_reason_code(exc),
        "reason": f"{label} failed; the details are in the server log.",
        **extra,
        "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
    }


def _reject_invalid_deployment_id(deployment_id: Any, start_time: float, **extra: Any) -> Optional[Dict[str, Any]]:
    """RPC boundary check: ids that could name or collide with an evidence row are refused before any work."""
    problem = caller_id_problem(deployment_id)
    if not problem:
        return None
    return {
        "deployment_id": None,
        "status": "REJECTED",
        "success": False,
        "stage": "VALIDATE",
        "disposition": "INVALID_DEPLOYMENT_ID",
        "reason_code": "invalid_deployment_id",
        "reason": f"The deployment id {problem}.",
        **extra,
        "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
    }


# The runtime backend's tenant-id grammar (frappe_backend._SAFE_TENANT_RE). It forbids '-', '.', uppercase and a
# trailing '_', so the backend's site name ``<tenant with _ as ->.<domain>`` maps back to exactly one tenant id.
_TENANT_ID_RE = re.compile(r"t_[a-z0-9][a-z0-9_]{1,59}[a-z0-9]")


def _tenant_of_site(resolved: str) -> Optional[str]:
    """The one tenant id whose backend site name is ``resolved``, or ``None`` for a site that is not a tenant site
    (a custom ``site_map`` entry, a bench or test site). CE-SEC-011 resolves custom ``site_map`` sites."""
    label, dot, _domain = resolved.partition(".")
    if not dot:
        return None
    tenant = label.replace("-", "_")
    return tenant if _TENANT_ID_RE.fullmatch(tenant) and tenant.replace("_", "-") == label else None


def _read_site_ids(site_id: str, runtime: Any = None) -> Tuple[str, ...]:
    """The ``site_id`` values the hold and replay lookups read for ``site_id``: the identity itself, plus, on the
    tenant site it belongs to, the host name that rows written before the single-identity rule used (CE-SEC-008
    round 6). Read-only: every new row, lock and journal entry uses ``site_id`` alone. Another site's host name is
    never added, because the alias is taken only when the current site maps back to exactly this identity.
    The site comes from the adapter's own runtime when it has one (an injected Frappe), else the global one."""
    resolved = getattr(getattr(runtime, "local", None), "site", None) if runtime is not None else None
    if not isinstance(resolved, str):
        resolved = getattr(getattr(frappe, "local", None), "site", None)
    if isinstance(resolved, str) and resolved != site_id and _tenant_of_site(resolved) == site_id:
        return (site_id, resolved)
    return (site_id,)


def _resolve_site_id(caller_site: Any, deployment_id: Any, start_time: float, **extra: Any):
    """The ``site_id`` for the lock, the lookups and the audit rows: ONE authoritative identity per site.

    On a tenant site the identity is the tenant id the backend binds (``t-alpha.<domain>`` -> ``t_alpha``),
    whether or not the caller passes it; any other spelling (the host name, ``t-alpha``, other case) is refused,
    so no alias can open a second lock and audit scope that steps around holds and replay records. On a site that
    is not a tenant site the site name is the only identity. With no resolved site (in-memory) the caller's
    canonical identity, else ``default``, is used. Returns ``(site_id, None)`` or ``(None, rejection)``.
    """
    resolved = getattr(getattr(frappe, "local", None), "site", None)
    if resolved:
        site = _tenant_of_site(resolved) or resolved
        if caller_site is not None and caller_site != site:
            return None, _site_rejection(deployment_id, start_time, "SITE_MISMATCH", "site_mismatch",
                                         "The site identity does not belong to the site this request runs on.",
                                         **extra)
    else:
        site = caller_site if caller_site is not None else "default"
    if caller_id_problem(site, MAX_SITE_ID_LENGTH):
        return None, _site_rejection(deployment_id, start_time, "INVALID_SITE_ID", "invalid_site_id",
                                     "The site identity is not canonical.", **extra)
    return site, None


def _site_rejection(deployment_id: Any, start_time: float, disposition: str, code: str, reason: str, **extra: Any):
    return {
        "deployment_id": deployment_id,
        "status": "REJECTED",
        "success": False,
        "stage": "VALIDATE",
        "disposition": disposition,
        "reason_code": code,
        "reason": reason,
        **extra,
        "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
    }


_LOCK_WAIT_TEXT = re.compile(r"[0-9]{1,9}")


def _parse_lock_wait_seconds(value: Any) -> Optional[int]:
    """The RPC timeout: an integer, or the digits of one as sent over the wire; anything else is ``None``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and _LOCK_WAIT_TEXT.fullmatch(value):
        value = int(value)
    if not isinstance(value, int) or not 1 <= value <= _MAX_LOCK_WAIT_SECONDS:
        return None
    return value


def _invalid_lock_wait(deployment_id: Any, start_time: float) -> Dict[str, Any]:
    return {
        "deployment_id": deployment_id,
        "status": "REJECTED",
        "success": False,
        "stage": "VALIDATE",
        "disposition": "INVALID_LOCK_WAIT_SECONDS",
        "reason_code": "invalid_lock_wait_seconds",
        "reason": f"lock_wait_seconds must be an integer from 1 to {_MAX_LOCK_WAIT_SECONDS}.",
        "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
    }


def apply_configuration_change(
    doctype: str,
    deployment_id: Optional[str] = None,
    field_def: Optional[Union[Dict[str, Any], str]] = None,
    idempotency_key: Optional[str] = None,
    proposal: Optional[Any] = None,
    base_revision_hash: Optional[str] = None,
    site_id: Optional[str] = None,
    adapter: Optional[Rev23DeploymentAdapter] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Whitelisted RPC endpoint for single-field physical schema deployment.
    Adheres strictly to ADR-001 Rev 2.3:
    1. Checks authenticated user roles: only authorized roles (System Manager,
       Finance Director, Operations Director) can apply changes.
    2. Invokes execute_single_field_deployment with durable MariaDB advisory lock,
       DDL plan gate, prepare audit, native Custom Field creation, and snapshot reconciliation.
    3. Returns structured deployment outcome (status, disposition, execution_time_ms).
    """
    start_time = time.perf_counter()

    # Normalize deployment_id
    if not deployment_id:
        deployment_id = kwargs.get("deployment_id") or f"dep_{uuid.uuid4().hex[:12]}"
    rejected = _reject_invalid_deployment_id(deployment_id, start_time)
    if rejected:
        return rejected
    lock_wait_seconds = _parse_lock_wait_seconds(kwargs.get("lock_wait_seconds", 3))
    if lock_wait_seconds is None:
        return _invalid_lock_wait(deployment_id, start_time)

    # Normalize JSON proposal if serialized over RPC
    if isinstance(proposal, str):
        try:
            proposal = json.loads(proposal)
        except Exception:
            pass

    proposal_envelope = proposal if (isinstance(proposal, dict) and isinstance(proposal.get("proposal"), dict)) else None
    inner_proposal = proposal_envelope["proposal"] if proposal_envelope is not None else proposal

    # Extract field_def from proposal if needed
    if not field_def and isinstance(inner_proposal, dict):
        changes = inner_proposal.get("changes", [])
        if changes:
            field_def = changes[0]

    # Normalize JSON field_def if serialized over RPC
    if isinstance(field_def, str):
        try:
            field_def = json.loads(field_def)
        except Exception as parse_err:
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "deployment_id": deployment_id,
                "status": "REJECTED",
                "success": False,
                "stage": "VALIDATE",
                "disposition": "INVALID_JSON_PAYLOAD",
                "reason": f"Could not parse field_def JSON string: {parse_err}",
                "execution_time_ms": execution_time_ms,
            }

    if not field_def or not isinstance(field_def, dict) or "fieldname" not in field_def:
        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "deployment_id": deployment_id,
            "status": "REJECTED",
            "success": False,
            "stage": "VALIDATE",
            "disposition": "INVALID_FIELD_DEFINITION",
            "reason": "Missing or invalid 'field_def' (must contain 'fieldname').",
            "execution_time_ms": execution_time_ms,
        }

    # Step 1: Check user roles
    user_roles = _resolve_caller_roles(kwargs)

    user_role_set = set(user_roles)
    if not user_role_set.intersection(AUTHORIZED_DEPLOYMENT_ROLES):
        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        if kwargs.get("raise_on_unauthorized"):
            if frappe and hasattr(frappe, "PermissionError"):
                raise frappe.PermissionError(
                    f"Unauthorized: User roles {sorted(user_role_set)} lack required deployment authority {sorted(AUTHORIZED_DEPLOYMENT_ROLES)}."
                )
            raise PermissionError(
                f"Unauthorized: User roles {sorted(user_role_set)} lack required deployment authority {sorted(AUTHORIZED_DEPLOYMENT_ROLES)}."
            )
        return {
            "deployment_id": deployment_id,
            "status": "REJECTED",
            "success": False,
            "stage": "AUTHORIZATION",
            "disposition": "UNAUTHORIZED_ROLE",
            "reason": (
                f"User does not possess any authorized deployment role. "
                f"Required one of: {sorted(AUTHORIZED_DEPLOYMENT_ROLES)}. Found: {sorted(user_role_set)}"
            ),
            "execution_time_ms": execution_time_ms,
        }

    # Step 1.2: Check intent and route to appropriate declarative engine
    intent = None
    if isinstance(inner_proposal, dict):
        intent = inner_proposal.get("intent")
    if not intent and isinstance(field_def, dict):
        if "property" in field_def or "property_name" in field_def:
            intent = "set_property"
    if not intent:
        intent = kwargs.get("intent")

    forward_kwargs = dict(kwargs)
    forward_kwargs.pop("user_roles", None)
    forward_kwargs.pop("adapter", None)
    forward_kwargs.pop("db", None)
    forward_kwargs.pop("site", None)
    forward_kwargs.pop("site_id", None)
    forward_kwargs.pop("fieldname", None)
    forward_kwargs.pop("property", None)
    forward_kwargs.pop("property_name", None)
    forward_kwargs.pop("value", None)
    forward_kwargs.pop("property_type", None)
    forward_kwargs.pop("workflow_def", None)
    forward_kwargs.pop("workflow", None)
    forward_kwargs.pop("report_def", None)
    forward_kwargs.pop("report", None)
    forward_kwargs.pop("intent", None)

    if intent in ("create_workflow", "workflow_action", "workflow"):
        wf_data = (inner_proposal.get("workflow") or inner_proposal.get("workflow_def")) if isinstance(inner_proposal, dict) else (kwargs.get("workflow_def") or kwargs.get("workflow"))
        return apply_workflow_change(doctype=doctype, deployment_id=deployment_id, workflow_def=wf_data, user_roles=user_roles, **forward_kwargs)

    if intent in ("create_report", "report", "report_builder"):
        rep_data = (inner_proposal.get("report") or inner_proposal.get("report_def")) if isinstance(inner_proposal, dict) else (kwargs.get("report_def") or kwargs.get("report"))
        return apply_report_change(doctype=doctype, deployment_id=deployment_id, report_def=rep_data, user_roles=user_roles, **forward_kwargs)

    if intent in ("set_property", "update_field_property", "property_setter", "quarantine_custom_field") or (isinstance(field_def, dict) and ("property" in field_def or "property_name" in field_def)):
        f_name = (field_def.get("fieldname") if isinstance(field_def, dict) else None) or kwargs.get("fieldname")
        p_name = (field_def.get("property") or field_def.get("property_name") if isinstance(field_def, dict) else None) or kwargs.get("property") or kwargs.get("property_name") or "hidden"
        val = (field_def.get("value") if isinstance(field_def, dict) and "value" in field_def else None)
        if val is None:
            val = kwargs.get("value", 1)
        p_type = (field_def.get("property_type") if isinstance(field_def, dict) else None) or kwargs.get("property_type", "Check")
        return apply_property_setter_change(
            doctype=doctype,
            deployment_id=deployment_id,
            fieldname=f_name,
            property_name=p_name,
            value=val,
            property_type=p_type,
            adapter=adapter or kwargs.get("db"),
            site_id=site_id,
            user_roles=user_roles,
            **forward_kwargs,
        )

    # Step 1.5: Validate mutation safety against Zone rules & Tier 0 invariants
    proposal_payload = dict(inner_proposal) if isinstance(inner_proposal, dict) else {
        "target_doctype": doctype,
        "intent": "add_custom_fields",
        "changes": [field_def],
        "user_roles": list(user_role_set),
    }
    proposal_payload["target_doctype"] = doctype
    proposal_payload["user_roles"] = list(user_role_set)

    try:
        validate_mutation_safety(proposal_payload)
    except ZoneSafetyViolation as exc:
        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "deployment_id": deployment_id,
            "status": "REJECTED",
            "success": False,
            "stage": "SAFETY_GUARDRAILS",
            "disposition": "ZONE_SAFETY_VIOLATION",
            "reason": str(exc),
            "execution_time_ms": execution_time_ms,
        }

    # Step 2: Initialize or resolve deployment adapter
    db = adapter or kwargs.get("db")
    if db is None:
        db = FrappeDeploymentAdapter()

    # Step 3: Resolve site_id and idempotency_key
    site_id, site_rejection = _resolve_site_id(site_id or kwargs.get("site"), deployment_id, start_time)
    if site_rejection:
        return site_rejection

    if not idempotency_key:
        idempotency_key = kwargs.get("idempotency_key") or f"idemp-{deployment_id}"

    # Step 4: Resolve base_revision_hash if not provided
    if base_revision_hash is None:
        try:
            if hasattr(db, "get_doctype_revision_hash") and callable(getattr(db, "get_doctype_revision_hash", None)):
                base_revision_hash = db.get_doctype_revision_hash(doctype)
            elif hasattr(db, "take_snapshot") and callable(getattr(db, "take_snapshot", None)):
                base_revision_hash = db.take_snapshot(doctype, field_def["fieldname"], deployment_id).revision_hash
            else:
                base_revision_hash = "rev_default"
        except RevisionHashError as exc:
            logger.error("DocType revision hash unreadable for %s", deployment_id, exc_info=exc)
            return {
                "deployment_id": deployment_id,
                "status": "REJECTED",
                "success": False,
                "stage": "INSPECT",
                "disposition": "REVISION_HASH_UNAVAILABLE",
                "reason_code": "revision_unavailable",
                "reason": "Cannot read the DocType configuration revision.",
                "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
            }


    # Step 4.5: Verify preview & DDL plan gate binding if preview metadata was provided (BPL-007)
    ddl_plan_container = proposal_envelope if proposal_envelope is not None else proposal
    proposal_ddl_plan = (ddl_plan_container.get("ddl_plan") if isinstance(ddl_plan_container, dict) else None)
    if isinstance(proposal_ddl_plan, dict) and not proposal_ddl_plan.get("is_approved_additive_only", True):
        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "deployment_id": deployment_id,
            "status": "REJECTED",
            "success": False,
            "stage": "INSPECT",
            "disposition": "DDL_PLAN_REJECTED",
            "fallback_action": "QUEUE_FOR_CONTROLLED_ADMIN_DEPLOYMENT",
            "reason": proposal_ddl_plan.get("rejection_reason") or "Previewed DDL plan was not approved additive-only.",
            "doctype": doctype,
            "fieldname": field_def.get("fieldname"),
            "execution_time_ms": execution_time_ms,
        }

    expected_preview_digest = kwargs.get("preview_digest") or (
        ddl_plan_container.get("preview_digest") if isinstance(ddl_plan_container, dict) else None
    )
    expected_statements = kwargs.get("expected_ddl_plan_statements") or (
        proposal_ddl_plan.get("statements") if isinstance(proposal_ddl_plan, dict) else None
    )
    if expected_preview_digest is not None or expected_statements is not None:
        if hasattr(db, "inspect_ddl_plan") and callable(getattr(db, "inspect_ddl_plan", None)):
            live_plan = db.inspect_ddl_plan(doctype, field_def)
        else:
            cols = db.get_table_columns_description(doctype) if hasattr(db, "get_table_columns_description") else None
            live_plan = inspect_frappe_ddl_plan(
                doctype,
                field_def,
                existing_columns_desc=cols,
                offline_simulator=bool(getattr(db, "in_memory", False) or getattr(db, "offline_ddl_simulator", False)),
            )
        if not live_plan.inspectable or not live_plan.is_approved_additive_only:
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "deployment_id": deployment_id,
                "status": "REJECTED",
                "success": False,
                "stage": "INSPECT",
                "disposition": "DDL_PLAN_REJECTED",
                "fallback_action": "QUEUE_FOR_CONTROLLED_ADMIN_DEPLOYMENT",
                "reason": live_plan.rejection_reason or "Live DDL plan gate rejected change.",
                "doctype": doctype,
                "fieldname": field_def.get("fieldname"),
                "execution_time_ms": execution_time_ms,
            }
        if expected_statements is not None and list(live_plan.statements) != list(expected_statements):
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "deployment_id": deployment_id,
                "status": "REJECTED",
                "success": False,
                "stage": "INSPECT",
                "disposition": "PREVIEW_MISMATCH",
                "reason": (
                    f"Live DDL plan {live_plan.statements!r} differs from previewed plan {list(expected_statements)!r}."
                ),
                "doctype": doctype,
                "fieldname": field_def.get("fieldname"),
                "execution_time_ms": execution_time_ms,
            }
        if expected_preview_digest is not None:
            digest_intent = (
                inner_proposal.get("intent")
                if isinstance(inner_proposal, dict) and "intent" in inner_proposal
                else (intent or "add_custom_fields")
            )
            if (
                isinstance(inner_proposal, dict)
                and "changes" in inner_proposal
                and inner_proposal["changes"] != [field_def]
            ):
                execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return {
                    "deployment_id": deployment_id,
                    "status": "REJECTED",
                    "success": False,
                    "stage": "INSPECT",
                    "disposition": "PREVIEW_MISMATCH",
                    "reason": "Deployed field_def does not match previewed proposal changes.",
                    "doctype": doctype,
                    "fieldname": field_def.get("fieldname"),
                    "execution_time_ms": execution_time_ms,
                }
            preview_payload = {
                "doctype": doctype,
                "intent": digest_intent,
                "base_revision_hash": base_revision_hash,
                "changes": [field_def],
                "statements": live_plan.statements,
            }
            computed_digest = hashlib.sha256(
                json.dumps(preview_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if computed_digest != expected_preview_digest:
                execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return {
                    "deployment_id": deployment_id,
                    "status": "REJECTED",
                    "success": False,
                    "stage": "INSPECT",
                    "disposition": "PREVIEW_MISMATCH",
                    "reason": "Preview digest mismatch against current DocType revision or DDL plan.",
                    "doctype": doctype,
                    "fieldname": field_def.get("fieldname"),
                    "execution_time_ms": execution_time_ms,
                }

    # Step 5: Execute 6-stage durable deployment sequence (§8 & §9)
    try:
        outcome = execute_single_field_deployment(
            db=db,
            deployment_id=deployment_id,
            idempotency_key=idempotency_key,
            site_id=site_id,
            doctype=doctype,
            base_revision_hash=base_revision_hash,
            field_def=field_def,
            lock_wait_seconds=lock_wait_seconds,
        )
    except IdempotencyConflictError as conflict_err:
        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        if kwargs.get("raise_on_conflict"):
            raise
        return {
            "deployment_id": deployment_id,
            "status": "REJECTED",
            "success": False,
            "stage": "IDEMPOTENCY_CHECK",
            "disposition": "IDEMPOTENCY_CONFLICT",
            "reason": str(conflict_err),
            "execution_time_ms": execution_time_ms,
        }
    except Exception as exc:
        return _unexpected_failure(exc, "Deployment execution", deployment_id, start_time)

    execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
    outcome["execution_time_ms"] = execution_time_ms
    outcome["success"] = (outcome.get("status") == "APPLIED")
    if "doctype" not in outcome:
        outcome["doctype"] = doctype
    if "fieldname" not in outcome and "fieldname" in field_def:
        outcome["fieldname"] = field_def["fieldname"]

    if "disposition" not in outcome:
        if outcome.get("status") == "REJECTED" and outcome.get("stage") == "ACQUIRE":
            outcome["disposition"] = "LOCK_CONTENTION_OR_TIMEOUT"
        else:
            outcome["disposition"] = outcome.get("stage", outcome.get("status", "UNKNOWN"))

    return outcome


if frappe and hasattr(frappe, "whitelist"):
    apply_configuration_change = frappe.whitelist()(apply_configuration_change)


def apply_property_setter_change(
    doctype: str,
    deployment_id: Optional[str] = None,
    fieldname: Optional[str] = None,
    property_name: Optional[str] = None,
    value: Any = None,
    property_type: str = "Data",
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Whitelisted RPC endpoint for Property Setter metadata mutation.
    Adheres strictly to ADR-001 Rev 2.3 (§5, §8, §9.1):
    1. Checks authenticated user roles: only authorized roles (System Manager,
       Finance Director, Operations Director) can apply changes.
    2. Invokes execute_property_setter_deployment with durable MariaDB advisory lock,
       audit prepare durability, Property Setter creation, cache clear, and metadata reflection.
    3. Returns structured outcome (status, disposition, execution_time_ms).
    """
    start_time = time.perf_counter()

    if not deployment_id:
        deployment_id = kwargs.get("deployment_id") or f"dep_ps_{uuid.uuid4().hex[:12]}"
    rejected = _reject_invalid_deployment_id(deployment_id, start_time)
    if rejected:
        return rejected
    if "lock_wait_seconds" in kwargs and _parse_lock_wait_seconds(kwargs["lock_wait_seconds"]) is None:
        return _invalid_lock_wait(deployment_id, start_time)

    if not property_name and "property" in kwargs:
        property_name = kwargs.get("property")

    user_roles = _resolve_caller_roles(kwargs)

    user_role_set = set(user_roles)
    if not user_role_set.intersection(AUTHORIZED_DEPLOYMENT_ROLES):
        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        if kwargs.get("raise_on_unauthorized"):
            if frappe and hasattr(frappe, "PermissionError"):
                raise frappe.PermissionError(
                    f"Unauthorized: User roles {sorted(user_role_set)} lack required deployment authority {sorted(AUTHORIZED_DEPLOYMENT_ROLES)}."
                )
            raise PermissionError(
                f"Unauthorized: User roles {sorted(user_role_set)} lack required deployment authority {sorted(AUTHORIZED_DEPLOYMENT_ROLES)}."
            )
        return {
            "deployment_id": deployment_id,
            "status": "REJECTED",
            "success": False,
            "stage": "AUTHORIZATION",
            "disposition": "UNAUTHORIZED_ROLE",
            "reason": (
                f"User does not possess any authorized deployment role. "
                f"Required one of: {sorted(AUTHORIZED_DEPLOYMENT_ROLES)}. Found: {sorted(user_role_set)}"
            ),
            "execution_time_ms": execution_time_ms,
        }

    db = kwargs.get("adapter") or kwargs.get("db")
    if db is None:
        db = FrappeDeploymentAdapter()

    site_id, site_rejection = _resolve_site_id(
        kwargs.get("site") or kwargs.get("site_id"), deployment_id, start_time, doctype=doctype)
    if site_rejection:
        return site_rejection

    forward_kwargs = dict(kwargs)
    forward_kwargs.pop("user_roles", None)
    forward_kwargs.pop("adapter", None)
    forward_kwargs.pop("db", None)
    forward_kwargs.pop("site", None)
    forward_kwargs.pop("site_id", None)

    try:
        outcome = execute_property_setter_deployment(
            db=db,
            deployment_id=deployment_id,
            site_id=site_id,
            doctype=doctype,
            fieldname=fieldname,
            property_name=property_name,
            value=value,
            property_type=property_type,
            user_roles=user_roles,
            **forward_kwargs,
        )
    except Exception as exc:
        return _unexpected_failure(exc, "Property Setter execution", deployment_id, start_time)

    return outcome


def apply_workflow_change(
    doctype: str,
    deployment_id: Optional[str] = None,
    workflow_def: Optional[Union[Dict[str, Any], str]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Whitelisted RPC endpoint for applying declarative Workflow definitions.
    Adheres strictly to ADR-001 Rev 2.3 (§10, ADR-006):
    - Strictly checks authorization: only System Manager, Finance Director, Operations Director.
    - Validates state machine invariants, reachability, and deadlock absence.
    - Captures baseline active workflow snapshot for safe rollback.
    - Activates workflow and records durable audit trail.
    """
    start_time = time.perf_counter()

    if not deployment_id:
        deployment_id = kwargs.get("deployment_id") or f"dep_wf_{uuid.uuid4().hex[:12]}"
    rejected = _reject_invalid_deployment_id(deployment_id, start_time, doctype=doctype)
    if rejected:
        return rejected
    if "lock_wait_seconds" in kwargs and _parse_lock_wait_seconds(kwargs["lock_wait_seconds"]) is None:
        return _invalid_lock_wait(deployment_id, start_time)

    if workflow_def is None and "workflow" in kwargs:
        workflow_def = kwargs.get("workflow")

    if isinstance(workflow_def, str):
        try:
            workflow_def = json.loads(workflow_def)
        except Exception as exc:
            return {
                "deployment_id": deployment_id,
                "status": "REJECTED",
                "success": False,
                "stage": "VALIDATE",
                "disposition": "INVALID_JSON_PAYLOAD",
                "reason": f"Failed to parse workflow_def JSON: {exc}",
                "doctype": doctype,
                "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
            }

    if not workflow_def:
        return {
            "deployment_id": deployment_id,
            "status": "REJECTED",
            "success": False,
            "stage": "VALIDATE",
            "disposition": "MISSING_WORKFLOW_PAYLOAD",
            "reason": "Missing workflow_def payload.",
            "doctype": doctype,
            "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
        }

    user_roles = _resolve_caller_roles(kwargs)

    user_role_set = set(user_roles)
    if not user_role_set.intersection(AUTHORIZED_DEPLOYMENT_ROLES):
        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        if kwargs.get("raise_on_unauthorized"):
            if frappe and hasattr(frappe, "PermissionError"):
                raise frappe.PermissionError(
                    f"Unauthorized: User roles {sorted(user_role_set)} lack required deployment authority {sorted(AUTHORIZED_DEPLOYMENT_ROLES)}."
                )
            raise PermissionError(
                f"Unauthorized: User roles {sorted(user_role_set)} lack required deployment authority {sorted(AUTHORIZED_DEPLOYMENT_ROLES)}."
            )
        return {
            "deployment_id": deployment_id,
            "status": "REJECTED",
            "success": False,
            "stage": "AUTHORIZATION",
            "disposition": "UNAUTHORIZED_ROLE",
            "reason": (
                f"User does not possess any authorized deployment role. "
                f"Required one of: {sorted(AUTHORIZED_DEPLOYMENT_ROLES)}. Found: {sorted(user_role_set)}"
            ),
            "doctype": doctype,
            "execution_time_ms": execution_time_ms,
        }

    db = kwargs.get("adapter") or kwargs.get("db")
    if db is None:
        db = FrappeDeploymentAdapter()

    site_id, site_rejection = _resolve_site_id(
        kwargs.get("site") or kwargs.get("site_id"), deployment_id, start_time, doctype=doctype)
    if site_rejection:
        return site_rejection

    forward_kwargs = dict(kwargs)
    forward_kwargs.pop("user_roles", None)
    forward_kwargs.pop("caller_roles", None)
    forward_kwargs.pop("adapter", None)
    forward_kwargs.pop("db", None)
    forward_kwargs.pop("site", None)
    forward_kwargs.pop("site_id", None)

    try:
        outcome = execute_workflow_deployment(
            db=db,
            deployment_id=deployment_id,
            site_id=site_id,
            doctype=doctype,
            workflow_def=workflow_def,
            user_roles=user_roles,
            **forward_kwargs,
        )
    except Exception as exc:
        return _unexpected_failure(exc, "Workflow deployment execution", deployment_id, start_time, doctype=doctype)

    return outcome


def apply_report_change(
    doctype: str,
    deployment_id: Optional[str] = None,
    report_def: Optional[Union[Dict[str, Any], str]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Whitelisted RPC endpoint for deploying declarative Report Builder definitions.
    Adheres strictly to PRD-001 and ADR-001 / ADR-006:
    - Role checks: System Manager, Finance Director, Operations Director, Sales Manager.
    - Validates report definition, columns, filters, and operators.
    - Captures baseline snapshot for 1-click rollback.
    - Creates or updates native Frappe Report document.
    - Durable audit trail in tabChange Engine Audit.
    """
    start_time = time.perf_counter()

    if not deployment_id:
        deployment_id = kwargs.get("deployment_id") or f"dep_rep_{uuid.uuid4().hex[:12]}"
    rejected = _reject_invalid_deployment_id(deployment_id, start_time, doctype=doctype)
    if rejected:
        return rejected
    if "lock_wait_seconds" in kwargs and _parse_lock_wait_seconds(kwargs["lock_wait_seconds"]) is None:
        return _invalid_lock_wait(deployment_id, start_time)

    if report_def is None and "report" in kwargs:
        report_def = kwargs.get("report")

    if isinstance(report_def, str):
        try:
            report_def = json.loads(report_def)
        except Exception as exc:
            return {
                "deployment_id": deployment_id,
                "status": "REJECTED",
                "success": False,
                "stage": "VALIDATE",
                "disposition": "INVALID_JSON_PAYLOAD",
                "reason": f"Failed to parse report_def JSON: {exc}",
                "doctype": doctype,
                "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
            }

    if not report_def:
        return {
            "deployment_id": deployment_id,
            "status": "REJECTED",
            "success": False,
            "stage": "VALIDATE",
            "disposition": "MISSING_REPORT_PAYLOAD",
            "reason": "Missing report_def payload.",
            "doctype": doctype,
            "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
        }

    user_roles = _resolve_caller_roles(kwargs)

    user_role_set = set(user_roles)
    if not user_role_set.intersection(AUTHORIZED_REPORT_DEPLOYMENT_ROLES):
        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        if kwargs.get("raise_on_unauthorized"):
            if frappe and hasattr(frappe, "PermissionError"):
                raise frappe.PermissionError(
                    f"Unauthorized: User roles {sorted(user_role_set)} lack required report deployment authority {sorted(AUTHORIZED_REPORT_DEPLOYMENT_ROLES)}."
                )
            raise PermissionError(
                f"Unauthorized: User roles {sorted(user_role_set)} lack required report deployment authority {sorted(AUTHORIZED_REPORT_DEPLOYMENT_ROLES)}."
            )
        return {
            "deployment_id": deployment_id,
            "status": "REJECTED",
            "success": False,
            "stage": "AUTHORIZATION",
            "disposition": "UNAUTHORIZED_ROLE",
            "reason": (
                f"User does not possess any authorized report deployment role. "
                f"Required one of: {sorted(AUTHORIZED_REPORT_DEPLOYMENT_ROLES)}. Found: {sorted(user_role_set)}"
            ),
            "doctype": doctype,
            "execution_time_ms": execution_time_ms,
        }

    db = kwargs.get("adapter") or kwargs.get("db")
    if db is None:
        db = FrappeDeploymentAdapter()

    site_id, site_rejection = _resolve_site_id(
        kwargs.get("site") or kwargs.get("site_id"), deployment_id, start_time, doctype=doctype)
    if site_rejection:
        return site_rejection

    forward_kwargs = dict(kwargs)
    forward_kwargs.pop("user_roles", None)
    forward_kwargs.pop("caller_roles", None)
    forward_kwargs.pop("adapter", None)
    forward_kwargs.pop("db", None)
    forward_kwargs.pop("site", None)
    forward_kwargs.pop("site_id", None)

    try:
        outcome = execute_report_deployment(
            db=db,
            deployment_id=deployment_id,
            site_id=site_id,
            doctype=doctype,
            report_def=report_def,
            user_roles=user_roles,
            **forward_kwargs,
        )
    except Exception as exc:
        return _unexpected_failure(exc, "Report deployment execution", deployment_id, start_time, doctype=doctype)

    return outcome


def revert_configuration_change(
    deployment_id: str,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Whitelisted RPC endpoint for 1-click rollback and soft quarantine.
    Adheres strictly to ADR-001 Rev 2.3 (§8, §9.1):
    - Strictly checks authorization: only System Manager, Finance Director, Operations Director.
    - If Property Setter: restores baseline property value captured before mutation,
      or removes Property Setter if no baseline existed. Marks ROLLED_BACK.
    - If Custom Field: soft-quarantines by setting hidden=1 and reqd=0 without dropping column.
      Marks QUARANTINED.
    """
    user_roles = _resolve_caller_roles(kwargs)

    db = kwargs.get("adapter") or kwargs.get("db")
    if db is None:
        db = FrappeDeploymentAdapter()

    forward_kwargs = dict(kwargs)
    forward_kwargs.pop("caller_roles", None)
    forward_kwargs.pop("user_roles", None)
    forward_kwargs.pop("adapter", None)
    forward_kwargs.pop("db", None)

    start_time = time.perf_counter()
    try:
        # A deployment that is still PREPARED or RECOVERY_REQUIRED is a hold: an ordinary revert must not clear
        # it (the locked recovery path is CE-SEC-009).
        # It is read only for an authorised caller: an unauthorised one gets the same refusal as for any other
        # revert and learns nothing about the deployment. (Under the target lock: CE-SEC-011.)
        authorised = bool(set(user_roles) & AUTHORIZED_ROLLBACK_ROLES)
        getter = getattr(db, "get_deployment_record", None)
        record = getter(deployment_id) if authorised and callable(getter) else None
        if isinstance(record, dict) and record.get("status") in ("PREPARED", "RECOVERY_REQUIRED"):
            return {
                "deployment_id": deployment_id,
                "status": "REJECTED",
                "success": False,
                "stage": "INSPECT",
                "disposition": "DEPLOYMENT_ON_HOLD",
                "reason_code": "recovery_hold",
                "reason": "The deployment is held for recovery; it cannot be reverted until it is recovered.",
                "doctype": record.get("doctype"),
                "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
            }
        return execute_rollback(
            deployment_id=deployment_id,
            caller_roles=user_roles,
            db=db,
            **forward_kwargs,
        )
    except (DurableEvidenceError, InvalidDeploymentIdError) as exc:
        # The audit store could not be read (or the id is unusable): "unavailable", never "not found".
        logger.error("rollback lookup failed for %s", deployment_id, exc_info=exc)
        return {
            "deployment_id": deployment_id if isinstance(deployment_id, str) and "#" not in deployment_id else None,
            "status": "REJECTED",
            "success": False,
            "stage": "INSPECT",
            "disposition": "ENGINE_UNAVAILABLE",
            "reason_code": "engine_unavailable",
            "reason": "The deployment record could not be read; the rollback was not attempted.",
            "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
        }



if frappe and hasattr(frappe, "whitelist"):
    apply_property_setter_change = frappe.whitelist()(apply_property_setter_change)
    apply_workflow_change = frappe.whitelist()(apply_workflow_change)
    apply_report_change = frappe.whitelist()(apply_report_change)
    revert_configuration_change = frappe.whitelist()(revert_configuration_change)



def enforce_runtime_policies_on_validate(doc, method=None, user_roles: Optional[List[str]] = None) -> PolicyEvaluationResult:
    """
    Lifecycle hook for Document.validate (§4.2).
    Resolves caller roles and evaluates active runtime policies against the document.
    Throws frappe.ValidationError (RuntimePolicyViolation) on violation.
    """
    user_roles = _resolve_caller_roles({"user_roles": user_roles})

    result = policy_catalog.evaluate_validate(doc, user_roles=user_roles, raise_exception=False)
    if not result.allowed:
        policy_id = result.violated_policies[0] if result.violated_policies else "UNKNOWN"
        reason = result.reasons[0] if result.reasons else "Policy validation failed"
        msg = f"Runtime Policy Violation [{policy_id}]: {reason}"
        if frappe and hasattr(frappe, "throw"):
            frappe.throw(msg, exc=RuntimePolicyViolation)
        raise RuntimePolicyViolation(msg, policy_id=policy_id, result=result)
    return result


def enforce_runtime_policies_on_submit(doc, method=None, user_roles: Optional[List[str]] = None) -> PolicyEvaluationResult:
    """
    Lifecycle hook for Document.before_submit (§4.2).
    Evaluates submission gates and submit-time invariants.
    Throws frappe.ValidationError (RuntimePolicyViolation) on violation.
    """
    user_roles = _resolve_caller_roles({"user_roles": user_roles})

    result = policy_catalog.evaluate_submit(doc, user_roles=user_roles, raise_exception=False)
    if not result.allowed:
        policy_id = result.violated_policies[0] if result.violated_policies else "UNKNOWN"
        reason = result.reasons[0] if result.reasons else "Policy submit lock failed"
        msg = f"Runtime Policy Violation [{policy_id}]: {reason}"
        if frappe and hasattr(frappe, "throw"):
            frappe.throw(msg, exc=RuntimePolicyViolation)
        raise RuntimePolicyViolation(msg, policy_id=policy_id, result=result)
    return result


def enforce_runtime_policies_on_update_after_submit(doc, method=None, user_roles: Optional[List[str]] = None) -> PolicyEvaluationResult:
    """
    Lifecycle hook for Document.before_update_after_submit (§4.2).
    Prevents modifying locked or protected fields on submitted documents.
    Throws frappe.ValidationError (RuntimePolicyViolation) on violation.
    """
    user_roles = _resolve_caller_roles({"user_roles": user_roles})

    result = policy_catalog.evaluate_update_after_submit(doc, user_roles=user_roles, raise_exception=False)
    if not result.allowed:
        policy_id = result.violated_policies[0] if result.violated_policies else "UNKNOWN"
        reason = result.reasons[0] if result.reasons else "Policy update-after-submit violation"
        msg = f"Runtime Policy Violation [{policy_id}]: {reason}"
        if frappe and hasattr(frappe, "throw"):
            frappe.throw(msg, exc=RuntimePolicyViolation)
        raise RuntimePolicyViolation(msg, policy_id=policy_id, result=result)
    return result


def get_runtime_policies(
    doctype: Optional[str] = None,
    stage: Optional[str] = None,
    include_inactive: bool = False,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """
    Whitelisted RPC method: returns runtime policies for the caller's site (from the request
    context only) and lifecycle stage. Built-in Tier 0 policies are always included.
    """
    _require_authorized_caller(kwargs)
    from change_engine.guarded_apply.policy_store import policy_store
    if doctype and not include_inactive:
        policies = policy_catalog.get_active_policies(doctype, stage=stage)
    else:
        policies = [
            p for p in policy_store.get_policies(doctype=doctype, stage=stage, active_only=not include_inactive)
            if not policy_catalog.is_protected_policy_id(p.policy_id)
        ]
        for dt, pol_list in policy_catalog._policies.items():
            if doctype and dt != doctype:
                continue
            for p in pol_list:
                if p.active and (not stage or p.stage == stage):
                    policies.append(p)
    return [p.to_dict() for p in policies]


def register_runtime_policy(
    policy_data: Union[str, Dict[str, Any], RuntimePolicy],
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Whitelisted RPC method: registers or updates a Tier 1 runtime policy for the caller's site,
    with revision and audit (CE-SEC-003). Requires System Manager, Finance Director or
    Operations Director. Tier 0 ids are refused; the tier and the site are never caller-set.
    """
    _require_admin_caller(kwargs)
    policy = _policy_from_request(policy_data)
    actor = _policy_actor(kwargs)
    from change_engine.guarded_apply.policy_store import policy_store
    if policy_catalog.is_protected_policy_id(policy.policy_id):
        raise PermissionError(f"Policy id '{policy.policy_id}' is reserved for built-in Tier 0 invariants")
    from change_engine.guarded_apply.policy_expression import validate_condition
    validate_condition(policy.condition_expr)
    saved_policy, audit = policy_store.save_policy(policy, actor=actor)
    policy_catalog.register_policy(saved_policy, actor=actor, persist=False)
    return {
        "success": True,
        "policy_id": saved_policy.policy_id,
        "revision": saved_policy.revision,
        "audit_id": audit.get("audit_id"),
        "action": audit.get("action"),
    }


def unregister_runtime_policy(
    policy_id: str,
    doctype: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Whitelisted RPC method: removes a Tier 1 runtime policy from the caller's site with an
    audit record. Requires admin permission. Built-in Tier 0 invariants cannot be removed.
    """
    _require_admin_caller(kwargs)
    actor = _policy_actor(kwargs)
    removed = policy_catalog.unregister_policy(policy_id, doctype=doctype, actor=actor)
    return {"success": True, "policy_id": policy_id, "removed": removed}


def get_policy_audit_trail(
    policy_id: Optional[str] = None,
    doctype: Optional[str] = None,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """Whitelisted RPC method: the durable audit journal for the caller's site."""
    _require_authorized_caller(kwargs)
    from change_engine.guarded_apply.policy_store import policy_store
    return policy_store.get_audit_trail(policy_id=policy_id, doctype=doctype)


def get_policy_revisions(
    policy_id: str,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """Whitelisted RPC method: historical revisions of a policy on the caller's site."""
    _require_authorized_caller(kwargs)
    from change_engine.guarded_apply.policy_store import policy_store
    return policy_store.get_policy_revisions(policy_id=policy_id)


def evaluate_document_policies(
    doctype: str,
    doc: Dict[str, Any],
    stage: str = "validate",
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Whitelisted RPC method: Evaluates runtime policies against a document preview
    without saving to the database. Roles come from the session inside Frappe; a
    caller-supplied role list is refused (CE-SEC-001, CE-SEC-003).
    """
    _require_authorized_caller(kwargs)
    resolved_roles = _policy_caller_roles(kwargs)
    if isinstance(doc, dict):
        doc = dict(doc)
        doc["doctype"] = doctype

    norm_stage = (stage or "validate").lower()
    if norm_stage in ("submit", "before_submit"):
        res = policy_catalog.evaluate_submit(doc, user_roles=resolved_roles, raise_exception=False)
    elif norm_stage in ("update_after_submit", "before_update_after_submit"):
        res = policy_catalog.evaluate_update_after_submit(doc, user_roles=resolved_roles, raise_exception=False)
    else:
        res = policy_catalog.evaluate_validate(doc, user_roles=resolved_roles, raise_exception=False)

    return res.to_dict()


if frappe and hasattr(frappe, "whitelist"):
    get_runtime_policies = frappe.whitelist()(get_runtime_policies)
    register_runtime_policy = frappe.whitelist()(register_runtime_policy)
    unregister_runtime_policy = frappe.whitelist()(unregister_runtime_policy)
    get_policy_audit_trail = frappe.whitelist()(get_policy_audit_trail)
    get_policy_revisions = frappe.whitelist()(get_policy_revisions)
    evaluate_document_policies = frappe.whitelist()(evaluate_document_policies)
