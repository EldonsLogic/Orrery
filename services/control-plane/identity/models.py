"""Identity records (ADR-0007). The identity store holds people, memberships and
staff only: no tenant business data, no roles (roles live in the tenant)."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

Clock = Callable[[], int]  # injected; returns Unix seconds


class Realm(str, Enum):
    CUSTOMER = "customer"
    STAFF = "staff"


class TenantStatus(str, Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPORTED = "exported"
    DELETED = "deleted"


OPEN_TENANT = frozenset({TenantStatus.TRIAL, TenantStatus.ACTIVE})


class MembershipStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class GrantStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REVOKED = "revoked"


@dataclass(frozen=True)
class Channel:
    """A verified contact route an invite is bound to."""
    kind: str  # "email" or "phone"
    address: str

    def normalised(self) -> "Channel":
        addr = self.address.strip()
        return Channel(self.kind, addr.lower() if self.kind == "email" else addr)


@dataclass(frozen=True)
class Person:
    person_id: str
    display_name: str
    verified_channels: frozenset = frozenset()  # of Channel, already normalised
    mfa_enrolled: bool = False
    active: bool = True


@dataclass(frozen=True)
class Membership:
    person_id: str
    tenant_id: str
    status: MembershipStatus = MembershipStatus.ACTIVE
    session_version: int = 1
    mfa_required: bool = False
    invited_by: Optional[str] = None
    created_at: int = 0


@dataclass(frozen=True)
class StaffIdentity:
    """Staff realm: separate issuer and audience; MFA always mandatory."""
    staff_id: str
    display_name: str
    mfa_enrolled: bool = False
    active: bool = True
    session_version: int = 1
    verified_channels: frozenset = frozenset()
    linked_person_ids: frozenset = frozenset()  # customer persons of the same human


@dataclass(frozen=True)
class TenantState:
    tenant_id: str
    status: TenantStatus = TenantStatus.ACTIVE
    mfa_for_all: bool = False


@dataclass(frozen=True)
class Invite:
    invite_hash: str  # sha256 of the secret; the secret itself is never stored
    tenant_id: str
    channel: Channel
    created_by: str
    created_at: int
    expires_at: int
    used_at: Optional[int] = None


@dataclass(frozen=True)
class RefreshRecord:
    token_hash: str
    family_id: str
    person_id: str
    tenant_id: str
    session_version: int
    mfa_satisfied: bool
    auth_time: int
    expires_at: int
    used: bool = False
    revoked: bool = False


@dataclass(frozen=True)
class SupportGrant:
    grant_id: str
    staff_id: str
    tenant_id: str
    reason: str
    scope: frozenset
    requested_at: int
    duration: int
    status: GrantStatus = GrantStatus.PENDING
    approved_by: Optional[str] = None
    approved_at: Optional[int] = None
    expires_at: Optional[int] = None


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: Optional[str] = field(default=None, repr=False)
    expires_at: int = 0
