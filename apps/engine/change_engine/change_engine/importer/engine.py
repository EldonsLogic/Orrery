"""Validate -> preview -> authenticated confirmed transactional apply."""
from __future__ import annotations

import copy
import hmac
import re

from .backend import ImportBackend
from .errors import ImportFailure
from .validation import MASTER_FIELDS, OPENING_FIELDS, business_key, canonical, prepare, text


class OpeningImporter:
    """Server-owned orchestrator. Request data cannot select roles or a backend."""

    def __init__(self, backend: ImportBackend, *, max_rows: int = 10_000):
        if type(max_rows) is not int or not 1 <= max_rows <= 10_000:
            raise ValueError("max_rows must be between 1 and 10000")
        self.backend, self.max_rows = backend, max_rows

    def _authorize(self, source, *, required_capability: str = "opening_import"):
        """Authenticate all stages before traversing untrusted datasets or reports."""
        try:
            identity = self.backend.identity()
            if (not isinstance(source, dict) or not isinstance(identity, dict) or identity.get("human") is not True
                    or not isinstance(identity.get("user_id"), str) or not identity["user_id"]
                    or not isinstance(source.get("tenant_id"), str) or not isinstance(source.get("company"), str)
                    or identity.get("tenant_id") != source["tenant_id"]
                    or not isinstance(identity.get("companies"), (list, tuple, set, frozenset))
                    or source["company"] not in identity["companies"]
                    or not isinstance(identity.get("capabilities"), (list, tuple, set, frozenset))
                    or "opening_import" not in identity["capabilities"]
                    or required_capability not in identity["capabilities"]):
                raise ImportFailure("IMP-AUTH")
            return identity
        except Exception:
            raise ImportFailure("IMP-AUTH") from None

    def _record_failure(self, tenant: str, batch_id: str, plan_hash: str | None, code: str, user_id: str) -> None:
        if code not in {"IMP-REFERENCE", "IMP-SCHEMA", "IMP-REPORT"}:
            recorded_hash = plan_hash if isinstance(plan_hash, str) and re.fullmatch(r"[0-9a-f]{64}", plan_hash) else ""
            try:
                self.backend.record_failure(tenant, batch_id, recorded_hash, code, user_id=user_id)
            except Exception:
                raise ImportFailure("IMP-RECOVERY") from None

    def _prepare(self, source, *, confirm_distinct=None, pending_plan_hash=None):
        """Build one plan using company-scoped master reads; fail closed on errors."""
        def _lookup_distinct(tenant_id, company, batch_id, digest, pending_hash):
            ids = self.backend.distinct_confirmations(tenant_id, company, batch_id, digest, pending_hash)
            if not ids:
                previous = self.backend.journal(tenant_id, batch_id)
                if (previous and previous["company"] == company
                        and previous.get("source_digest") == digest
                        and previous["status"] == "applied"
                        and previous.get("pending_plan_hash")):
                    ids = self.backend.distinct_confirmations(
                        tenant_id, company, batch_id, digest, previous["pending_plan_hash"])
            return ids

        try:
            plan, result = prepare(
                source, self.max_rows,
                lambda entity, key: self.backend.master(source["tenant_id"], source["company"], entity, key),
                lambda tenant_id, company: self.backend.company_currency(tenant_id, company),
                _lookup_distinct,
                confirm_distinct=confirm_distinct,
                pending_plan_hash=pending_plan_hash,
            )
            previous = self.backend.journal(plan["tenant_id"], plan["batch_id"])
            if (previous and previous["company"] == plan["company"]
                    and previous.get("source_digest") == plan["source_digest"]):
                result["plan_hash"] = previous["plan_hash"]
            return plan, result
        except ImportFailure:
            raise
        except (TypeError, ValueError, KeyError, ArithmeticError, RecursionError):
            raise ImportFailure("IMP-SCHEMA") from None
        except Exception:
            raise ImportFailure("IMP-WRITE") from None

    def validate(self, source: dict) -> dict:
        """Return deterministic safe errors/counts/totals without writing data."""
        return self.preview(source)

    def preview(self, source: dict) -> dict:
        """Bind rows, report, master snapshots and context to a SHA-256 plan."""
        try:
            self._authorize(source)
            _, result = self._prepare(source)
            return result
        except ImportFailure as exc:
            # Fail at the first error: the flag means further errors may be omitted.
            payload = {"ok": False, "errors": [exc.to_dict()], "errors_truncated": True}
            if exc.name_groups is not None:
                payload["name_groups"] = exc.name_groups
                payload["plan_hash"] = exc.plan_hash
            return payload

    def confirm(self, source: dict, *, confirmed_by: str | None = None,
                owner_confirmed_distinct: list[str] | tuple[str, ...] | None = None,
                plan_hash: str | None = None) -> dict:
        """Verify and server-record owner distinct confirmation for flagged name groups."""
        identity = self._authorize(source, required_capability="opening_import_confirm")
        tenant = identity["tenant_id"]
        try:
            batch_id = text(source.get("batch_id"))
        except ImportFailure:
            batch_id = ""
        try:
            if (confirmed_by != identity["user_id"]
                    or not isinstance(owner_confirmed_distinct, (list, tuple, set, frozenset))
                    or not all(isinstance(gid, str) for gid in owner_confirmed_distinct)
                    or not isinstance(plan_hash, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", plan_hash)):
                raise ImportFailure("IMP-CONFIRM")
            ids = list(owner_confirmed_distinct)
            if len(set(ids)) != len(ids):
                raise ImportFailure("IMP-CONFIRM")
            source = copy.deepcopy(source)
            identity = self._authorize(source, required_capability="opening_import_confirm")
            with self.backend.transaction():
                plan, result = self._prepare(source, confirm_distinct=ids, pending_plan_hash=plan_hash)
                self.backend.record_distinct_confirmation(
                    plan["tenant_id"], plan["company"], plan["batch_id"],
                    plan["source_digest"], plan["pending_plan_hash"],
                    result["owner_confirmed_distinct"], identity["user_id"],
                )
            return result
        except Exception as exc:
            code = exc.code if isinstance(exc, ImportFailure) else "IMP-WRITE"
            self._record_failure(tenant, batch_id, plan_hash, code, identity["user_id"])
            raise ImportFailure(code) from None

    def apply(self, source: dict, *, confirmed_by: str | None = None, plan_hash: str | None = None) -> dict:
        """Confirm and atomically apply an exact plan, including prior master state.

        Recompute while holding the transaction so master snapshots/reference types
        cannot change between confirmation and writing. A committed identical batch
        retry returns its original result even if those masters changed afterwards.
        """
        identity = self._authorize(source)
        # Detach caller-owned data before entering the transactional boundary.
        initial, _ = self._prepare(source)
        tenant, batch_id = initial["tenant_id"], initial["batch_id"]
        try:
            source = copy.deepcopy(source)
            identity = self._authorize(source)
            if (confirmed_by != identity["user_id"] or not isinstance(plan_hash, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", plan_hash)):
                raise ImportFailure("IMP-CONFIRM")
            with self.backend.transaction():
                previous = self.backend.journal(tenant, batch_id)
                if previous:
                    # Stored source hash separates an exact retry from altered input,
                    # while plan_hash remains bound to the original master snapshots.
                    if (previous["plan_hash"] != plan_hash or previous["company"] != source["company"]
                            or previous.get("source_digest") != initial["source_digest"]):
                        raise ImportFailure("IMP-CONFLICT")
                    if previous["status"] != "applied":
                        raise ImportFailure("IMP-RECOVERY")
                    return {"status": "already_applied", "plan_hash": plan_hash}
                plan, preview = self._prepare(source)
                if any(plan["datasets"].get(entity) for entity in OPENING_FIELDS):
                    self.backend.claim_opening(tenant, plan["company"], batch_id)
                if not hmac.compare_digest(plan_hash, preview["plan_hash"]):
                    raise ImportFailure("IMP-CONFIRM")
                master_rows = {(c["entity"], c["key"]): c["after"] for c in plan["master_changes"]}
                # Master records exist before any opening detail links to them.
                order = ("Account", "Customer", "Supplier", "Item", "Warehouse", "TrialBalance", "AR", "AP", "Stock")
                for entity in order:
                    for index, row in enumerate(plan["datasets"].get(entity, [])):
                        key = business_key(entity, row) if entity in MASTER_FIELDS else canonical([batch_id, index])
                        written = master_rows[(entity, key)] if entity in MASTER_FIELDS else row
                        self.backend.write(tenant, plan["company"], entity, key, written)
                self.backend.commit_batch(plan, plan_hash, identity["user_id"])
            return {"status": "applied", "plan_hash": plan_hash}
        except Exception as exc:
            code = exc.code if isinstance(exc, ImportFailure) else "IMP-WRITE"
            self._record_failure(tenant, batch_id, plan_hash, code, identity["user_id"])
            raise ImportFailure(code) from None
