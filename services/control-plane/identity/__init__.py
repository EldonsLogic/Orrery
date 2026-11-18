"""Identity core (PLT-005, ADR-0007): people, per-tenant memberships, sessions,
tokens, MFA policy, invites and staff support grants. Domain logic only: no
network server, no identity provider, no real users (Q-14). Production signing
and the identity provider come from the identity-provider spike."""

from .audit import AuditEvent, AuditLog
from .errors import IdentityError
from .invites import InviteService
from .models import (Channel, GrantStatus, Membership, MembershipStatus, Person, Realm,
                     StaffIdentity, TenantState, TenantStatus, TokenPair)
from .policy import RoleInfo, RoleResolver
from .repository import InMemoryRepository, Repository
from .service import IdentityService
from .signing import Signer, TestOnlyHmacSha256Signer
from .support import SupportGrantService
from .tokens import AccessClaims, RealmConfig

__all__ = [
    "AccessClaims", "AuditEvent", "AuditLog", "Channel", "GrantStatus", "IdentityError",
    "IdentityService", "InMemoryRepository", "InviteService", "Membership",
    "MembershipStatus", "Person", "Realm", "RealmConfig", "Repository", "RoleInfo",
    "RoleResolver", "Signer", "StaffIdentity", "SupportGrantService", "TenantState",
    "TenantStatus", "TestOnlyHmacSha256Signer", "TokenPair",
]
