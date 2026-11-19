"""Keyed, idempotent, role-guarded writes for the twelve in-scope doctypes (ERP-010).

One `HrmsService` is bound to one tenant and one company for its whole life. Every operation:
1. refuses a doctype outside the allow-list (`scope.py`),
2. validates values exactly (`validation.py`),
3. checks the caller's backend roles, then the engine's own permission and permission levels,
4. finds the record by its stable business key inside that tenant and company, and only then
   inserts, updates changed fields, or does nothing. Re-applying a configuration therefore never
   creates a duplicate (ADR-0028: a run cut short is recovered by running it again).

It never calculates pay, tax, leave balances or end-of-service amounts (ADR-0031).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Sequence, TypeVar

from .access import Session, Store
from .errors import HrmsError
from .scope import assert_allowed_doctype
from .specs import (
    APPLY_ORDER, HR_ADMIN_ROLES, HR_SETUP_ROLES, LEAVE_DECISION_ROLES, SPECS, DocSpec, Rule,
)
from .validation import normalise_record

T = TypeVar("T")
_UNEQUAL = object()


@dataclass(frozen=True)
class ApplyResult:
    doctype: str
    key: Mapping[str, Any]
    name: str
    action: str  # created, updated, unchanged, approved, rejected
    changed: tuple[str, ...] = ()


def _guard(call: Callable[..., T], *args: Any) -> T:
    """Run a session or store call; any failure is a refusal, never a silent pass."""
    try:
        return call(*args)
    except HrmsError:
        raise
    except Exception:
        raise HrmsError("operation_failed") from None


def _canon(rule: Rule, value: Any) -> Any:
    """Canonical form of a stored value, so the engine's own typing (floats, dates) compares equal."""
    if value is None:
        return _UNEQUAL
    try:
        if rule.kind == "decimal":
            return format(Decimal(str(value)).normalize(), "f")
        if rule.kind == "date":
            return str(value)[:10]
        if rule.kind == "bool":
            return bool(value)
    except (InvalidOperation, ValueError):
        return _UNEQUAL
    return value


def _same(spec: DocSpec, name: str, stored: Any, wanted: Any) -> bool:
    if name in spec.children:
        child = spec.children[name]
        rows = stored if isinstance(stored, (list, tuple)) else []
        have = [{f: _canon(child.fields[f], r.get(f)) for f in child.fields if f in w} for r, w in zip(rows, wanted)]
        return len(rows) == len(wanted) and have == list(wanted)
    return _canon(spec.fields[name], stored) == wanted


class HrmsService:
    def __init__(self, session: Session, store: Store, *, tenant: str, company: str) -> None:
        if not isinstance(tenant, str) or not tenant.strip():
            raise HrmsError("tenant_mismatch")
        if not isinstance(company, str) or not company.strip():
            raise HrmsError("company_missing")
        user = _guard(lambda: session.user)
        if not isinstance(user, str) or not user.strip() or user.casefold() == "guest":
            raise HrmsError("session_invalid")
        if _guard(lambda: session.tenant) != tenant or _guard(lambda: store.tenant) != tenant:
            raise HrmsError("tenant_mismatch")
        if not _guard(session.company_permitted, company):
            raise HrmsError("company_not_permitted")
        self._session, self._store = session, store
        self.tenant, self.company, self.user = tenant, company, user

    # -- guards ---------------------------------------------------------------------------
    def _roles(self) -> frozenset[str]:
        return frozenset(_guard(self._session.roles))

    def _require_roles(self, allowed: frozenset[str], doctype: str) -> frozenset[str]:
        roles = self._roles()
        if not roles & allowed:
            raise HrmsError("role_not_permitted", doctype=doctype)
        return roles

    def _require_native(self, doctype: str, ptype: str, fields: Sequence[str]) -> None:
        if not _guard(self._session.has_permission, doctype, ptype):
            raise HrmsError("permission_denied", doctype=doctype)
        if _guard(self._session.denied_fields, doctype, list(fields)):
            raise HrmsError("field_permission_denied", doctype=doctype)

    def _find_one(self, doctype: str, filters: Mapping[str, Any]) -> dict[str, Any] | None:
        rows = _guard(self._store.find, doctype, dict(filters))
        if len(rows) > 1:
            raise HrmsError("ambiguous_key", doctype=doctype)
        return rows[0] if rows else None

    def _employee(self, name: str) -> dict[str, Any]:
        row = self._find_one("Employee", {"name": name, "company": self.company})
        if row is None:
            raise HrmsError("employee_not_found", field="employee", doctype="Employee")
        return row

    @staticmethod
    def _key(spec: DocSpec, values: Mapping[str, Any]) -> dict[str, Any]:
        return {k: values[k] for k in spec.key_fields}

    def _lookup(self, spec: DocSpec, values: Mapping[str, Any]) -> dict[str, Any] | None:
        filters = self._key(spec, values)
        if spec.company_scoped:
            filters["company"] = self.company
        return self._find_one(spec.doctype, filters)

    # -- upsert ---------------------------------------------------------------------------
    def upsert(self, doctype: str, payload: Mapping[str, Any]) -> ApplyResult:
        spec = SPECS[assert_allowed_doctype(doctype)]
        values = normalise_record(spec, payload, self.company)
        roles = self._require_roles(spec.write_roles, doctype)
        return self._write(spec, values, roles)

    def apply_configuration(self, records: Sequence[Mapping[str, Any]]) -> list[ApplyResult]:
        """Apply many records. Everything is validated and role-checked before the first write;
        records then apply referenced-first. Safe to run again after any interruption."""
        if not isinstance(records, (list, tuple)):
            raise HrmsError("payload_invalid")
        planned: list[tuple[DocSpec, dict[str, Any], frozenset[str]]] = []
        seen: set[tuple[str, tuple[Any, ...]]] = set()
        for record in records:
            if not isinstance(record, Mapping) or set(record) != {"doctype", "values"}:
                raise HrmsError("payload_invalid")
            spec = SPECS[assert_allowed_doctype(record["doctype"])]
            values = normalise_record(spec, record["values"], self.company)
            roles = self._require_roles(spec.write_roles, spec.doctype)
            marker = (spec.doctype, tuple(self._key(spec, values).values()))
            if marker in seen:
                raise HrmsError("duplicate_row", doctype=spec.doctype)
            seen.add(marker)
            planned.append((spec, values, roles))
        planned.sort(key=lambda item: APPLY_ORDER.index(item[0].doctype))
        return [self._write(spec, values, roles) for spec, values, roles in planned]

    def _write(self, spec: DocSpec, values: dict[str, Any], roles: frozenset[str]) -> ApplyResult:
        doctype = spec.doctype
        applicant: dict[str, Any] | None = None
        if spec.employee_field:
            applicant = self._employee(values[spec.employee_field])
        if doctype == "Leave Application" and not roles & HR_SETUP_ROLES:
            # A caller with only the self-service role may file for their own employee record.
            owner = (applicant or {}).get("user_id")
            if not isinstance(owner, str) or owner.casefold() != self.user.casefold():
                raise HrmsError("role_not_permitted", doctype=doctype)
        key = self._key(spec, values)
        existing = self._lookup(spec, values)
        if existing is None:
            self._require_native(doctype, "create", list(values))
            row = dict(values)
            if doctype == "Leave Application":
                row["status"] = "Open"
            created = _guard(self._store.insert, doctype, row)
            return ApplyResult(doctype, key, created["name"], "created", tuple(values))
        if doctype == "Leave Application" and existing.get("status") != "Open":
            raise HrmsError("leave_application_not_open", doctype=doctype)
        changed = tuple(f for f, v in values.items() if not _same(spec, f, existing.get(f), v))
        if not changed:
            return ApplyResult(doctype, key, existing["name"], "unchanged")
        self._require_native(doctype, "write", changed)
        _guard(self._store.update, doctype, existing["name"], {f: values[f] for f in changed})
        return ApplyResult(doctype, key, existing["name"], "updated", changed)

    # -- leave decision -------------------------------------------------------------------
    def decide_leave_application(self, key: Mapping[str, Any], decision: str) -> ApplyResult:
        """Approve or reject an open leave application. The approver is the authenticated caller;
        nobody can approve or reject their own application, whatever roles they hold."""
        doctype = "Leave Application"
        if decision not in ("approve", "reject"):
            raise HrmsError("decision_invalid")
        roles = self._require_roles(LEAVE_DECISION_ROLES, doctype)
        spec = SPECS[doctype]
        values = normalise_record(spec, key, self.company)
        if set(values) != set(spec.key_fields) | {"company"}:
            raise HrmsError("payload_invalid", doctype=doctype)
        self._require_native(doctype, "write", ["status"])
        application = self._lookup(spec, values)
        if application is None:
            raise HrmsError("record_not_found", doctype=doctype)
        applicant = self._employee(application.get("employee"))
        applicant_user = applicant.get("user_id")
        if isinstance(applicant_user, str) and applicant_user.casefold() == self.user.casefold():
            raise HrmsError("self_approval_forbidden", doctype=doctype)
        designated = application.get("leave_approver")
        if designated and not roles & HR_ADMIN_ROLES and str(designated).casefold() != self.user.casefold():
            raise HrmsError("not_designated_approver", doctype=doctype)
        target = "Approved" if decision == "approve" else "Rejected"
        status = application.get("status")
        if status == target:
            return ApplyResult(doctype, self._key(spec, values), application["name"], "unchanged")
        if status in ("Approved", "Rejected"):
            raise HrmsError("leave_application_already_decided", doctype=doctype)
        if status != "Open":
            raise HrmsError("leave_application_not_open", doctype=doctype)
        _guard(self._store.update, doctype, application["name"], {"status": target})
        return ApplyResult(
            doctype, self._key(spec, values), application["name"], target.lower(), ("status",)
        )
