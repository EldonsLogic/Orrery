"""Validate -> preview -> authenticated confirmed transactional apply."""
from __future__ import annotations

import copy
import hmac
import re

from .backend import ImportBackend
from .errors import ImportFailure
from .validation import MASTER_FIELDS, business_key, canonical, prepare


class OpeningImporter:
    """Server-owned orchestrator. Request data cannot select roles or a backend."""

    def __init__(self, backend: ImportBackend, *, max_rows: int = 10_000):
        if type(max_rows) is not int or not 1 <= max_rows <= 10_000:
            raise ValueError("max_rows must be between 1 and 10000")
        self.backend, self.max_rows = backend, max_rows

    def validate(self, source: dict) -> dict:
        """Return deterministic safe errors/counts/totals without writing data."""
        return self.preview(source)

    def preview(self, source: dict) -> dict:
        """Bind context, rows, report and rounding precision to a SHA-256 plan."""
        try:
            _, result = prepare(source, self.max_rows)
            return result
        except ImportFailure as exc:
            return {"ok": False, "errors": [exc.to_dict()]}
        except (TypeError, ValueError, KeyError, ArithmeticError, RecursionError):
            return {"ok": False, "errors": [ImportFailure("IMP-SCHEMA").to_dict()]}

    def apply(self, source: dict, *, confirmed_by: str | None = None, plan_hash: str | None = None) -> dict:
        """Require an authorised human and matching hash, then atomically write.

        Recompute rather than trusting a mutable preview object. Batch journal
        and records share the backend transaction, including the unique batch
        claim. An existing different hash is a conflict even across companies.
        """
        try:
            plan, preview = prepare(source, self.max_rows)
            plan = copy.deepcopy(plan)
        except ImportFailure:
            raise
        except (TypeError, ValueError, KeyError, ArithmeticError, RecursionError):
            raise ImportFailure("IMP-SCHEMA") from None
        try:
            identity = self.backend.identity()
            if (not isinstance(identity, dict) or identity.get("human") is not True
                    or not isinstance(identity.get("user_id"), str) or not identity["user_id"]
                    or identity.get("tenant_id") != plan["tenant_id"]
                    or not isinstance(identity.get("companies"), (list, tuple, set, frozenset))
                    or plan["company"] not in identity["companies"]
                    or not isinstance(identity.get("roles"), (list, tuple, set, frozenset))
                    or not {"Accounts Manager", "System Manager"}.intersection(identity["roles"])):
                raise ImportFailure("IMP-AUTH")
        except Exception:
            raise ImportFailure("IMP-AUTH") from None
        if (confirmed_by != identity["user_id"] or not isinstance(plan_hash, str)
                or not re.fullmatch(r"[0-9a-f]{64}", plan_hash) or not hmac.compare_digest(plan_hash, preview["plan_hash"])):
            raise ImportFailure("IMP-CONFIRM")
        tenant, batch_id = plan["tenant_id"], plan["batch_id"]
        try:
            with self.backend.transaction():
                previous = self.backend.journal(tenant, batch_id)
                if previous:
                    if previous["plan_hash"] != plan_hash or previous["company"] != plan["company"]:
                        raise ImportFailure("IMP-CONFLICT")
                    if previous["status"] != "applied":
                        raise ImportFailure("IMP-RECOVERY")
                    return {"status": "already_applied", "plan_hash": plan_hash}
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
            try:
                self.backend.record_failure(tenant, batch_id, plan_hash, code)
            except Exception:
                raise ImportFailure("IMP-RECOVERY") from None
            raise ImportFailure(code) from None
