"""Keyed, idempotent, role-guarded writes for the twelve in-scope doctypes (ERP-010).

One `HrmsService` is bound to one tenant, one company and one caller. Nothing is cached as
trusted: every operation, and every write inside it, re-reads the live caller, session and store
tenant and company permission, and refuses if any differs from the binding (the service is never
silently reused for another caller or site). Every operation:
1. refuses a doctype outside the allow-list (`scope.py`),
2. validates values exactly (`validation.py`),
3. checks the caller's backend roles, then the engine's own permission and permission levels,
4. takes the store's lock for that business key, finds the record by its stable key inside that
   tenant and company, and only then inserts, updates changed fields, or does nothing. Re-applying
   a configuration therefore never creates a duplicate, even when two callers apply at once
   (ADR-0028: a run cut short is recovered by running it again).

It never calculates pay, tax, leave balances or end-of-service amounts (ADR-0031).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterator, Mapping, Sequence, TypeVar

from .access import DuplicateKeyError, Session, Store
from .errors import HrmsError
from .scope import assert_allowed_doctype
from .specs import (
    APPLY_ORDER, HR_ADMIN_ROLES, HR_SETUP_ROLES, LEAVE_DECISION_ROLES, SPECS, DocSpec, Rule,
)
from .validation import canonical_decimal, normalise_record

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
            return canonical_decimal(Decimal(str(value)))
        if rule.kind == "date":
            return str(value)[:10]
        if rule.kind == "bool":
            return bool(value)
    except (InvalidOperation, ValueError):
        return _UNEQUAL
    return value


def _identity(value: Any) -> str | None:
    """A sign-in identity in comparable form, or None when missing, empty or not a string."""
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().casefold()


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
        self._session, self._store = session, store
        self.tenant, self.company = tenant, company
        self.user = self._context(None)

    # -- guards ---------------------------------------------------------------------------
    def _context(self, bound_user: str | None) -> str:
        """Re-read the live caller, tenants and company permission; refuse any drift.

        Called at construction (to bind) and again before every operation and every write."""
        user = _guard(lambda: self._session.user)
        if not isinstance(user, str) or not user.strip() or user.casefold() == "guest":
            raise HrmsError("session_invalid")
        if bound_user is not None and user != bound_user:
            raise HrmsError("session_invalid")  # a different caller than the one this service was made for
        if _guard(lambda: self._session.tenant) != self.tenant or _guard(lambda: self._store.tenant) != self.tenant:
            raise HrmsError("tenant_mismatch")
        if not _guard(self._session.company_permitted, self.company):
            raise HrmsError("company_not_permitted")
        return user

    def _live_user(self) -> str:
        return self._context(self.user)

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
        """Find the record by its key with a current read; only called while the key lock is held."""
        filters = self._key(spec, values)
        if spec.company_scoped:
            filters["company"] = self.company
        rows = _guard(self._store.find_current, spec.doctype, filters)
        if len(rows) > 1:
            raise HrmsError("ambiguous_key", doctype=spec.doctype)
        return rows[0] if rows else None

    @contextlib.contextmanager
    def _locked(self, spec: DocSpec, values: Mapping[str, Any]) -> Iterator[None]:
        """Hold the store's lock for (tenant, company, doctype, canonical key) around lookup + write."""
        scope = (self.company if spec.company_scoped else "", *(str(v) for v in self._key(spec, values).values()))
        try:
            with contextlib.ExitStack() as stack:
                stack.enter_context(self._store.key_lock(spec.doctype, scope))
                yield
        except HrmsError:
            raise
        except Exception:
            raise HrmsError("operation_failed") from None

    def _insert(self, doctype: str, row: Mapping[str, Any]) -> dict[str, Any]:
        try:
            return self._store.insert(doctype, row)
        except (HrmsError, DuplicateKeyError):
            raise
        except Exception:
            raise HrmsError("operation_failed") from None

    def _leave_applicant_principal(self, applicant: Mapping[str, Any] | None, values: Mapping[str, Any]) -> str:
        """Check filing permissions and resolve the principal from the verified employee link."""
        self._require_native("Leave Application", "create", list(values))
        principal = (applicant or {}).get("user_id")
        if _identity(principal) is None:
            raise HrmsError("applicant_identity_unresolved", doctype="Leave Application")
        return principal.strip()

    # -- upsert ---------------------------------------------------------------------------
    def upsert(self, doctype: str, payload: Mapping[str, Any]) -> ApplyResult:
        self._live_user()
        spec = SPECS[assert_allowed_doctype(doctype)]
        values = normalise_record(spec, payload, self.company)
        roles = self._require_roles(spec.write_roles, doctype)
        return self._write(spec, values, roles)

    def apply_configuration(self, records: Sequence[Mapping[str, Any]]) -> list[ApplyResult]:
        """Apply many records. Everything is validated and role-checked before the first write;
        records then apply referenced-first. Safe to run again after any interruption."""
        self._live_user()
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
        # Roles are re-read for each record: a role withdrawn mid-run stops the rest of the run.
        return [self._write(spec, values, self._require_roles(spec.write_roles, spec.doctype)) for spec, values, _ in planned]

    def _write(self, spec: DocSpec, values: dict[str, Any], roles: frozenset[str]) -> ApplyResult:
        doctype = spec.doctype
        user = self._live_user()
        applicant: dict[str, Any] | None = None
        if spec.employee_field:
            applicant = self._employee(values[spec.employee_field])
        if doctype == "Leave Application" and not roles & HR_SETUP_ROLES:
            # A caller with only the self-service role may file for their own employee record.
            owner = _identity((applicant or {}).get("user_id"))
            if owner is None or owner != user.strip().casefold():
                raise HrmsError("role_not_permitted", doctype=doctype)
        key = self._key(spec, values)
        with self._locked(spec, values):
            user = self._live_user()  # again, now that the lock is held: nothing may have drifted
            for attempt in (0, 1):
                existing = self._lookup(spec, values)
                if existing is None:
                    row = dict(values)
                    if doctype == "Employee":
                        self._check_identity_binding(user, None, values)
                    if doctype == "Leave Application":
                        principal = self._leave_applicant_principal(applicant, values)
                        row["status"] = "Open"
                    else:
                        self._require_native(doctype, "create", list(values))
                    try:
                        created = self._insert(doctype, row)
                    except DuplicateKeyError:
                        if attempt == 0:
                            continue  # another writer won the race: take the update path instead
                        raise HrmsError("ambiguous_key", doctype=doctype) from None
                    if doctype == "Leave Application":
                        # Recorded once, in the protected store, never through the document payload.
                        _guard(self._store.record_applicant_identity, doctype, created["name"], principal)
                    return ApplyResult(doctype, key, created["name"], "created", tuple(values))
                return self._update_existing(spec, values, existing, key, user, applicant)
        raise HrmsError("operation_failed")  # pragma: no cover - the loop always returns or raises

    def _update_existing(
        self, spec: DocSpec, values: dict[str, Any], existing: dict[str, Any], key: dict[str, Any], user: str,
        applicant: Mapping[str, Any] | None,
    ) -> ApplyResult:
        doctype = spec.doctype
        if doctype == "Leave Application" and existing.get("status") != "Open":
            raise HrmsError("leave_application_not_open", doctype=doctype)
        changed = tuple(f for f, v in values.items() if not _same(spec, f, existing.get(f), v))
        if doctype == "Employee":
            self._check_identity_binding(user, existing, {f: values[f] for f in changed})
        if changed:
            self._require_native(doctype, "write", changed)
        if doctype == "Leave Application":
            filed = _guard(self._store.get_applicant_identity, doctype, existing["name"])
            if filed in (None, ""):
                # An earlier insert may have succeeded before the protected write failed.
                principal = self._leave_applicant_principal(applicant, values)
                _guard(self._store.record_applicant_identity, doctype, existing["name"], principal)
        if not changed:
            return ApplyResult(doctype, key, existing["name"], "unchanged")
        _guard(self._store.update, doctype, existing["name"], {f: values[f] for f in changed})
        return ApplyResult(doctype, key, existing["name"], "updated", changed)

    @staticmethod
    def _check_identity_binding(user: str, existing: dict[str, Any] | None, changes: Mapping[str, Any]) -> None:
        """Linking an employee to a sign-in account decides who may act as that employee, so it is a
        permission-sensitive change: an existing link is never changed here, and a caller never links
        their own account (an applicant could otherwise rebind or claim identities to defeat the
        separation of duties in `decide_leave_application`)."""
        if "user_id" not in changes:
            return
        if existing is not None and existing.get("user_id") not in (None, ""):
            raise HrmsError("identity_binding_protected", doctype="Employee")
        if _identity(changes["user_id"]) == user.strip().casefold():
            raise HrmsError("identity_binding_protected", doctype="Employee")

    # -- leave decision -------------------------------------------------------------------
    def decide_leave_application(self, key: Mapping[str, Any], decision: str) -> ApplyResult:
        """Approve or reject an open leave application. The approver is the authenticated caller;
        nobody can approve or reject their own application, whatever roles they hold."""
        doctype = "Leave Application"
        self._live_user()
        if decision not in ("approve", "reject"):
            raise HrmsError("decision_invalid")
        roles = self._require_roles(LEAVE_DECISION_ROLES, doctype)
        spec = SPECS[doctype]
        values = normalise_record(spec, key, self.company)
        if set(values) != set(spec.key_fields) | {"company"}:
            raise HrmsError("payload_invalid", doctype=doctype)
        with self._locked(spec, values):
            user = self._live_user()
            roles = self._require_roles(LEAVE_DECISION_ROLES, doctype)
            self._require_native(doctype, "write", ["status"])
            application = self._lookup(spec, values)
            if application is None:
                raise HrmsError("record_not_found", doctype=doctype)
            applicant = self._employee(application.get("employee"))
            filed = _guard(self._store.get_applicant_identity, doctype, application["name"])
            self._require_separate_applicant(user, filed, applicant)
            if not roles & HR_ADMIN_ROLES:
                # A Leave Approver who is not an administrator must be the named approver.
                designated = _identity(application.get("leave_approver"))
                if designated is None or designated != user.strip().casefold():
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

    @staticmethod
    def _require_separate_applicant(user: str, filed_principal: Any, applicant: Mapping[str, Any]) -> None:
        """The caller must not be the applicant, and the applicant's identity must be resolved.

        Two identities are compared: the principal captured when the application was filed, and the
        employee record's current link. The caller may match neither. Both must be present, non-empty
        text and still agree; anything else (missing, changed, wrong type) fails closed."""
        filed = _identity(filed_principal)
        current = _identity(applicant.get("user_id"))
        me = user.strip().casefold()
        if me in (filed, current):
            raise HrmsError("self_approval_forbidden", doctype="Leave Application")
        if filed is None or current is None or filed != current:
            raise HrmsError("applicant_identity_unresolved", doctype="Leave Application")
