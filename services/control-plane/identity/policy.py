"""Roles come from the tenant, never from a request or a token (ADR-0007 items
2 and 9). The caller injects a RoleResolver; any unexpected result denies.
MFA policy (ADR-0007 item 6, SEC-005)."""

from dataclasses import dataclass
from typing import Protocol

from .errors import IdentityError

# Functions whose holders must use MFA. "owner" is added from SEC-005 ("MFA for
# owners"); ADR-0007 item 6 names isAdmin and finance/accounting (see Q-147).
MFA_FUNCTIONS = frozenset({"finance", "accounting", "owner"})
OWNER_FUNCTION = "owner"
INVITE_PERMISSION = "member.invite"


@dataclass(frozen=True)
class RoleInfo:
    name: str
    is_admin: bool = False
    functions: frozenset = frozenset()


class RoleResolver(Protocol):
    def roles_for(self, tenant_id: str, person_id: str):
        """Return the person's roles in that tenant from the tenant's assignment store."""


def resolve_roles(resolver, tenant_id: str, person_id: str) -> tuple:
    """Fail closed: an exception, None, a non-sequence or any non-RoleInfo item
    is IDN-012. An empty tuple is a valid answer (member with no roles)."""
    try:
        result = resolver.roles_for(tenant_id, person_id)
    except Exception:
        raise IdentityError("IDN-012") from None
    if not isinstance(result, (tuple, list)):
        raise IdentityError("IDN-012")
    roles = tuple(result)
    for role in roles:
        if (not isinstance(role, RoleInfo) or not isinstance(role.is_admin, bool)
                or not isinstance(role.functions, frozenset)):
            raise IdentityError("IDN-012")
    return roles


def role_requires_mfa(role: RoleInfo) -> bool:
    return role.is_admin or bool(role.functions & MFA_FUNCTIONS)


def mfa_required(roles: tuple, *, tenant_mfa_for_all: bool, membership_flag: bool) -> bool:
    return tenant_mfa_for_all or membership_flag or any(role_requires_mfa(r) for r in roles)


def is_owner(roles: tuple) -> bool:
    return any(OWNER_FUNCTION in r.functions for r in roles)


def is_owner_or_admin(roles: tuple) -> bool:
    return any(r.is_admin or OWNER_FUNCTION in r.functions for r in roles)


def has_invite_permission(caller_permissions) -> bool:
    """Permissions are data the caller resolved from the tenant, never request input."""
    return isinstance(caller_permissions, frozenset) and INVITE_PERMISSION in caller_permissions
