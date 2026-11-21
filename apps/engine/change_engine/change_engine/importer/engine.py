"""Validate -> preview -> authenticated confirmed transactional apply."""
from __future__ import annotations

import copy
import hmac
import re

from .backend import ImportBackend
from .errors import ImportFailure
from .validation import MASTER_FIELDS, OPENING_FIELDS, business_key, canonical, prepare


class OpeningImporter:
    """Server-owned orchestrator. Request data cannot select roles or a backend."""

    def __init__(self, backend: ImportBackend, *, max_rows: int = 10_000):
        if type(max_rows) is not int or not 1 <= max_rows <= 10_000:
            raise ValueError("max_rows must be between 1 and 10000")
        self.backend, self.max_rows = backend, max_rows

    def _authorize(self, source):
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
                    or "opening_import" not in identity["capabilities"]):
                raise ImportFailure("IMP-AUTH")
            return identity
        except Exception:
            raise ImportFailure("IMP-AUTH") from None

    def _prepare(self, source):
        """Build one plan using company-scoped master reads; fail closed on errors."""
        try:
            plan, result = prepare(source, self.max_rows, lambda entity, key: self.backend.master(
                source["tenant_id"], source["company"], entity, key))
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
            return {"ok": False, "errors": [exc.to_dict()], "errors_truncated": True}

    def apply(self, source: dict, *, confirmed_by: str | None = None, plan_hash: str | None = None) -> dict:
        """Confirm and atomically apply an exact plan, including prior master state.

        Recompute while holding the transaction so master snapshots/reference types
        cannot change between confirmation and writing. A committed identical batch
        retry returns its original result even if those masters changed afterwards.
        """
        identity = self._authorize(source)
        # Detach caller-owned data before entering the transactional boundary.
        initial, _ = self._prepare(source)
        source = copy.deepcopy(source)
        identity = self._authorize(source)
        tenant, batch_id = source["tenant_id"], source["batch_id"]
        if (confirmed_by != identity["user_id"] or not isinstance(plan_hash, str)
                or not re.fullmatch(r"[0-9a-f]{64}", plan_hash)):
            raise ImportFailure("IMP-CONFIRM")
        try:
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
                # Master records exist before any opening detail links to them.
                order = ("Account", "Customer", "Supplier", "Item", "Warehouse", "TrialBalance", "AR", "AP", "Stock")
                for entity in order:
                    for index, row in enumerate(plan["datasets"].get(entity, [])):
                        key = business_key(entity, row) if entity in MASTER_FIELDS else canonical([batch_id, index])
                        self.backend.write(tenant, plan["company"], entity, key, row)
                self.backend.commit_batch(plan, plan_hash, identity["user_id"])
            return {"status": "applied", "plan_hash": plan_hash}
        except Exception as exc:
            code = exc.code if isinstance(exc, ImportFailure) else "IMP-WRITE"
            if code not in {"IMP-CONFIRM", "IMP-REFERENCE", "IMP-SCHEMA", "IMP-REPORT"}:
                try:
                    self.backend.record_failure(tenant, batch_id, plan_hash, code, user_id=identity["user_id"])
                except Exception:
                    raise ImportFailure("IMP-RECOVERY") from None
            raise ImportFailure(code) from None
