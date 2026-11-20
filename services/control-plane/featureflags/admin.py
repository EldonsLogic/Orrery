"""Flag changes. Humans only: the caller must present verified staff-realm claims
for an active, MFA-satisfied staff member.

Restricted flags (agent authority, money, compliance) gate code paths that act on
money, tax, compliance or agent authority, so enabling one is a two-person change:
a proposer and a different approver, each holding the configured staff role and
each spending their own fresh MFA step-up (one step-up pays for one change). The
approval is bound to the exact change (flag, new value, scope, expiry), is single
use, and expires. The same two-person flow releases the platform-wide kill switch.
Switching OFF, engaging a kill and releasing a flag or tenant kill (step-up, one
person) need no second human. Every change is a sealed, append-only audit record.

Honest limit (Q-450, Q-431): claims carry no human-versus-agent flag. "Never an
agent" rests on (1) realm separation (an agent has no staff-realm session), (2) the
staff role, which is provisioned only to named humans, (3) a refusal of
agent-looking subject ids, and (4) two distinct people having to agree."""

import dataclasses
import re
import secrets
import unicodedata

from identity import IdentityError, Realm
from identity.service import STEP_UP_MAX_AGE
from identity.tokens import AccessClaims, check_live

from .errors import FlagError
from .model import MAX_BP, MAX_ENTRIES, Proposal, valid_id, valid_key

PROPOSAL_TTL = 900
_AGENT_ID = re.compile(r"(agent|svc|service|bot|system)[:_\-.]", re.I)
_BAD_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}


def _clean_reason(reason) -> str:
    if (not isinstance(reason, str) or not 3 <= len(reason) <= 200
            or any(unicodedata.category(c) in _BAD_CATEGORIES for c in reason)):
        raise FlagError("FLG-003")
    return reason


class FlagAdmin:
    def __init__(self, idn, registry, store, *, restricted_role=None, staff_roles=None):
        """`staff_roles.has_role(staff_id, role) -> bool` is a port to the staff
        role store. With no role name or no port configured, restricted changes
        are refused (default deny). One clock: the identity service's."""
        self.idn, self.registry, self.store = idn, registry, store
        self.restricted_role, self.staff_roles = restricted_role, staff_roles

    def _now(self) -> int:
        now = self.idn.now()
        if type(now) is not int or now <= 0:
            raise FlagError("FLG-030")
        return now

    # --- caller checks -------------------------------------------------
    def _staff(self, claims, action) -> AccessClaims:
        try:
            if not isinstance(claims, AccessClaims):
                raise FlagError("FLG-010")  # agents, services and raw ids are not claims
            check_live(claims, self._now())
            if (claims.realm is not Realm.STAFF or claims.tenant is not None
                    or not claims.mfa_satisfied or _AGENT_ID.match(str(claims.subject))):
                raise FlagError("FLG-010")
            staff = self.idn.repo.get_staff(claims.subject)
            if staff is None or not staff.active or staff.session_version != claims.session_version:
                raise FlagError("FLG-010")
            return claims
        except (IdentityError, FlagError) as e:
            code = e.code if isinstance(e, FlagError) else "FLG-010"
            self._deny(claims, action, code)
            raise FlagError("FLG-010" if code.startswith("IDN") else code) from None

    def _spend_step_up(self, claims, action) -> None:
        """Fresh MFA step-up, consumed: the same sign-in cannot pay for a second change."""
        try:
            try:
                self.idn.require_step_up(claims)
            except IdentityError:
                raise FlagError("FLG-011") from None
            if not self.store.consume_step_up(claims.subject, claims.auth_time, self._now(),
                                              STEP_UP_MAX_AGE):
                raise FlagError("FLG-011")
        except FlagError as e:
            self._deny(claims, action, e.code)
            raise

    def _require_role(self, claims, action) -> None:
        try:
            ok = (self.restricted_role is not None and self.staff_roles is not None
                  and self.staff_roles.has_role(claims.subject, self.restricted_role) is True)
        except Exception:
            ok = False
        if not ok:
            self._deny(claims, action, "FLG-013")
            raise FlagError("FLG-013")

    def _deny(self, claims, action, code):
        try:
            subject = getattr(claims, "subject", None)
            self.store.note_denial({"at": self._now(), "action": action, "code": code,
                                    "subject": subject if valid_id(subject) else None})
        except Exception:
            pass

    def _def(self, key):
        d = self.registry.get(key)
        if d is None:
            raise FlagError("FLG-002")
        return d

    # --- planning a change --------------------------------------------
    def _plan(self, kind, key, tenant_id, user_id, value):
        """(action, old, new, flag_state, kill, enabling) against current state; or
        None for a no-op. Pure: nothing is written."""
        if kind == "release_platform_kill":
            k = self.store.kill_state()
            if not k.platform:
                return None
            return ("kill.release.platform", True, False, None, dataclasses.replace(k, platform=False), True)
        s = self.store.get_flag(key)
        if kind == "global":
            if value is s.global_value:
                return None
            return ("set_global", s.global_value, value, dataclasses.replace(s, global_value=value),
                    None, value is True)
        if kind == "percent":
            if value == s.percent_bp:
                return None
            return ("set_percent", s.percent_bp, value, dataclasses.replace(s, percent_bp=value),
                    None, value > s.percent_bp)
        member = tenant_id if kind == "tenant" else (tenant_id, user_id)
        cur = s.tenants if kind == "tenant" else s.users
        if (member in cur) is value:
            return None
        new = frozenset(cur | {member} if value else cur - {member})
        if len(new) > MAX_ENTRIES:
            raise FlagError("FLG-003")
        field = "tenants" if kind == "tenant" else "users"
        return (f"set_{kind}", member in cur, value, dataclasses.replace(s, **{field: new}),
                None, value is True)

    def _validate(self, kind, key, tenant_id, user_id, value):
        if kind == "release_platform_kill":
            if key is not None or tenant_id is not None or user_id is not None or value is not True:
                raise FlagError("FLG-003")
            return None
        d = self._def(key)
        if kind == "global":
            ok = value is None or type(value) is bool
        elif kind == "percent":
            ok = type(value) is int and 0 <= value <= MAX_BP
        elif kind == "tenant":
            ok = type(value) is bool and valid_id(tenant_id)
        elif kind == "user":
            ok = type(value) is bool and valid_id(tenant_id) and valid_id(user_id)
        else:
            ok = False
        if not ok:
            raise FlagError("FLG-003")
        return d

    def _commit(self, version, plan, staff_id, reason, key, tenant, user, approved_by=None):
        action, old, new, flag_state, kill, _ = plan
        entry = dict(at=self._now(), staff_id=staff_id, approved_by=approved_by, action=action,
                     flag_key=key, tenant_id=tenant, user_id=user, old=old, new=new, reason=reason)
        return self.store.commit(version, flag_key=key, flag_state=flag_state, kill=kill, entry=entry)

    # --- direct changes (never needing a second person) ----------------
    def _direct(self, claims, kind, key, tenant_id, user_id, value, reason, action):
        d = self._validate(kind, key, tenant_id, user_id, value)
        staff = self._staff(claims, action)
        reason = _clean_reason(reason)
        version = self.store.version()
        plan = self._plan(kind, key, tenant_id, user_id, value)
        if plan is None:
            return None
        if plan[5] and d.restricted:
            self._deny(claims, action, "FLG-014")
            raise FlagError("FLG-014")  # enabling a restricted flag: propose and approve
        return self._commit(version, plan, staff.subject, reason, key, tenant_id, user_id)

    def set_global(self, claims, key, value, reason):
        """value True, False, or None to clear back to the definition default."""
        return self._direct(claims, "global", key, None, None, value, reason, "set_global")

    def set_tenant(self, claims, key, tenant_id, on, reason):
        return self._direct(claims, "tenant", key, tenant_id, None, on, reason, "set_tenant")

    def set_user(self, claims, key, tenant_id, user_id, on, reason):
        return self._direct(claims, "user", key, tenant_id, user_id, on, reason, "set_user")

    def set_percent(self, claims, key, basis_points, reason):
        return self._direct(claims, "percent", key, None, None, basis_points, reason, "set_percent")

    # --- two-person changes -------------------------------------------
    def propose(self, claims, kind, reason, *, key=None, tenant_id=None, user_id=None, value=True):
        """Step 1 (proposer: staff role, own step-up, consumed). Returns a
        Proposal; its id is given to a different staff human to approve."""
        action = "propose"
        d = self._validate(kind, key, tenant_id, user_id, value)
        staff = self._staff(claims, action)
        reason = _clean_reason(reason)
        plan = self._plan(kind, key, tenant_id, user_id, value)
        if plan is None or not (kind == "release_platform_kill" or (plan[5] and d.restricted)):
            raise FlagError("FLG-003")  # nothing to approve: use the direct call
        self._require_role(staff, action)
        self._spend_step_up(staff, action)
        now = self._now()
        p = Proposal(secrets.token_urlsafe(16), kind, key, tenant_id, user_id, value, reason,
                     staff.subject, now + PROPOSAL_TTL)
        self.store.put_proposal(p, now)
        return p

    def approve(self, claims, proposal_id):
        """Step 2 (a different staff human, role, own step-up, consumed). Applies
        exactly the proposed change if it is still valid and unchanged in kind."""
        action = "approve"
        staff = self._staff(claims, action)
        self._require_role(staff, action)
        p = self.store.take_proposal(proposal_id, self._now(), not_by=staff.subject)  # single use
        if p is None:
            self._deny(claims, action, "FLG-015")
            raise FlagError("FLG-015")
        self._spend_step_up(staff, action)
        self._validate(p.kind, p.flag_key, p.tenant_id, p.user_id, p.value)
        version = self.store.version()
        plan = self._plan(p.kind, p.flag_key, p.tenant_id, p.user_id, p.value)
        if plan is None:
            return None
        return self._commit(version, plan, p.proposer, p.reason, p.flag_key, p.tenant_id,
                            p.user_id, approved_by=staff.subject)

    # --- kill switch ---------------------------------------------------
    def engage_kill(self, claims, level, reason, *, key=None, tenant_id=None):
        """Stopping is the safe direction: staff human with MFA, no step-up."""
        self._kill_args(level, key, tenant_id)
        staff = self._staff(claims, "kill.engage")
        reason = _clean_reason(reason)
        version, k = self.store.version(), self.store.kill_state()
        new, old = self._kill_change(k, level, key, tenant_id, True)
        if old:
            return None
        plan = (f"kill.engage.{level}", False, True, None, new, False)
        return self._commit(version, plan, staff.subject, reason, key, tenant_id, None)

    def release_kill(self, claims, level, reason, *, key=None, tenant_id=None):
        """Release of a flag or tenant kill: staff human, fresh consumed step-up.
        The platform-wide switch is released only through propose/approve."""
        self._kill_args(level, key, tenant_id)
        if level == "platform":
            self._deny(claims, "kill.release", "FLG-014")
            raise FlagError("FLG-014")
        staff = self._staff(claims, "kill.release")
        reason = _clean_reason(reason)
        version, k = self.store.version(), self.store.kill_state()
        new, old = self._kill_change(k, level, key, tenant_id, False)
        if not old:
            return None
        self._spend_step_up(staff, "kill.release")
        plan = (f"kill.release.{level}", True, False, None, new, True)
        return self._commit(version, plan, staff.subject, reason, key, tenant_id, None)

    def _kill_args(self, level, key, tenant_id):
        ok = ((level == "platform" and key is None and tenant_id is None)
              or (level == "flag" and valid_key(key) and tenant_id is None and self.registry.get(key))
              or (level == "tenant" and key is None and valid_id(tenant_id)))
        if not ok:
            raise FlagError("FLG-003")

    @staticmethod
    def _kill_change(k, level, key, tenant_id, engage):
        if level == "platform":
            return dataclasses.replace(k, platform=engage), k.platform
        field = "flags" if level == "flag" else "tenants"
        member = key if level == "flag" else tenant_id
        cur = getattr(k, field)
        return (dataclasses.replace(k, **{field: frozenset(cur | {member} if engage else cur - {member})}),
                member in cur)
