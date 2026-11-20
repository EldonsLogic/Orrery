"""Evaluation context built only from verified claims (PLT-005). Tenant and user
come from the token, never from a request field, header or body."""

import contextvars
from dataclasses import dataclass
from typing import Optional

from identity import IdentityError
from identity.tokens import AccessClaims, check_live

from .errors import FlagError
from .model import valid_id

_MINT = contextvars.ContextVar("featureflags_mint", default=False)


@dataclass(frozen=True)
class EvalContext:
    claims: AccessClaims
    tenant_id: Optional[str]
    user_id: str

    def __post_init__(self):
        if not _MINT.get():
            raise FlagError("FLG-020")

    @classmethod
    def from_claims(cls, claims, now: int) -> "EvalContext":
        """Raises FLG-020 for anything that did not come from `decode`, is outside
        its time window, or carries odd ids. The evaluator re-checks on every call."""
        if not isinstance(claims, AccessClaims):
            raise FlagError("FLG-020")
        try:
            check_live(claims, now)
        except IdentityError:
            raise FlagError("FLG-020") from None
        tenant, subject = claims.tenant, claims.subject
        if not valid_id(subject) or (tenant is not None and not valid_id(tenant)):
            raise FlagError("FLG-020")
        token = _MINT.set(True)
        try:
            return cls(claims, tenant, subject)
        finally:
            _MINT.reset(token)
