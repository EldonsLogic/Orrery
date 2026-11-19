"""Interfaces the endpoint depends on. Real implementations are the identity service, the Tool API gateway
and the agent runtime; tests inject fakes. Nothing here can approve anything (ADR-0044 item 2)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Protocol


@dataclass(frozen=True)
class Principal:
    """The verified caller. Tenant and roles come from the identity service, never from the request."""
    tenant_id: str
    subject: str
    role_ids: tuple = ()
    session_id: str = ""


@dataclass(frozen=True)
class Approval:
    """A pending approval that the Tool API already created (display only)."""
    id: str
    summary: str = ""
    status: str = "pending"


@dataclass(frozen=True)
class RuntimeUsage:
    """Yielded by the runtime; becomes a `meter.ai_usage` event, never a wire event."""
    model_id: str
    tier: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    cost_micro_usd: int = 0


@dataclass(frozen=True)
class RuntimeContext:
    """All the runtime gets. There is no client state, no client tools and no client roles in here."""
    principal: Principal
    thread_id: str
    run_id: str
    user_text: str
    server_state: dict = field(default_factory=dict)
    locale: str = "en"
    run_approvals: list = field(default_factory=list)  # approval ids this run created (runtime appends; M7)


class TokenVerifier(Protocol):
    def verify(self, token: str, tenant_id: str) -> Principal:
        """Raise on any failure. Wraps IdentityService.verify_customer_token and caller_roles."""


class AgentRuntime(Protocol):
    model_id: str
    prompt_version: str

    def run(self, ctx: RuntimeContext) -> Iterable:
        """Yield AG-UI event dicts and RuntimeUsage items. Real model calls live behind this (OPR-001)."""


class ApprovalReader(Protocol):
    """Read-only view of Tool API approvals (`approval.list_mine`). Deciding is the approval endpoint's job."""

    def pending(self, principal: Principal) -> Iterable[Approval]: ...

    def get(self, principal: Principal, approval_id: str) -> Optional[Approval]: ...


class IdentityAdapter:
    """TokenVerifier over `IdentityService` (services/control-plane/identity)."""

    def __init__(self, identity):
        self._identity = identity

    def verify(self, token: str, tenant_id: str) -> Principal:
        claims = self._identity.verify_customer_token(token, tenant_id)
        if claims.tenant != tenant_id:
            raise PermissionError("tenant mismatch")
        roles = tuple(getattr(r, "id", r) for r in self._identity.caller_roles(claims, tenant_id))
        return Principal(tenant_id=claims.tenant, subject=claims.subject, role_ids=roles,
                         session_id=claims.token_id)
