"""
Change engine 1-Click Soft-Rollback & Field Quarantine Engine
Implements ADR-001 (Rev 2.3) Section 8, Section 9, and Section 9.1:
- Role Authorization: strictly verifies caller roles (System Manager, Finance Director, Operations Director).
- Reversible Property Setters: restores baseline property value captured before mutation,
  or deletes the Property Setter if no baseline existed. Marks audit status ROLLED_BACK.
- Quarantinable Custom Fields (§9.1): ADR-001 forbids physical DROP COLUMN in Phase 1 & 2 to prevent data loss.
  Soft-quarantines the field by creating Property Setters with hidden = 1 and reqd = 0. Marks audit status QUARANTINED.
- Clears DocType cache and records durable recovery audit trail.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Set, Union

try:
    import frappe
except ImportError:
    frappe = None

from .safety_guardrails import TIER_1_GOVERNANCE_ROLES
from .schema_reconciler import (
    acquire_scoped_locks,
    begin_fresh_read_view_checked,
    blocked_response,
    engine_refusal,
    release_scoped_locks,
)

logger = logging.getLogger(__name__)

AUTHORIZED_ROLLBACK_ROLES: Set[str] = {
    "System Manager",
    "Finance Director",
    "Operations Director",
    "Sales Manager",
}


def _read_record(db: Any, deployment_id: str) -> Optional[Dict[str, Any]]:
    if hasattr(db, "get_deployment_record") and callable(getattr(db, "get_deployment_record", None)):
        return db.get_deployment_record(deployment_id)
    if hasattr(db, "audit_journal") and isinstance(db.audit_journal, dict):
        return db.audit_journal.get(deployment_id)
    return None


def _already_finished(record: Dict[str, Any], deployment_id: str, start_time: float) -> Optional[Dict[str, Any]]:
    """The answer for a deployment that is already rolled back or quarantined, else ``None``."""
    status = record.get("status")
    if status not in ("ROLLED_BACK", "QUARANTINED"):
        return None
    done = "rolled back" if status == "ROLLED_BACK" else "quarantined"
    return {
        "deployment_id": deployment_id,
        "status": status,
        "success": True,
        "disposition": f"ALREADY_{status}",
        "message": f"Deployment '{deployment_id}' is already {done}.",
        "doctype": record.get("doctype"),
        "fieldname": record.get("fieldname"),
        "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
    }


def execute_rollback(
    deployment_id: str,
    caller_roles: Optional[Union[List[str], Set[str]]] = None,
    db: Any = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Executes a 1-click rollback or quarantine according to ADR-001 Rev 2.3 (§5, §8, §9.1).

    1. Strictly verifies role authorization: only System Manager, Finance Director,
       Operations Director can revert.
    2. Retrieves deployment record from tabChange Engine Audit (or db audit store).
    3. Reversible Property Setters:
       - Restores the baseline property value captured before mutation. If no baseline
         existed, removes the Property Setter.
       - Marks audit status ROLLED_BACK.
    4. Quarantinable Custom Fields (§9.1):
       - ADR-001 forbids physical DROP COLUMN in Phase 1 & 2 to prevent data loss.
       - Soft-quarantines the field by creating Property Setters with hidden = 1 and reqd = 0.
       - Marks audit status QUARANTINED.
    5. Clears DocType cache and returns structured outcome.
    """
    start_time = time.perf_counter()

    # Step 1: Strictly verifies role authorization (§5, §10).
    # Fails closed (CE-SEC-002): a missing session user or a failed lookup means no roles.
    if caller_roles is None:
        caller_roles = []
        try:
            user = getattr(getattr(frappe, "session", None), "user", None) if frappe else None
            if user:
                caller_roles = list(frappe.get_roles(user))
        except Exception:
            caller_roles = []

    caller_role_set = set(caller_roles)
    if not caller_role_set.intersection(AUTHORIZED_ROLLBACK_ROLES):
        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        if kwargs.get("raise_on_unauthorized"):
            if frappe and hasattr(frappe, "PermissionError"):
                raise frappe.PermissionError(
                    f"Unauthorized: Role {sorted(caller_role_set)} lacks rollback authority {sorted(AUTHORIZED_ROLLBACK_ROLES)}."
                )
            raise PermissionError(
                f"Unauthorized: Role {sorted(caller_role_set)} lacks rollback authority {sorted(AUTHORIZED_ROLLBACK_ROLES)}."
            )
        return {
            "deployment_id": deployment_id,
            "status": "REJECTED",
            "success": False,
            "stage": "AUTHORIZATION",
            "disposition": "UNAUTHORIZED_ROLE",
            "reason": (
                f"User roles {sorted(caller_role_set)} lack required rollback authority. "
                f"Required one of: {sorted(AUTHORIZED_ROLLBACK_ROLES)}."
            ),
            "execution_time_ms": execution_time_ms,
        }

    # Step 2: Resolve database adapter
    if db is None:
        from change_engine.api.endpoints import FrappeDeploymentAdapter
        db = FrappeDeploymentAdapter()

    # Step 3: Retrieves deployment record from tabChange Engine Audit (or db audit store). A fresh view first: the
    # read's audit-table check (CREATE TABLE IF NOT EXISTS) commits implicitly, so it must never run over a caller's
    # pending writes; with writes pending the view refuses and nothing is read (CE-SEC-011 review).
    failed_view = begin_fresh_read_view_checked(db)
    if failed_view:
        return engine_refusal(blocked_response(failed_view), deployment_id, "ENGINE_UNAVAILABLE", start_time)
    record = _read_record(db, deployment_id)

    if not record:
        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "deployment_id": deployment_id,
            "status": "REJECTED",
            "success": False,
            "stage": "INSPECT",
            "disposition": "DEPLOYMENT_NOT_FOUND",
            "reason": f"Deployment record '{deployment_id}' was not found in audit store.",
            "execution_time_ms": execution_time_ms,
        }

    finished = _already_finished(record, deployment_id, start_time)
    if finished is not None:
        return finished

    site_id = record.get("site_id") or "default"
    doctype = record.get("doctype", "")
    fieldname = record.get("fieldname", "")

    # Step 4: The target lock (<= 64 chars, §7.2), then a fresh read view, then the record and its hold are read
    # AGAIN under the lock (CE-SEC-011): the unlocked read above only finds which target to lock.
    lock_wait_seconds = int(kwargs.get("lock_wait_seconds", 5))
    held: List[str] = []
    try:
        locked = acquire_scoped_locks(db, held, site_id, doctype, None, lock_wait_seconds)
        if locked is not None:
            code, reason = locked
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "deployment_id": deployment_id,
                "status": "REJECTED",
                "success": False,
                "stage": "ACQUIRE",
                "disposition": "LOCK_CONTENTION_OR_TIMEOUT",
                "reason_code": code,
                "reason": reason.replace("MariaDB GET_LOCK", "MariaDB GET_LOCK for rollback"),
                "doctype": doctype,
                "fieldname": fieldname,
                "execution_time_ms": execution_time_ms,
            }

        failed_view = begin_fresh_read_view_checked(db)
        if failed_view:
            return engine_refusal(blocked_response(failed_view), deployment_id, "ENGINE_UNAVAILABLE", start_time,
                                  doctype=doctype)
        fresh = _read_record(db, deployment_id)
        # A deployment that is still PREPARED or RECOVERY_REQUIRED is a hold: an ordinary revert must not clear it
        # (the locked recovery path is CE-SEC-009). The same record, the same row, now seen under the lock.
        if isinstance(fresh, dict) and fresh.get("status") in ("PREPARED", "RECOVERY_REQUIRED"):
            return {
                "deployment_id": deployment_id,
                "status": "REJECTED",
                "success": False,
                "stage": "INSPECT",
                "disposition": "DEPLOYMENT_ON_HOLD",
                "reason_code": "recovery_hold",
                "reason": "The deployment is held for recovery; it cannot be reverted until it is recovered.",
                "doctype": fresh.get("doctype"),
                "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
            }
        if (not isinstance(fresh, dict) or fresh.get("doctype", "") != doctype
                or (fresh.get("site_id") or "default") != site_id):
            # The record vanished or is not the one whose target was locked: nothing is done.
            return engine_refusal(blocked_response("deployment record"), deployment_id, "ENGINE_UNAVAILABLE",
                                  start_time, doctype=doctype)
        finished = _already_finished(fresh, deployment_id, start_time)  # a concurrent revert finished first
        if finished is not None:
            return finished
        record = fresh  # everything below acts on the record as seen under the lock

        # Step 5: Classify deployment type (Report vs Workflow vs Property Setter vs Custom Field)
        is_report = (
            record.get("deployment_type") == "report"
            or bool(record.get("report_name"))
            or (isinstance(record.get("outcome"), dict) and record["outcome"].get("disposition") == "REPORT_BUILDER_DEPLOYED")
            or (isinstance(record.get("baseline_snapshot"), dict) and "deployed_report_name" in record["baseline_snapshot"])
        )

        is_workflow = (
            record.get("deployment_type") == "workflow"
            or bool(record.get("workflow_name"))
            or (isinstance(record.get("outcome"), dict) and record["outcome"].get("disposition") == "WORKFLOW_STATE_MACHINE_ACTIVATED")
            or (isinstance(record.get("baseline_snapshot"), dict) and "deployed_workflow_name" in record["baseline_snapshot"])
        )

        is_property_setter = (
            record.get("deployment_type") == "property_setter"
            or bool(record.get("property_name"))
            or (isinstance(record.get("outcome"), dict) and record["outcome"].get("disposition") == "PROPERTY_SETTER_APPLIED")
            or (isinstance(record.get("baseline_snapshot"), dict) and "had_existing_property_setter" in record["baseline_snapshot"])
        )

        if is_report:
            # --- REPORT BUILDER ROLLBACK FLOW (PRD-001, ADR-001 Rev 2.3 §10, ADR-006) ---
            baseline_snapshot = record.get("baseline_snapshot") or {}
            deployed_report_name = (
                record.get("report_name")
                or baseline_snapshot.get("deployed_report_name")
                or (record.get("outcome") or {}).get("report_name")
            )
            had_previous = baseline_snapshot.get("had_existing_report", False)
            previous_report_data = baseline_snapshot.get("previous_report_data")

            if had_previous and previous_report_data:
                # 1. Restore previous baseline report
                if hasattr(db, "apply_report") and callable(getattr(db, "apply_report", None)):
                    db.apply_report(deployed_report_name, previous_report_data)
                elif frappe and hasattr(frappe, "get_doc"):
                    r_doc = frappe.get_doc("Report", deployed_report_name)
                    r_doc.update(previous_report_data)
                    r_doc.save(ignore_permissions=True)
                    if hasattr(frappe.db, "commit"):
                        frappe.db.commit()
                disposition = "PREVIOUS_REPORT_RESTORED"
                restored_report = deployed_report_name
            else:
                # 2. If new report, soft-deactivate by setting disabled = 1
                if hasattr(db, "set_report_disabled") and callable(getattr(db, "set_report_disabled", None)):
                    db.set_report_disabled(deployed_report_name, 1)
                elif frappe and hasattr(frappe, "db") and hasattr(frappe.db, "set_value"):
                    frappe.db.set_value("Report", deployed_report_name, "disabled", 1)
                    if hasattr(frappe.db, "commit"):
                        frappe.db.commit()
                disposition = "REPORT_DISABLED"
                restored_report = None

            # Clear DocType cache
            if hasattr(db, "clear_doctype_cache") and callable(getattr(db, "clear_doctype_cache", None)):
                db.clear_doctype_cache(doctype)
            if frappe and hasattr(frappe, "clear_cache"):
                frappe.clear_cache(doctype=doctype)

            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            outcome = {
                "deployment_id": deployment_id,
                "status": "ROLLED_BACK",
                "success": True,
                "disposition": disposition,
                "doctype": doctype,
                "report_name": deployed_report_name,
                "restored_report": restored_report,
                "execution_time_ms": execution_time_ms,
            }

            # Marks audit status ROLLED_BACK
            if hasattr(db, "persist_final_outcome_and_audit") and callable(getattr(db, "persist_final_outcome_and_audit", None)):
                db.persist_final_outcome_and_audit(deployment_id, {"outcome": outcome})

            return outcome

        elif is_workflow:
            # --- WORKFLOW ROLLBACK FLOW (ADR-001 Rev 2.3 §10, ADR-006) ---
            baseline_snapshot = record.get("baseline_snapshot") or {}
            deployed_workflow_name = (
                record.get("workflow_name")
                or baseline_snapshot.get("deployed_workflow_name")
                or (record.get("outcome") or {}).get("workflow_name")
            )
            had_previous = baseline_snapshot.get("had_active_workflow", False)
            previous_workflow_name = baseline_snapshot.get("previous_workflow_name")

            if had_previous and previous_workflow_name:
                # 1. Deactivate deployed workflow
                if hasattr(db, "set_workflow_active") and callable(getattr(db, "set_workflow_active", None)):
                    db.set_workflow_active(deployed_workflow_name, 0)
                elif frappe and hasattr(frappe, "db") and hasattr(frappe.db, "set_value"):
                    frappe.db.set_value("Workflow", deployed_workflow_name, "is_active", 0)

                # 2. Reactivate previously active workflow
                if hasattr(db, "set_workflow_active") and callable(getattr(db, "set_workflow_active", None)):
                    db.set_workflow_active(previous_workflow_name, 1)
                elif frappe and hasattr(frappe, "db") and hasattr(frappe.db, "set_value"):
                    frappe.db.set_value("Workflow", previous_workflow_name, "is_active", 1)

                if frappe and hasattr(frappe, "db") and hasattr(frappe.db, "commit"):
                    frappe.db.commit()

                disposition = "PREVIOUS_WORKFLOW_RESTORED"
                restored_workflow = previous_workflow_name
            else:
                # No previous workflow existed, cleanly deactivate deployed workflow
                if hasattr(db, "set_workflow_active") and callable(getattr(db, "set_workflow_active", None)):
                    db.set_workflow_active(deployed_workflow_name, 0)
                elif frappe and hasattr(frappe, "db") and hasattr(frappe.db, "set_value"):
                    frappe.db.set_value("Workflow", deployed_workflow_name, "is_active", 0)

                if frappe and hasattr(frappe, "db") and hasattr(frappe.db, "commit"):
                    frappe.db.commit()

                disposition = "WORKFLOW_DEACTIVATED"
                restored_workflow = None

            # Clear DocType cache
            if hasattr(db, "clear_doctype_cache") and callable(getattr(db, "clear_doctype_cache", None)):
                db.clear_doctype_cache(doctype)
            if frappe and hasattr(frappe, "clear_cache"):
                frappe.clear_cache(doctype=doctype)

            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            outcome = {
                "deployment_id": deployment_id,
                "status": "ROLLED_BACK",
                "success": True,
                "disposition": disposition,
                "doctype": doctype,
                "workflow_name": deployed_workflow_name,
                "restored_workflow": restored_workflow,
                "execution_time_ms": execution_time_ms,
            }

            # Marks audit status ROLLED_BACK
            if hasattr(db, "persist_final_outcome_and_audit") and callable(getattr(db, "persist_final_outcome_and_audit", None)):
                db.persist_final_outcome_and_audit(deployment_id, {"outcome": outcome})

            return outcome

        elif is_property_setter:
            # --- REVERSIBLE PROPERTY SETTER FLOW ---
            property_name = record.get("property_name")
            if not property_name and isinstance(record.get("outcome"), dict):
                property_name = record["outcome"].get("property_name")

            baseline_snapshot = record.get("baseline_snapshot") or {}
            had_existing = baseline_snapshot.get("had_existing_property_setter", False)
            baseline_value = record.get("baseline_value")
            if baseline_value is None and "baseline_value" in baseline_snapshot:
                baseline_value = baseline_snapshot.get("baseline_value")

            property_type = record.get("property_type") or baseline_snapshot.get("property_type", "Data")

            if had_existing and baseline_value is not None:
                # Restores the baseline property value captured before mutation
                if hasattr(db, "apply_property_setter") and callable(getattr(db, "apply_property_setter", None)):
                    db.apply_property_setter(
                        doctype=doctype,
                        fieldname=fieldname,
                        property_name=property_name,
                        value=baseline_value,
                        property_type=property_type,
                    )
                elif frappe and hasattr(frappe, "make_property_setter"):
                    try:
                        frappe.make_property_setter({
                            "doctype": doctype,
                            "fieldname": fieldname,
                            "property": property_name,
                            "value": baseline_value,
                            "property_type": property_type,
                        })
                    except TypeError:
                        frappe.make_property_setter(
                            doctype=doctype,
                            fieldname=fieldname,
                            property=property_name,
                            value=baseline_value,
                            property_type=property_type,
                        )
                    if hasattr(frappe, "db") and hasattr(frappe.db, "commit"):
                        frappe.db.commit()
                disposition = "PROPERTY_SETTER_RESTORED_BASELINE"
            else:
                # If no baseline existed, removes the Property Setter
                if hasattr(db, "delete_property_setter") and callable(getattr(db, "delete_property_setter", None)):
                    db.delete_property_setter(doctype=doctype, fieldname=fieldname, property_name=property_name)
                elif frappe and hasattr(frappe, "db") and hasattr(frappe.db, "sql"):
                    try:
                        if fieldname:
                            frappe.db.sql(
                                "DELETE FROM `tabProperty Setter` WHERE doc_type = %s AND field_name = %s AND property = %s",
                                (doctype, fieldname, property_name),
                            )
                        else:
                            frappe.db.sql(
                                "DELETE FROM `tabProperty Setter` WHERE doc_type = %s AND (field_name IS NULL OR field_name = '') AND property = %s",
                                (doctype, property_name),
                            )
                        if hasattr(frappe, "db") and hasattr(frappe.db, "commit"):
                            frappe.db.commit()
                    except Exception:
                        pass
                disposition = "PROPERTY_SETTER_REMOVED"

            # Clear DocType cache
            if hasattr(db, "clear_doctype_cache") and callable(getattr(db, "clear_doctype_cache", None)):
                db.clear_doctype_cache(doctype)
            if frappe and hasattr(frappe, "clear_cache"):
                frappe.clear_cache(doctype=doctype)

            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            outcome = {
                "deployment_id": deployment_id,
                "status": "ROLLED_BACK",
                "success": True,
                "disposition": disposition,
                "doctype": doctype,
                "fieldname": fieldname,
                "property_name": property_name,
                "restored_value": baseline_value,
                "removed_setter": not had_existing,
                "execution_time_ms": execution_time_ms,
            }

            # Marks audit status ROLLED_BACK
            if hasattr(db, "persist_final_outcome_and_audit") and callable(getattr(db, "persist_final_outcome_and_audit", None)):
                db.persist_final_outcome_and_audit(deployment_id, {"outcome": outcome})

            return outcome

        else:
            # --- QUARANTINABLE CUSTOM FIELD FLOW (§9.1) ---
            # ADR-001 forbids physical DROP COLUMN in Phase 1 & 2 to prevent data loss.
            # Soft-quarantines the field by creating Property Setters with hidden = 1 and reqd = 0.

            # 1. Soft-quarantine: hidden = 1
            if hasattr(db, "apply_property_setter") and callable(getattr(db, "apply_property_setter", None)):
                db.apply_property_setter(
                    doctype=doctype,
                    fieldname=fieldname,
                    property_name="hidden",
                    value=1,
                    property_type="Check",
                )
            elif frappe and hasattr(frappe, "make_property_setter"):
                try:
                    frappe.make_property_setter({
                        "doctype": doctype,
                        "fieldname": fieldname,
                        "property": "hidden",
                        "value": "1",
                        "property_type": "Check",
                    })
                except TypeError:
                    frappe.make_property_setter(
                        doctype=doctype,
                        fieldname=fieldname,
                        property="hidden",
                        value="1",
                        property_type="Check",
                    )
                if hasattr(frappe, "db") and hasattr(frappe.db, "commit"):
                    frappe.db.commit()

            # 2. Soft-quarantine: reqd = 0
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
                        "value": "0",
                        "property_type": "Check",
                    })
                except TypeError:
                    frappe.make_property_setter(
                        doctype=doctype,
                        fieldname=fieldname,
                        property="reqd",
                        value="0",
                        property_type="Check",
                    )
                if hasattr(frappe, "db") and hasattr(frappe.db, "commit"):
                    frappe.db.commit()

            # 3. Clear DocType cache
            if hasattr(db, "clear_doctype_cache") and callable(getattr(db, "clear_doctype_cache", None)):
                db.clear_doctype_cache(doctype)
            if frappe and hasattr(frappe, "clear_cache"):
                frappe.clear_cache(doctype=doctype)

            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            outcome = {
                "deployment_id": deployment_id,
                "status": "QUARANTINED",
                "success": True,
                "disposition": "CUSTOM_FIELD_QUARANTINED",
                "doctype": doctype,
                "fieldname": fieldname,
                "actions": [
                    {"property": "hidden", "value": 1, "property_type": "Check"},
                    {"property": "reqd", "value": 0, "property_type": "Check"},
                ],
                "physical_column_dropped": False,
                "execution_time_ms": execution_time_ms,
            }

            # Marks audit status QUARANTINED
            if hasattr(db, "persist_final_outcome_and_audit") and callable(getattr(db, "persist_final_outcome_and_audit", None)):
                db.persist_final_outcome_and_audit(deployment_id, {"outcome": outcome})

            return outcome

    finally:
        release_scoped_locks(db, held)
