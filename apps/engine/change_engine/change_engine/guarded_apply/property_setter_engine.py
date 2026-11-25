"""
Change engine Property Setter Mutation Engine
Implements ADR-001 (Rev 2.3) Section 5, Section 8, and Section 9.1:
- Evaluates proposal against validate_mutation_safety() (ensuring Tier 0 invariants cannot be hidden or altered).
- Bounded advisory lock GET_LOCK <= 64 chars respecting MariaDB limits (§7.2).
- Persists baseline snapshot before modification in audit journal (fail-closed durability, §8).
- Applies Property Setter via native frappe.make_property_setter or in-memory deployment adapter.
- Clears DocType cache frappe.clear_cache(doctype=doctype).
- Verifies effective metadata reflection and returns structured outcome (status: APPLIED, disposition: PROPERTY_SETTER_APPLIED).
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set, Union

try:
    import frappe
except ImportError:
    frappe = None

from .safety_guardrails import (
    ALLOWED_PROPERTY_SETTER_PROPERTIES,
    PROHIBITED_CODE_PROPERTIES,
    PROHIBITED_EXPRESSION_PATTERNS,
    TIER_1_GOVERNANCE_ROLES,
    is_restricted_link_doctype,
    validate_mutation_safety,
    ZoneSafetyViolation,
)
from .schema_reconciler import (
    TIMEOUT_NOT_EFFECTIVE,
    IdempotencyConflictError,
    RevisionHashError,
    acquire_scoped_locks,
    begin_fresh_read_view_checked,
    blocked_response,
    compute_canonical_payload_hash,
    engine_refusal,
    release_scoped_locks,
    session_discarded_response,
    set_lock_wait_timeout_checked,
    settle_apply,
)

logger = logging.getLogger(__name__)

# Strict allowlist and default Frappe property_type mapping for approved Property Setter mutations (§5)
PROPERTY_TYPE_MAP: Dict[str, str] = {
    "label": "Data",
    "description": "Text",
    "insert_after": "Data",
    "reqd": "Check",
    "hidden": "Check",
    "read_only": "Check",
    "in_list_view": "Check",
    "in_standard_filter": "Check",
    "bold": "Check",
    "collapsible": "Check",
    "options": "Text",
    "default": "Data",
}


def normalize_property_value(property_name: str, property_type: str, value: Any) -> Any:
    """Normalizes property value based on property type (e.g. Check properties store 0 or 1)."""
    if property_type == "Check" or property_name in ("reqd", "hidden", "read_only", "in_list_view", "in_standard_filter", "bold", "collapsible"):
        if value is None:
            return 0
        if isinstance(value, str):
            return 1 if value.strip() in ("1", "true", "True") else 0
        return 1 if bool(value) else 0
    if value is None:
        return ""
    return str(value)


def _resolve_fieldtype(db: Any, doctype: str, fieldname: Optional[str]) -> Optional[str]:
    """Read the target field's fieldtype from adapter or Frappe metadata; None when unavailable."""
    if not fieldname:
        return None
    if db is not None and hasattr(db, "get_effective_field_property") and callable(getattr(db, "get_effective_field_property", None)):
        try:
            ft = db.get_effective_field_property(doctype, fieldname, "fieldtype")
            if isinstance(ft, str) and ft.strip():
                return ft.strip()
        except Exception:
            pass
    if frappe and hasattr(frappe, "get_meta"):
        try:
            meta = frappe.get_meta(doctype)
            df = meta.get_field(fieldname) if hasattr(meta, "get_field") else None
            ft = getattr(df, "fieldtype", None) if df is not None else None
            if isinstance(ft, str) and ft.strip():
                return ft.strip()
        except Exception:
            pass
    return None


def execute_property_setter_deployment(
    db: Any,
    deployment_id: str,
    site_id: str,
    doctype: str,
    fieldname: Optional[str],
    property_name: str,
    value: Any,
    property_type: str = "Data",
    user_roles: Optional[Union[List[str], Set[str]]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Executes a Property Setter mutation deployment under ADR-001 Rev 2.3 (§5, §8, §9.1).

    1. Evaluates proposal against validate_mutation_safety() and strict PROPERTY_TYPE_MAP allowlist
       (ensuring Tier 0 fields cannot be hidden or altered and unapproved properties / eval: code are blocked).
    2. Acquires MariaDB GET_LOCK advisory lock with <= 64 char identifier.
    3. Checks idempotency binding and recovers from any ongoing RECOVERY_REQUIRED target.
    4. Persists baseline snapshot before modification in audit journal (fail-closed durability).
    5. Applies Property Setter via frappe.make_property_setter or db adapter.
    6. Clears DocType cache via frappe.clear_cache(doctype=doctype).
    7. Verifies effective metadata reflection and returns structured outcome.
    """
    start_time = time.perf_counter()

    # Step 0: Enforce strict property allowlist and normalize property type and value
    try:
        if not property_name or not isinstance(property_name, str):
            raise ZoneSafetyViolation(
                f"Unapproved Field Property Violation (§5): Missing or invalid property_name '{property_name}'."
            )
        prop_lower = property_name.strip().lower()
        if prop_lower in PROHIBITED_CODE_PROPERTIES:
            raise ZoneSafetyViolation(
                f"No-Generated-Code Rule Violation (PRD-001 / ADR-001 §5): Property '{property_name}' "
                f"(such as 'depends_on' with 'eval:' JavaScript) is strictly prohibited."
            )
        if isinstance(value, str) and PROHIBITED_EXPRESSION_PATTERNS.search(value):
            raise ZoneSafetyViolation(
                f"No-Generated-Code Rule Violation (PRD-001 / ADR-001 §5): Executable expression or 'eval:' "
                f"payload in property '{property_name}' ('{value}') is strictly prohibited."
            )

        eff_property_type = property_type
        if property_type == "Data" and property_name in PROPERTY_TYPE_MAP:
            eff_property_type = PROPERTY_TYPE_MAP[property_name]
        normalized_value = normalize_property_value(property_name, eff_property_type, value)

        # Step 1: Evaluates proposal against validate_mutation_safety()
        proposal_payload: Dict[str, Any] = {
            "intent": "set_property",
            "target_doctype": doctype,
            "changes": [
                {
                    "fieldname": fieldname or "",
                    "property": property_name,
                    "value": normalized_value,
                }
            ],
        }
        if user_roles is not None:
            proposal_payload["user_roles"] = list(user_roles)

        validate_mutation_safety(proposal_payload)

        if property_name not in PROPERTY_TYPE_MAP or property_name not in ALLOWED_PROPERTY_SETTER_PROPERTIES:
            raise ZoneSafetyViolation(
                f"Unapproved Field Property Violation (§5): Property '{property_name}' on '{doctype}.{fieldname}' "
                f"is not in the approved property allowlist {sorted(ALLOWED_PROPERTY_SETTER_PROPERTIES)}."
            )

        if property_name == "options":
            target_fieldtype = _resolve_fieldtype(db, doctype, fieldname)
            ft_cf = target_fieldtype.casefold() if target_fieldtype is not None else None
            if ft_cf == "link":
                link_target = str(normalized_value).strip()
                if not link_target:
                    raise ZoneSafetyViolation(
                        f"Invalid Link Target: '{fieldname}' requires a target DocType in 'options'."
                    )
                if is_restricted_link_doctype(link_target):
                    raise ZoneSafetyViolation(
                        f"Restricted Link Target: Cannot link directly to ledger/audit table '{link_target}'."
                    )
            elif ft_cf is None or ft_cf in ("table", "table multiselect"):
                # Fail closed when fieldtype cannot be proven non-Link (or is a DocType-bearing Table field).
                if is_restricted_link_doctype(normalized_value):
                    raise ZoneSafetyViolation(
                        f"Restricted Link Target: Cannot link directly to ledger/audit table '{normalized_value}'."
                    )
    except ZoneSafetyViolation as exc:
        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        if kwargs.get("raise_on_violation") or kwargs.get("raise_on_safety_violation"):
            raise
        return {
            "deployment_id": deployment_id,
            "status": "REJECTED",
            "success": False,
            "stage": "SAFETY_GUARDRAILS",
            "disposition": "ZONE_SAFETY_VIOLATION",
            "reason": str(exc),
            "doctype": doctype,
            "fieldname": fieldname,
            "property_name": property_name,
            "execution_time_ms": execution_time_ms,
        }

    # Step 2: Site-scoped idempotency lock, then the target lock (both <= 64 chars, §7.2), a fresh read view
    # after them, and a lookup that fails blocks (CE-SEC-011: the single-field path's discipline).
    lock_wait_seconds = int(kwargs.get("lock_wait_seconds", 5))
    idempotency_key = kwargs.get("idempotency_key") or f"idemp-{deployment_id}"
    held: List[str] = []
    try:
        locked = acquire_scoped_locks(db, held, site_id, doctype, idempotency_key, lock_wait_seconds)
        if locked is not None:
            code, reason = locked
            return {
                "deployment_id": deployment_id,
                "status": "REJECTED",
                "success": False,
                "stage": "ACQUIRE",
                "disposition": "LOCK_CONTENTION_OR_TIMEOUT",
                "reason_code": code,
                "reason": reason,
                "doctype": doctype,
                "fieldname": fieldname,
                "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
            }

        failed_view = begin_fresh_read_view_checked(db)
        if failed_view:
            return engine_refusal(blocked_response(failed_view), deployment_id, "ENGINE_UNAVAILABLE", start_time,
                                  doctype=doctype, fieldname=fieldname)

        # Step 2.5: Idempotency Binding Check (§7.1)
        payload_hash = compute_canonical_payload_hash(
            site_id,
            doctype,
            {
                "fieldname": fieldname,
                "property": property_name,
                "value": normalized_value,
                "property_type": eff_property_type,
            },
        )

        try:
            existing = db.get_existing_deployment_by_idempotency(site_id, idempotency_key)
        except Exception:
            logger.exception("durable idempotency lookup failed for %s", deployment_id)
            return engine_refusal(blocked_response("idempotency"), deployment_id, "ENGINE_UNAVAILABLE", start_time,
                                  doctype=doctype, fieldname=fieldname)
        if existing is not None:
            if not isinstance(existing, dict) or not isinstance(existing.get("outcome"), dict):
                logger.error("the stored outcome for %s is not the expected shape", deployment_id)
                return engine_refusal(blocked_response("idempotency"), deployment_id, "ENGINE_UNAVAILABLE",
                                      start_time, doctype=doctype, fieldname=fieldname)
            if existing.get("payload_hash") != payload_hash:
                raise IdempotencyConflictError(
                    f"IDEMPOTENCY_CONFLICT: Key '{idempotency_key}' was already used with a different payload."
                )
            cached_outcome = dict(existing["outcome"])
            cached_outcome["execution_time_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
            return cached_outcome

        # Target DocType recovery state gate (§8.1)
        try:
            target_blocked = bool(
                hasattr(db, "is_target_in_recovery_required") and db.is_target_in_recovery_required(site_id, doctype))
        except Exception:
            logger.exception("durable recovery lookup failed for %s", deployment_id)
            return engine_refusal(blocked_response("recovery"), deployment_id, "ENGINE_UNAVAILABLE", start_time,
                                  doctype=doctype, fieldname=fieldname)
        if target_blocked:
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "deployment_id": deployment_id,
                "status": "RECOVERY_REQUIRED",
                "success": False,
                "stage": "INSPECT",
                "disposition": "TARGET_IN_RECOVERY_REQUIRED",
                "reason": f"Target '{doctype}' has an unresolved RECOVERY_REQUIRED state; deployments blocked.",
                "execution_time_ms": execution_time_ms,
            }

        # Step 3: Persists baseline snapshot before modification in audit journal (§8, §9.1)
        had_existing = False
        existing_ps_name = None
        baseline_value = None

        if hasattr(db, "get_property_setter") and callable(getattr(db, "get_property_setter", None)):
            existing_ps = db.get_property_setter(doctype, fieldname, property_name)
            if existing_ps is not None:
                had_existing = True
                baseline_value = existing_ps.get("value")
                existing_ps_name = existing_ps.get("name")
        elif frappe and hasattr(frappe, "db") and hasattr(frappe.db, "get_value"):
            try:
                ps_dict = frappe.db.get_value(
                    "Property Setter",
                    {"doc_type": doctype, "field_name": fieldname, "property": property_name},
                    ["name", "value", "property_type"],
                    as_dict=True,
                )
                if ps_dict:
                    had_existing = True
                    baseline_value = ps_dict.get("value")
                    existing_ps_name = ps_dict.get("name")
            except Exception:
                pass

        if not had_existing:
            if hasattr(db, "get_effective_field_property") and callable(getattr(db, "get_effective_field_property", None)):
                baseline_value = db.get_effective_field_property(doctype, fieldname, property_name)
            elif frappe and hasattr(frappe, "get_meta"):
                try:
                    meta = frappe.get_meta(doctype)
                    df = meta.get_field(fieldname) if hasattr(meta, "get_field") else None
                    if df:
                        baseline_value = getattr(df, property_name, None)
                except Exception:
                    pass

        baseline_snapshot: Dict[str, Any] = {
            "had_existing_property_setter": had_existing,
            "existing_property_setter_name": existing_ps_name,
            "baseline_value": baseline_value,
            "property_type": eff_property_type,
            "property_name": property_name,
        }

        base_revision_hash = kwargs.get("base_revision_hash")
        if not base_revision_hash:
            try:
                if hasattr(db, "get_doctype_revision_hash") and callable(getattr(db, "get_doctype_revision_hash", None)):
                    base_revision_hash = db.get_doctype_revision_hash(doctype)
                elif getattr(db, "in_memory", False) or getattr(db, "offline_ddl_simulator", False):
                    base_revision_hash = "rev_ps_default"  # explicit offline/in-memory mode only
                else:
                    # A live adapter without a readable revision hash must not get a stand-in that
                    # compares equal on both sides (ERP-027).
                    raise RevisionHashError("adapter cannot report the DocType revision hash")
            except RevisionHashError:
                logger.exception("DocType revision hash unreadable for %s", deployment_id)
                return {
                    "deployment_id": deployment_id,
                    "status": "REJECTED",
                    "success": False,
                    "stage": "INSPECT",
                    "disposition": "REVISION_HASH_UNAVAILABLE",
                    "reason_code": "revision_unavailable",
                    "reason": "Cannot read the DocType configuration revision.",
                    "doctype": doctype,
                    "fieldname": fieldname,
                    "property_name": property_name,
                    "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
                }

        prepare_record = {
            "deployment_id": deployment_id,
            "idempotency_key": idempotency_key,
            "payload_hash": payload_hash,
            "site_id": site_id,
            "doctype": doctype,
            "fieldname": fieldname,
            "base_revision_hash": base_revision_hash,
            "deployment_type": "property_setter",
            "property_name": property_name,
            "property_value": normalized_value,
            "property_type": eff_property_type,
            "baseline_value": baseline_value,
            "baseline_snapshot": baseline_snapshot,
            "status": "PREPARED",
        }

        # The session lock-wait timeout is set and read back BEFORE any intent exists: if it is not effective
        # nothing is written and nothing runs (CE-SEC-008).
        if not set_lock_wait_timeout_checked(db, lock_wait_seconds):
            return engine_refusal(TIMEOUT_NOT_EFFECTIVE, deployment_id, "LOCK_TIMEOUT_NOT_EFFECTIVE", start_time,
                                  doctype=doctype, fieldname=fieldname)

        try:
            db.persist_prepare_and_audit_intent(prepare_record)
        except Exception:
            logger.exception("could not persist the deployment intent for %s", deployment_id)
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "deployment_id": deployment_id,
                "status": "FAILED_CLEAN",
                "success": False,
                "stage": "PREPARE",
                "disposition": "AUDIT_PREPARE_FAILED",
                "reason_code": "audit_prepare_failed",
                "reason": "Fail-closed: Could not persist deployment/audit intent.",
                "execution_time_ms": execution_time_ms,
            }

        # Step 4: Applies Property Setter via native frappe.make_property_setter or db adapter
        apply_error: Optional[str] = None
        try:
            if hasattr(db, "apply_property_setter") and callable(getattr(db, "apply_property_setter", None)):
                db.apply_property_setter(
                    doctype=doctype,
                    fieldname=fieldname,
                    property_name=property_name,
                    value=normalized_value,
                    property_type=eff_property_type,
                )
            elif frappe and hasattr(frappe, "make_property_setter"):
                try:
                    frappe.make_property_setter({
                        "doctype": doctype,
                        "fieldname": fieldname,
                        "property": property_name,
                        "value": normalized_value,
                        "property_type": eff_property_type,
                    })
                except TypeError:
                    frappe.make_property_setter(
                        doctype=doctype,
                        fieldname=fieldname,
                        property=property_name,
                        value=normalized_value,
                        property_type=eff_property_type,
                    )
                if hasattr(frappe, "db") and hasattr(frappe.db, "commit"):
                    frappe.db.commit()

            # ADR-001 Rev 2.3 (§9.1): When quarantining a field (hidden=1), also set reqd=0
            # to guarantee that hiding the field does not cause mandatory validation errors on document save.
            if property_name == "hidden" and int(normalized_value) == 1 and fieldname:
                try:
                    if hasattr(db, "apply_property_setter") and callable(getattr(db, "apply_property_setter", None)):
                        db.apply_property_setter(
                            doctype=doctype,
                            fieldname=fieldname,
                            property_name="reqd",
                            value=0,
                            property_type="Check",
                        )
                    elif frappe and hasattr(frappe, "make_property_setter"):
                        try:
                            frappe.make_property_setter({
                                "doctype": doctype,
                                "fieldname": fieldname,
                                "property": "reqd",
                                "value": 0,
                                "property_type": "Check",
                            })
                        except TypeError:
                            frappe.make_property_setter(
                                doctype=doctype,
                                fieldname=fieldname,
                                property="reqd",
                                value=0,
                                property_type="Check",
                            )
                        if hasattr(frappe, "db") and hasattr(frappe.db, "commit"):
                            frappe.db.commit()
                except Exception:
                    pass
        except Exception:
            # The raw error stays in the log.
            logger.exception("Property Setter apply for %s raised", deployment_id)
            apply_error = "apply_failed"

        # A failed apply leaves uncommitted writes: they are rolled back before any outcome is recorded, and a
        # session that cannot be relied on is never finalized (the intent stays as the hold).
        if not settle_apply(db, failed=bool(apply_error)):
            return engine_refusal(session_discarded_response(), deployment_id, "SESSION_DISCARDED", start_time,
                                  doctype=doctype, fieldname=fieldname, property_name=property_name)

        # Step 5: Clears DocType cache frappe.clear_cache(doctype=doctype)
        try:
            if hasattr(db, "clear_doctype_cache") and callable(getattr(db, "clear_doctype_cache", None)):
                db.clear_doctype_cache(doctype)
            if frappe and hasattr(frappe, "clear_cache"):
                frappe.clear_cache(doctype=doctype)
        except Exception:
            pass

        # Step 6: Verifies effective metadata reflection
        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

        if apply_error:
            outcome = {
                "deployment_id": deployment_id,
                "status": "FAILED_CLEAN",
                "success": False,
                "stage": "APPLY",
                "disposition": "PROPERTY_SETTER_APPLY_FAILED",
                "reason_code": apply_error,
                "reason": "The Property Setter could not be applied; the details are in the server log.",
                "doctype": doctype,
                "fieldname": fieldname,
                "property_name": property_name,
                "execution_time_ms": execution_time_ms,
            }
        else:
            verified = True
            if hasattr(db, "get_property_setter") and callable(getattr(db, "get_property_setter", None)):
                ps = db.get_property_setter(doctype, fieldname, property_name)
                if ps is not None:
                    verified = (str(ps.get("value")) == str(normalized_value))
                else:
                    verified = False
            elif frappe and hasattr(frappe, "db") and hasattr(frappe.db, "get_value"):
                try:
                    val = frappe.db.get_value(
                        "Property Setter",
                        {"doc_type": doctype, "field_name": fieldname, "property": property_name},
                        "value",
                    )
                    if val is not None:
                        verified = (str(val) == str(normalized_value))
                    else:
                        verified = False
                except Exception:
                    pass

            if not verified:
                outcome = {
                    "deployment_id": deployment_id,
                    "status": "RECOVERY_REQUIRED",
                    "success": False,
                    "stage": "RECONCILE",
                    "disposition": "METADATA_REFLECTION_MISMATCH",
                    "reason": f"Property Setter on {doctype}.{fieldname}.{property_name} was not reflected in metadata.",
                    "doctype": doctype,
                    "fieldname": fieldname,
                    "property_name": property_name,
                    "execution_time_ms": execution_time_ms,
                }
            else:
                outcome = {
                    "deployment_id": deployment_id,
                    "status": "APPLIED",
                    "success": True,
                    "disposition": "CUSTOM_FIELD_QUARANTINED" if (property_name == "hidden" and int(normalized_value) == 1) else "PROPERTY_SETTER_APPLIED",
                    "doctype": doctype,
                    "fieldname": fieldname,
                    "property_name": property_name,
                    "value": normalized_value,
                    "baseline_value": baseline_value,
                    "execution_time_ms": execution_time_ms,
                }

        # Step 7: Finalize state & audit
        try:
            db.persist_final_outcome_and_audit(
                deployment_id,
                {"payload_hash": payload_hash, "outcome": outcome},
            )
        except Exception:
            logger.exception("finalization of %s failed after the apply ran", deployment_id)
            outcome = {
                **outcome,
                "status": "RECOVERY_REQUIRED",
                "finalization_error": "finalization_failed",
            }

        return outcome
    finally:
        release_scoped_locks(db, held)
