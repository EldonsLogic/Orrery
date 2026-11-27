"""
Change engine Guarded Schema Deployment & Non-Destructive Snapshot Reconciler
Implements ADR-001 (Rev 2.3) Sections 6, 7, 8, and 9:
- Bounded, collision-resistant MariaDB GET_LOCK identifier (<= 64 chars) with 1 / 0 / NULL handling (§7.2)
- Immutable Idempotency Key + Canonical Payload Hash conflict detection (§7.1)
- Approved-Only DDL Plan Inspection Gate before synchronous execution (§6.1 & §6.2)
- 6-Stage Durable Deployment Sequence surviving MariaDB implicit commits (§8)
- Non-Destructive Exhaustive Snapshot Reconciliation (§9): Phase 1 NEVER auto-deletes orphaned metadata
  or drops physical columns; all uncertain or divergent states enter `RECOVERY_REQUIRED`.
"""

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Protocol, Tuple

logger = logging.getLogger(__name__)


class RevisionHashError(RuntimeError):
    """The live DocType revision hash could not be read; callers must fail closed."""


class IdempotencyConflictError(Exception):
    """Raised when an idempotency_key is reused with a different canonical request payload."""
    pass


class DeploymentIntentConflictError(RuntimeError):
    """CE-SEC-008: a Stage 3 intent for this deployment id already exists; it is never overwritten.

    ``reason`` is ``binding_mismatch`` (another key, payload, site, target or plan) or
    ``already_recorded`` (the same binding: the earlier attempt is replayed or recovered, never
    re-run under a second intent).
    """

    def __init__(self, deployment_id: str, reason: str):
        super().__init__(f"Deployment intent '{deployment_id}' already exists ({reason}); refusing to overwrite it")
        self.deployment_id = deployment_id
        self.reason = reason


class DurableEvidenceError(RuntimeError):
    """CE-SEC-008: durable deployment evidence (baseline, plan, dispatch journal) is missing or malformed."""


class InvalidDeploymentIdError(ValueError):
    """CE-SEC-008: a caller-chosen deployment id or idempotency key could reach the evidence namespace."""


# New deployment ids and idempotency keys are canonical: a short ASCII charset, no spaces. The id limit leaves
# room for every derived name (``idemp-<id>``, ``<id>#evidence``, ``<id>#d0001``) inside VARCHAR(140). Because the
# charset is ASCII with no spaces, MariaDB's case-insensitive, space-padded comparison is the only equivalence
# left, and the lock names fold exactly that (``_collation_fold``): one equality for locks, lookups and rows.
MAX_DEPLOYMENT_ID_LENGTH = 100
MAX_IDEMPOTENCY_KEY_LENGTH = 128
MAX_SITE_ID_LENGTH = 140  # VARCHAR(140)
_CANONICAL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:\-]*")


def caller_id_problem(value: Any, max_length: int = MAX_DEPLOYMENT_ID_LENGTH) -> Optional[str]:
    """Why a NEW caller-chosen deployment id or idempotency key is refused, or ``None``.

    Evidence rows live next to the main rows as ``<deployment_id>#...``; the charset keeps every caller value
    out of that namespace and out of the collation's equivalence classes.
    """
    if not isinstance(value, str) or not value or len(value) > max_length:
        return f"must be a non-empty string of at most {max_length} characters"
    if not _CANONICAL_ID.fullmatch(value):
        return "may only use letters, digits and _ . : - and must start with a letter or digit"
    return None


def evidence_namespace_problem(value: Any) -> Optional[str]:
    """Lookups, finalizers and rollback accept any EXISTING main row id (older ids may be longer or looser),
    but never one inside the evidence namespace."""
    if not isinstance(value, str) or not value:
        return "must be a non-empty string"
    if "#" in value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        return "must not contain '#' or control characters"
    return None


def _collation_fold(value: str) -> str:
    """How the audit table's default collations compare text: ignoring case and trailing spaces."""
    return str(value).rstrip(" ").lower()


class SessionDiscardedError(RuntimeError):
    """CE-SEC-008: the database session was discarded (a rollback or a lock release could not be verified);
    nothing may commit, finalize or rely on a lock through it. The reconciler holds the deployment instead."""


class LockTimeoutError(RuntimeError):
    """CE-SEC-008: the session lock-wait timeout could not be set or its effective value read back."""


@dataclass(frozen=True)
class ExhaustiveSnapshot:
    has_meta: bool
    has_col: bool
    definition_matches: bool = True
    indexes_unchanged: bool = True
    provenance_matches: bool = True
    unapproved_side_effects: bool = False
    revision_hash: str = ""
    error_code: Optional[str] = None  # set when the snapshot could not be taken: a refusal, not a revision change


from .ddl_plan_gate import (
    APPROVED_DDL_REGEX,
    DDLPlanInspection,
    inspect_frappe_ddl_plan,
    validate_ddl_plan,
)


class Rev23DeploymentAdapter(Protocol):
    """Protocol for Frappe v15 + MariaDB 10.11 deployment execution under ADR-001 Rev 2.3."""

    def begin_fresh_read_view(self) -> None: ...
    def acquire_advisory_lock(self, lock_key: str, wait_seconds: int) -> Optional[int]: ...
    def release_advisory_lock(self, lock_key: str) -> None: ...
    def is_target_in_recovery_required(self, site_id: str, doctype: str) -> bool: ...
    def get_existing_deployment_by_idempotency(self, site_id: str, idempotency_key: str) -> Optional[Dict[str, Any]]: ...
    def take_snapshot(self, doctype: str, fieldname: str, expected_deployment_id: str) -> ExhaustiveSnapshot: ...
    def inspect_ddl_plan(self, doctype: str, field_def: Dict[str, Any]) -> DDLPlanInspection: ...
    def persist_prepare_and_audit_intent(self, record: Dict[str, Any]) -> None: ...
    def persist_final_outcome_and_audit(self, deployment_id: str, outcome: Dict[str, Any]) -> None: ...
    def set_lock_wait_timeout(self, seconds: int) -> None: ...
    def apply_native_custom_field(self, deployment_id: str, doctype: str, field_def: Dict[str, Any]) -> None: ...
    def clear_doctype_cache(self, doctype: str) -> None: ...


def make_bounded_lock_key(site_id: str, doctype: str) -> str:
    """
    Maps (site_id, doctype) to a bounded, collision-resistant lock identifier <= 64 chars
    respecting MariaDB GET_LOCK limits and avoiding raw string concatenation (§7.2).
    """
    digest = hashlib.sha256(f"{_collation_fold(site_id)}\x00{_collation_fold(doctype)}".encode("utf-8")).hexdigest()[:48]
    return f"ce:v1:{digest}"


def make_idempotency_lock_key(site_id: str, idempotency_key: str) -> str:
    """Site-scoped lock for one idempotency key (<= 64 chars), distinct from every target lock."""
    digest = hashlib.sha256(
        f"{_collation_fold(site_id)}\x00idem\x00{_collation_fold(idempotency_key)}".encode("utf-8")).hexdigest()[:40]
    return f"ce:v1:idem:{digest}"


def _release_checked(db: Any, lock_key: str) -> bool:
    """Release one advisory lock; ``True`` only when it is verified released. A release that fails or raises
    never escapes past the response, but the caller must then discard the session."""
    try:
        return db.release_advisory_lock(lock_key) is not False
    except Exception:
        logger.exception("could not release advisory lock %s", lock_key)
        return False


def _discard_session(db: Any) -> None:
    mark = getattr(db, "mark_session_unusable", None)
    if callable(mark):
        try:
            mark()
        except Exception:
            logger.exception("could not discard the database session")


def acquire_scoped_locks(
    db: Any, held: List[str], site_id: str, doctype: str, idempotency_key: Optional[str], wait_seconds: int
) -> Optional[Tuple[str, str]]:
    """Take the site-scoped idempotency lock (when there is a key) and then the target lock, in that order, for the
    non-DDL engines and the revert (CE-SEC-011). Every lock taken is appended to ``held`` BEFORE the next one is
    tried, so the caller's ``finally: release_scoped_locks(db, held)`` frees whatever is held however this returns
    or raises. Returns ``None`` when every lock is held, else ``(reason_code, reason)`` for the refusal; the
    database's own error text is logged, never returned."""
    keys = [make_bounded_lock_key(site_id, doctype)]
    if idempotency_key is not None:
        keys.insert(0, make_idempotency_lock_key(site_id, idempotency_key))
    for key in keys:
        try:
            result = db.acquire_advisory_lock(key, wait_seconds=wait_seconds)
        except Exception:
            logger.exception("advisory lock acquisition raised for %s", key)
            return "engine_unavailable", "Could not acquire the MariaDB advisory lock (database error)."
        if result != 1:
            detail = "Lock wait timeout (0)" if result == 0 else "Database lock error (NULL)"
            return ("lock_timeout" if result == 0 else "engine_unavailable",
                    f"Could not acquire MariaDB GET_LOCK ({detail})")
        held.append(key)
    return None


def release_scoped_locks(db: Any, held: List[str]) -> None:
    """The ``finally`` of the guarded sequence for a caller that holds ``held``: the session's own
    ``lock_wait_timeout`` is restored, every lock is released and verified (newest first), and a restore or a
    release that is not verified discards the session, because a lock that may still be held keeps blocking others
    for as long as the connection lives. Never raises."""
    unusable = False
    restore = getattr(db, "restore_lock_wait_timeout", None)
    if callable(restore):
        try:
            unusable = restore() is False or unusable
        except Exception:
            logger.exception("could not restore the session lock_wait_timeout")
            unusable = True
    for key in reversed(held):
        unusable = not _release_checked(db, key) or unusable
    if unusable:
        _discard_session(db)


def begin_fresh_read_view_checked(db: Any) -> Optional[str]:
    """Open a fresh read view after the locks; ``None`` when it is open (or the adapter has no such view), else the
    name of the lookup that failed, for ``blocked_response``. The error is logged, never returned."""
    refresh = getattr(db, "begin_fresh_read_view", None)
    if not callable(refresh):
        return None
    try:
        refresh()
    except Exception:
        logger.exception("could not open a fresh read view")
        return "read view"
    return None


def set_lock_wait_timeout_checked(db: Any, seconds: int) -> bool:
    """Set the session ``lock_wait_timeout`` and read it back BEFORE any intent exists (CE-SEC-008); ``False`` when
    it did not verify, and the caller refuses with ``lock_timeout_not_effective``."""
    setter = getattr(db, "set_lock_wait_timeout", None)
    if not callable(setter):
        return True
    try:
        setter(seconds)
    except Exception:
        logger.exception("lock_wait_timeout could not be set and verified")
        return False
    return True


def settle_apply(db: Any, failed: bool) -> bool:
    """After the apply step: when it failed, roll back whatever it left uncommitted; then say whether the session
    can still be relied on. ``False`` when the rollback failed or the session was discarded (the caller then holds
    the deployment and never finalizes it); ``True`` when a final outcome may be recorded (CE-SEC-011).
    Never raises."""
    rollback = getattr(db, "_rollback_durable", None)
    if failed and callable(rollback) and getattr(db, "in_memory", False) is not True:
        try:
            if rollback() is False:
                return False
        except Exception:
            logger.exception("could not roll back the failed apply")
            return False
    return getattr(db, "session_unusable", False) is not True


def read_apply_target(db: Any, kind: str, doctype: str, name: Any, fieldname: Any = None,
                      property_name: Any = None) -> Optional[Tuple[Any, ...]]:
    """The committed state of a non-DDL apply's target, for the before/after comparison that alone allows
    FAILED_CLEAN (CE-SEC-011 review); ``None`` when it cannot be read, which never compares as unchanged.
    Never raises."""
    reader = getattr(db, "read_apply_target", None)
    if not callable(reader):
        return () if getattr(db, "in_memory", False) is True else None
    try:
        return reader(kind, doctype, name, fieldname, property_name)
    except Exception:
        logger.exception("could not read the deployment target back")
        return None


def target_unchanged(before: Optional[Tuple[Any, ...]], after: Optional[Tuple[Any, ...]]) -> bool:
    """A failed apply is clean only when the target read the same before the intent and after the rollback."""
    return before is not None and after is not None and before == after


def session_discarded_response() -> Dict[str, Any]:
    """The refusal for a deployment whose session was discarded: nothing is finalized, the intent stays as the hold."""
    return {
        "status": "RECOVERY_REQUIRED",
        "stage": "APPLY",
        "reason_code": "session_discarded",
        "reason": "The database session was discarded before finalization; the deployment is held for recovery.",
    }


def blocked_response(lookup: str) -> Dict[str, Any]:
    """The refusal for a durable lookup that failed: it blocks, and says nothing of the error."""
    return {
        "status": "REJECTED",
        "stage": "INSPECT",
        "reason_code": "engine_unavailable",
        "reason": f"Fail-closed: the durable {lookup} lookup failed; deployment blocked.",
    }


def engine_refusal(base: Dict[str, Any], deployment_id: str, disposition: str, start_time: float,
                   **extra: Any) -> Dict[str, Any]:
    """A non-DDL engine's refusal: a ``base`` (code and fixed text) in the engine's response shape."""
    return {
        **base,
        "deployment_id": deployment_id,
        "success": False,
        "disposition": disposition,
        **extra,
        "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
    }


TIMEOUT_NOT_EFFECTIVE: Dict[str, Any] = {
    "status": "REJECTED",
    "stage": "PREPARE",
    "reason_code": "lock_timeout_not_effective",
    "reason": "Fail-closed: lock_wait_timeout could not be set and verified.",
}


def compute_canonical_payload_hash(site_id: str, doctype: str, field_def: Dict[str, Any]) -> str:
    """Computes a deterministic SHA-256 hash of the canonical request payload (§7.1)."""
    canonical = json.dumps(
        {"site_id": site_id, "doctype": doctype, "field_def": field_def},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def execute_single_field_deployment(
    db: Rev23DeploymentAdapter,
    deployment_id: str,
    idempotency_key: str,
    site_id: str,
    doctype: str,
    base_revision_hash: str,
    field_def: Dict[str, Any],
    lock_wait_seconds: int = 3,
    approved_plan: Optional[DDLPlanInspection] = None,
) -> Dict[str, Any]:
    """
    Executes the 6-Stage Durable Deployment Sequence defined in ADR-001 Rev 2.3 (§8 & §9).

    ``approved_plan`` lets a caller that has already judged the plan itself (the runtime backend's decimal
    phantom-MODIFY case, where Frappe's own diff is not additive-only) supply the statements; every other
    stage, lock, lookup and journal rule is the same. Every statement is still checked against the approved
    plan at dispatch.
    """
    fieldname = field_def["fieldname"]
    for label, value, code, limit in (
        ("deployment id", deployment_id, "invalid_deployment_id", MAX_DEPLOYMENT_ID_LENGTH),
        ("idempotency key", idempotency_key, "invalid_idempotency_key", MAX_IDEMPOTENCY_KEY_LENGTH),
        ("site identity", site_id, "invalid_site_id", MAX_SITE_ID_LENGTH),
    ):
        problem = caller_id_problem(value, limit)
        if problem:
            return {
                "deployment_id": None,
                "status": "REJECTED",
                "stage": "VALIDATE",
                "reason_code": code,
                "reason": f"The {label} {problem}.",
            }
    payload_hash = compute_canonical_payload_hash(site_id, doctype, field_def)
    lock_key = make_bounded_lock_key(site_id, doctype)
    idem_lock_key = make_idempotency_lock_key(site_id, idempotency_key)

    # Stage 1: Acquire verified connection-scoped advisory locks (1 = acquired, 0 = timeout, None = error):
    # the site-scoped idempotency lock first, so one key cannot reserve two targets, then the target lock.
    # Both are acquired inside the try, so whatever is held is released whichever way this returns or raises.
    held: List[str] = []
    try:
        for key in (idem_lock_key, lock_key):
            try:
                lock_result = db.acquire_advisory_lock(key, wait_seconds=5)
            except Exception:
                logger.exception("advisory lock acquisition raised for %s", deployment_id)
                return {
                    "deployment_id": deployment_id,
                    "status": "REJECTED",
                    "stage": "ACQUIRE",
                    "reason_code": "engine_unavailable",
                    "reason": "Could not acquire the MariaDB advisory lock (database error).",
                }
            if lock_result != 1:
                reason = "Lock wait timeout (0)" if lock_result == 0 else "Database lock error (NULL)"
                return {
                    "deployment_id": deployment_id,
                    "status": "REJECTED",
                    "stage": "ACQUIRE",
                    "reason": f"Could not acquire MariaDB GET_LOCK ({reason})",
                }
            held.append(key)

        bind = getattr(db, "bind_request_site", None)
        if callable(bind):
            bind(site_id)

        # Everything below reads fresh: a read view opened before the locks could miss a row another session
        # committed while this one waited for them. A view that cannot be refreshed blocks.
        refresh = getattr(db, "begin_fresh_read_view", None)
        if callable(refresh):
            try:
                refresh()
            except Exception as lookup_exc:
                return _blocked_by_lookup_failure(deployment_id, "read view", lookup_exc)

        # Step 1.5: Check Idempotency Binding (§7.1). A failed lookup blocks; it is never "no earlier attempt".
        try:
            existing = db.get_existing_deployment_by_idempotency(site_id, idempotency_key)
        except Exception as lookup_exc:
            return _blocked_by_lookup_failure(deployment_id, "idempotency", lookup_exc)
        if existing is not None:
            replay = _replay_or_conflict(existing, payload_hash, idempotency_key)
            if replay is None:
                return _blocked_by_lookup_failure(deployment_id, "idempotency", ValueError("malformed stored outcome"))
            return replay

        # Block if target DocType already has an unresolved RECOVERY_REQUIRED deployment (§8.1)
        try:
            target_blocked = db.is_target_in_recovery_required(site_id, doctype)
        except Exception as lookup_exc:
            return _blocked_by_lookup_failure(deployment_id, "recovery", lookup_exc)
        if target_blocked:
            return {
                "deployment_id": deployment_id,
                "status": "RECOVERY_REQUIRED",
                "stage": "INSPECT",
                "reason": f"Target '{doctype}' has an unresolved RECOVERY_REQUIRED state; deployments blocked.",
            }

        # Stage 2: Inspect Revision, Before-Snapshot, and Approved-Only DDL Plan (§6.1, §8)
        before = db.take_snapshot(doctype, fieldname, expected_deployment_id=deployment_id)

        if getattr(before, "error_code", None):
            # The snapshot (or the evidence behind it) could not be read: a refusal with its own code, never a
            # "the revision changed" that would send the caller to retry.
            return {
                "deployment_id": deployment_id,
                "status": "REJECTED",
                "stage": "INSPECT",
                "reason_code": before.error_code,
                "reason": "Fail-closed: the table snapshot or its durable evidence could not be read.",
            }

        if before.revision_hash != base_revision_hash:
            return {
                "deployment_id": deployment_id,
                "status": "REVISION_CONFLICT",
                "stage": "INSPECT",
                "reason": "DocType configuration revision changed externally before deployment.",
            }

        # Pre-existing partial or conflicting state check (§5.1, §9)
        if before.has_meta or before.has_col:
            status = "RECOVERY_REQUIRED" if (before.has_meta != before.has_col) else "REJECTED"
            return {
                "deployment_id": deployment_id,
                "status": status,
                "stage": "INSPECT",
                "reason": (
                    f"Pre-existing field or divergence on '{doctype}.{fieldname}' "
                    f"(has_meta={before.has_meta}, has_col={before.has_col})."
                ),
            }

        # Mandatory DDL Plan Safety Gate (§6.1 & §6.2), unless the caller supplied its own judged plan
        if approved_plan is not None:
            problem = _approved_plan_problem(approved_plan, doctype, fieldname)
            ddl_plan = approved_plan if problem is None else DDLPlanInspection(
                inspectable=True, statements=list(approved_plan.statements), is_approved_additive_only=False,
                rejection_reason=problem, reason_code="invalid_approved_plan")
        else:
            if hasattr(db, "inspect_ddl_plan") and callable(getattr(db, "inspect_ddl_plan", None)):
                ddl_plan = db.inspect_ddl_plan(doctype, field_def)
            else:
                existing_cols = None
                if hasattr(db, "get_table_columns_description") and callable(getattr(db, "get_table_columns_description", None)):
                    existing_cols = db.get_table_columns_description(doctype)
                ddl_plan = inspect_frappe_ddl_plan(
                    doctype,
                    field_def,
                    existing_columns_desc=existing_cols,
                    offline_simulator=bool(getattr(db, "in_memory", False) or getattr(db, "offline_ddl_simulator", False)),
                )

            # Enforce fail-closed gate validation on planned statements (§6.1 & §6.2)
            if ddl_plan.inspectable and ddl_plan.is_approved_additive_only:
                is_valid, validation_reason = validate_ddl_plan(ddl_plan.statements)
                if not is_valid:
                    ddl_plan = DDLPlanInspection(
                        inspectable=True,
                        statements=ddl_plan.statements,
                        is_approved_additive_only=False,
                        rejection_reason=validation_reason,
                    )

        if not ddl_plan.inspectable or not ddl_plan.is_approved_additive_only:
            return {
                "deployment_id": deployment_id,
                "status": "REJECTED",
                "stage": "INSPECT",
                "fallback_action": "QUEUE_FOR_CONTROLLED_ADMIN_DEPLOYMENT",
                "reason": ddl_plan.rejection_reason or "Unprovable or non-additive DDL plan from updatedb().",
                **({"reason_code": ddl_plan.reason_code} if ddl_plan.reason_code == "invalid_approved_plan" else {}),
            }

        # The session lock-wait timeout is set and read back BEFORE any intent exists: if it is not
        # effective nothing is written and nothing runs (CE-SEC-008).
        try:
            db.set_lock_wait_timeout(lock_wait_seconds)
        except Exception:
            logger.exception("lock_wait_timeout could not be set and verified for %s", deployment_id)
            return {
                "deployment_id": deployment_id,
                "status": "REJECTED",
                "stage": "PREPARE",
                "reason_code": "lock_timeout_not_effective",
                "reason": "Fail-closed: lock_wait_timeout could not be set and verified.",
            }

        # Stage 3: Prepare — Commit durable intent, payload hash, DDL plan evidence, and audit BEFORE DDL (§8, §10)
        try:
            db.persist_prepare_and_audit_intent({
                "deployment_id": deployment_id,
                "idempotency_key": idempotency_key,
                "payload_hash": payload_hash,
                "site_id": site_id,
                "doctype": doctype,
                "fieldname": fieldname,
                "base_revision_hash": base_revision_hash,
                "ddl_plan_statements": ddl_plan.statements,
                "status": "PREPARED",
            })
        except DeploymentIntentConflictError as conflict:
            # A strict insert met an older record: it is untouched and nothing runs.
            if conflict.reason == "already_recorded":
                # The same request is already on record: return what it produced (or its hold), never a bare refusal.
                try:
                    recorded = db.get_existing_deployment_by_idempotency(site_id, idempotency_key)
                except Exception as lookup_exc:
                    return _blocked_by_lookup_failure(deployment_id, "idempotency", lookup_exc)
                if recorded is not None and recorded.get("payload_hash") == payload_hash:
                    replay = _replay_or_conflict(recorded, payload_hash, idempotency_key)
                    if replay is not None:
                        return replay
                return {
                    "deployment_id": deployment_id,
                    "status": "RECOVERY_REQUIRED",
                    "stage": "PREPARE",
                    "reason_code": "intent_already_recorded",
                    "reason": "Fail-closed: this deployment is already on record; it is held until it is recovered.",
                }
            return {
                "deployment_id": deployment_id,
                "status": "REJECTED",
                "stage": "PREPARE",
                "reason_code": f"intent_{conflict.reason}",
                "reason": "Fail-closed: an earlier deployment record with this id exists and was left untouched.",
            }
        except Exception:
            # Fail closed before any schema mutation is attempted
            logger.exception("could not persist the deployment intent for %s", deployment_id)
            return {
                "deployment_id": deployment_id,
                "status": "FAILED_CLEAN",
                "stage": "PREPARE",
                "reason_code": "audit_prepare_failed",
                "reason": "Fail-closed: Could not persist deployment/audit intent.",
            }

        # Stage 4: Apply Native Frappe Configuration Operation (§8)
        apply_error: Optional[str] = None
        try:
            db.apply_native_custom_field(deployment_id, doctype, field_def)
        except Exception:
            # Do NOT assume rollback on exception; proceed to Stage 5 Reconciliation. The raw error stays in the log.
            logger.exception("DDL dispatch for %s raised; reconciling from the live schema", deployment_id)
            apply_error = "ddl_dispatch_failed"

        # A session that was discarded (a rollback failed, so unknown writes may be pending on it) never reconciles
        # or finalizes: finalization would commit them. The PREPARED row stays as the hold; the target is blocked.
        if getattr(db, "session_unusable", False):
            return {
                "deployment_id": deployment_id,
                "status": "RECOVERY_REQUIRED",
                "stage": "APPLY",
                "reason_code": "session_discarded",
                "reason": "The database session was discarded before finalization; the deployment is held for recovery.",
            }

        # Stage 5: Reconcile Exhaustive Snapshot (§9 — Non-Destructive by Default)
        after = db.take_snapshot(doctype, fieldname, expected_deployment_id=deployment_id)
        outcome = reconcile_exhaustive_snapshot(
            deployment_id=deployment_id,
            doctype=doctype,
            fieldname=fieldname,
            before=before,
            after=after,
            apply_error=apply_error,
        )

        if outcome["status"] == "APPLIED":
            db.clear_doctype_cache(doctype)

        # Stage 6: Finalize State & Audit Event (§8)
        try:
            db.persist_final_outcome_and_audit(
                deployment_id,
                {"payload_hash": payload_hash, "outcome": outcome},
            )
        except Exception:
            # If finalization fails after DDL, preserve RECOVERY_REQUIRED on audit journal and return it
            logger.exception("finalization of %s failed after the DDL ran", deployment_id)
            if hasattr(db, "mark_recovery_required") and callable(getattr(db, "mark_recovery_required", None)):
                try:
                    db.mark_recovery_required(deployment_id, "finalization_failed")
                except Exception:
                    logger.exception("could not mark %s recovery-required", deployment_id)
            outcome = {
                **outcome,
                "status": "RECOVERY_REQUIRED",
                "finalization_error": "finalization_failed",
            }

        return outcome
    finally:
        unusable = False
        restore = getattr(db, "restore_lock_wait_timeout", None)
        if callable(restore):
            # The caller's session gets its own lock_wait_timeout back on every exit path (a restore that does
            # not verify discards the session).
            try:
                unusable = restore() is False or unusable
            except Exception:
                logger.exception("could not restore the session lock_wait_timeout")
                unusable = True
        for key in reversed(held):
            unusable = not _release_checked(db, key) or unusable
        if unusable:
            # A lock that may still be held keeps blocking others for as long as this connection lives: the
            # session is declared unusable and discarded, which frees every lock it owns.
            _discard_session(db)


def _replay_or_conflict(existing: Dict[str, Any], payload_hash: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
    """The stored outcome for a matching earlier request, an idempotency conflict for another payload, or
    ``None`` when the stored record is not the expected shape (the caller blocks)."""
    if not isinstance(existing, dict) or not isinstance(existing.get("outcome"), dict):
        return None
    if existing.get("payload_hash") != payload_hash:
        raise IdempotencyConflictError(
            f"IDEMPOTENCY_CONFLICT: Key '{idempotency_key}' was already used with a different payload."
        )
    return existing["outcome"]


def _approved_plan_problem(plan: DDLPlanInspection, doctype: str, fieldname: str) -> Optional[str]:
    """Why a caller-supplied plan is not acceptable, or ``None``. It goes through the gate a computed plan goes
    through (``validate_ddl_plan``: exactly one additive ADD COLUMN statement), and must also name this table and
    this field, so an empty, extra, foreign or non-additive plan never reaches an intent or a dispatch."""
    if not isinstance(plan, DDLPlanInspection) or not plan.inspectable or not plan.is_approved_additive_only:
        return "the supplied plan is not an inspectable, approved additive plan"
    statements = list(plan.statements or [])
    valid, why = validate_ddl_plan(statements)
    if not valid:
        return f"the supplied plan does not pass the DDL plan gate: {why}"
    match = APPROVED_DDL_REGEX.fullmatch(statements[0])
    if match is None or match["table"] != f"`tab{doctype}`" or match["name"] != fieldname:
        return "the supplied plan does not add this field to this table"
    return None


def _blocked_by_lookup_failure(deployment_id: str, lookup: str, exc: Exception) -> Dict[str, Any]:
    """A durable lookup that errors blocks the deployment; the error is never read as 'nothing found'.
    The exception is logged, never returned."""
    logger.error("durable %s lookup failed for %s: %s", lookup, deployment_id, type(exc).__name__, exc_info=exc)
    return {
        "deployment_id": deployment_id,
        "status": "REJECTED",
        "stage": "INSPECT",
        "reason_code": "engine_unavailable",
        "reason": f"Fail-closed: the durable {lookup} lookup failed ({type(exc).__name__}); deployment blocked.",
    }


def reconcile_exhaustive_snapshot(
    deployment_id: str,
    doctype: str,
    fieldname: str,
    before: ExhaustiveSnapshot,
    after: ExhaustiveSnapshot,
    apply_error: Optional[str],
) -> Dict[str, Any]:
    """
    Implements the exact 6-row Non-Destructive Reconciliation Table from ADR-001 Rev 2.3 (§9).
    Phase 1 NEVER auto-deletes orphaned Custom Field metadata or drops physical columns.
    """
    # Row 1: Absent | Absent | Baseline unchanged, no partial side effects -> FAILED_CLEAN
    if not after.has_meta and not after.has_col:
        if after.unapproved_side_effects or not after.indexes_unchanged:
            return {
                "deployment_id": deployment_id,
                "status": "RECOVERY_REQUIRED",
                "disposition": "UNAPPROVED_SIDE_EFFECT_WITHOUT_FIELD",
                "error": apply_error,
            }
        return {
            "deployment_id": deployment_id,
            "status": "FAILED_CLEAN",
            "disposition": "ABSENT_ABSENT_BASELINE_VERIFIED",
            "error": apply_error,
        }

    # Row 4: Present | Absent | Orphan metadata -> RECOVERY_REQUIRED by default (No auto-delete in Phase 1)
    if after.has_meta and not after.has_col:
        return {
            "deployment_id": deployment_id,
            "status": "RECOVERY_REQUIRED",
            "disposition": "ORPHAN_METADATA_NON_DESTRUCTIVE_HOLD",
            "error": apply_error,
        }

    # Row 5: Absent | Present | Orphan physical column -> RECOVERY_REQUIRED
    if not after.has_meta and after.has_col:
        return {
            "deployment_id": deployment_id,
            "status": "RECOVERY_REQUIRED",
            "disposition": "ORPHAN_PHYSICAL_COLUMN",
            "error": apply_error,
        }

    # Both Present | Present (Rows 2, 3, 6):
    # Row 3: Definition mismatch or unexpected side effect / index modification -> RECOVERY_REQUIRED
    if not after.definition_matches or not after.indexes_unchanged or after.unapproved_side_effects:
        return {
            "deployment_id": deployment_id,
            "status": "RECOVERY_REQUIRED",
            "disposition": "DEFINITION_MISMATCH_OR_UNAPPROVED_SIDE_EFFECT",
            "error": apply_error,
        }

    # Row 6: Definition matches, but provenance or concurrent external revision is uncertain -> RECOVERY_REQUIRED
    if not after.provenance_matches:
        return {
            "deployment_id": deployment_id,
            "status": "RECOVERY_REQUIRED",
            "disposition": "UNCERTAIN_PROVENANCE_OR_CONCURRENT_REVISION",
            "error": apply_error,
        }

    # Row 2: Present | Present | Expected definition, indexes, and provenance; no unapproved effects -> APPLIED
    return {
        "deployment_id": deployment_id,
        "status": "APPLIED",
        "disposition": "VERIFIED_CONSISTENT",
        "doctype": doctype,
        "fieldname": fieldname,
        "post_apply_warning": apply_error,
    }
