"""Flag changes. Humans only: the caller must present verified staff-realm claims
for an active, MFA-satisfied staff member. Enabling a restricted flag (agent
authority, money, compliance) and every kill release need a fresh MFA step-up.
Every change is an append-only audit record (who, when, old, new, reason)."""

import dataclasses
import re

from identity import IdentityError, Realm
from identity.tokens import AccessClaims, check_live

from .errors import FlagError
from .evaluator import read_clock
from .model import MAX_BP, MAX_ENTRIES, FlagState, KillState, valid_id, valid_key

_REASON = re.compile(r"[^\x00-\x1f\x7f]{3,200}")


class FlagAdmin:
    def __init__(self, idn, registry, store, clock):
        self.idn, self.registry, self.store, self.clock = idn, registry, store, clock

    # --- caller checks -------------------------------------------------
    def _staff(self, claims, *, step_up=False, action="") -> str:
        try:
            if not isinstance(claims, AccessClaims):
                raise FlagError("FLG-010")  # agents, services and raw ids are not claims
            now = read_clock(self.clock)
            check_live(claims, now)
            if claims.realm is not Realm.STAFF or claims.tenant is not None or not claims.mfa_satisfied:
                raise FlagError("FLG-010")
            staff = self.idn.repo.get_staff(claims.subject)
            if staff is None or not staff.active or staff.session_version != claims.session_version:
                raise FlagError("FLG-010")
            if step_up:
                try:
                    self.idn.require_step_up(claims)
                except IdentityError:
                    raise FlagError("FLG-011") from None
            return claims.subject
        except IdentityError:
            self._deny(claims, action, "FLG-010")
            raise FlagError("FLG-010") from None
        except FlagError as e:
            self._deny(claims, action, e.code)
            raise

    def _deny(self, claims, action, code):
        try:
            subject = getattr(claims, "subject", None)
            self.store.note_denial({"at": self.clock(), "action": action, "code": code,
                                    "subject": subject if valid_id(subject) else None})
        except Exception:
            pass

    @staticmethod
    def _reason(reason) -> str:
        if not isinstance(reason, str) or _REASON.fullmatch(reason) is None:
            raise FlagError("FLG-003")
        return reason

    def _def(self, key):
        d = self.registry.get(key)
        if d is None:
            raise FlagError("FLG-002")
        return d

    def _commit(self, version, staff_id, action, reason, old, new, *, key=None, tenant=None,
                user=None, flag_state=None, kill=None):
        entry = dict(at=read_clock(self.clock), staff_id=staff_id, action=action, flag_key=key,
                     tenant_id=tenant, user_id=user, old=old, new=new, reason=reason)
        return self.store.commit(version, flag_key=key, flag_state=flag_state, kill=kill, entry=entry)

    # --- flag state ----------------------------------------------------
    def set_global(self, claims, key, on, reason):
        d = self._def(key)
        if type(on) is not bool:
            raise FlagError("FLG-003")
        staff = self._staff(claims, step_up=on and d.restricted, action="set_global")
        reason = self._reason(reason)
        version, s = self.store.version(), self.store.get_flag(key)
        if s.global_value is on:
            return None
        return self._commit(version, staff, "set_global", reason, s.global_value, on, key=key,
                            flag_state=dataclasses.replace(s, global_value=on))

    def set_tenant(self, claims, key, tenant_id, on, reason):
        d = self._def(key)
        if type(on) is not bool or not valid_id(tenant_id):
            raise FlagError("FLG-003")
        staff = self._staff(claims, step_up=on and d.restricted, action="set_tenant")
        reason = self._reason(reason)
        version, s = self.store.version(), self.store.get_flag(key)
        old = tenant_id in s.tenants
        if old is on:
            return None
        tenants = s.tenants | {tenant_id} if on else s.tenants - {tenant_id}
        if len(tenants) > MAX_ENTRIES:
            raise FlagError("FLG-003")
        return self._commit(version, staff, "set_tenant", reason, old, on, key=key, tenant=tenant_id,
                            flag_state=dataclasses.replace(s, tenants=frozenset(tenants)))

    def set_user(self, claims, key, tenant_id, user_id, on, reason):
        d = self._def(key)
        if type(on) is not bool or not valid_id(tenant_id) or not valid_id(user_id):
            raise FlagError("FLG-003")
        staff = self._staff(claims, step_up=on and d.restricted, action="set_user")
        reason = self._reason(reason)
        version, s = self.store.version(), self.store.get_flag(key)
        pair = (tenant_id, user_id)
        old = pair in s.users
        if old is on:
            return None
        users = s.users | {pair} if on else s.users - {pair}
        if len(users) > MAX_ENTRIES:
            raise FlagError("FLG-003")
        return self._commit(version, staff, "set_user", reason, old, on, key=key, tenant=tenant_id,
                            user=user_id, flag_state=dataclasses.replace(s, users=frozenset(users)))

    def set_percent(self, claims, key, basis_points, reason):
        d = self._def(key)
        if type(basis_points) is not int or not 0 <= basis_points <= MAX_BP:
            raise FlagError("FLG-003")
        version, s = self.store.version(), self.store.get_flag(key)
        staff = self._staff(claims, step_up=d.restricted and basis_points > s.percent_bp,
                            action="set_percent")
        reason = self._reason(reason)
        if basis_points == s.percent_bp:
            return None
        return self._commit(version, staff, "set_percent", reason, s.percent_bp, basis_points,
                            key=key, flag_state=dataclasses.replace(s, percent_bp=basis_points))

    # --- kill switch ---------------------------------------------------
    def engage_kill(self, claims, level, reason, *, key=None, tenant_id=None):
        """Stopping is the safe direction: staff human with MFA, no step-up."""
        self._kill_args(level, key, tenant_id)
        staff = self._staff(claims, action="kill.engage")
        reason = self._reason(reason)
        version, k = self.store.version(), self.store.kill_state()
        new, old = self._kill_change(k, level, key, tenant_id, True)
        if old:
            return None
        return self._commit(version, staff, f"kill.engage.{level}", reason, False, True,
                            key=key, tenant=tenant_id, kill=new)

    def release_kill(self, claims, level, reason, *, key=None, tenant_id=None, second=None):
        """Releasing needs a fresh step-up; the platform-wide switch also needs a
        second, different staff human with their own step-up (SEC-020 section 12)."""
        self._kill_args(level, key, tenant_id)
        staff = self._staff(claims, step_up=True, action="kill.release")
        if level == "platform":
            other = self._staff(second, step_up=True, action="kill.release.second") \
                if second is not None else None
            if other is None or other == staff:
                self._deny(claims, "kill.release", "FLG-012")
                raise FlagError("FLG-012")
        reason = self._reason(reason)
        version, k = self.store.version(), self.store.kill_state()
        new, old = self._kill_change(k, level, key, tenant_id, False)
        if not old:
            return None
        return self._commit(version, staff, f"kill.release.{level}", reason, True, False,
                            key=key, tenant=tenant_id, kill=new)

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
