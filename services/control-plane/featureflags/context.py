"""Evaluation context built only from verified claims (PLT-005). Tenant and user
are read from the claims on every call, never stored separately, so a mutated or
forged context cannot change who is being evaluated."""

from identity import IdentityError
from identity.tokens import AccessClaims, check_live

from .errors import FlagError
from .model import valid_id

_PROOF = object()


class EvalContext:
    __slots__ = ("claims",)

    def __init__(self, claims, _proof=None):
        if _proof is not _PROOF:
            raise FlagError("FLG-020")
        object.__setattr__(self, "claims", claims)

    def __setattr__(self, name, value):
        raise FlagError("FLG-020")

    def __delattr__(self, name):
        raise FlagError("FLG-020")

    @property
    def tenant_id(self):
        return self.claims.tenant

    @property
    def user_id(self):
        return self.claims.subject

    @classmethod
    def from_claims(cls, claims, now: int) -> "EvalContext":
        derive(claims, now)
        return cls(claims, _PROOF)


def derive(claims, now: int):
    """(tenant, user) from verified, live claims, or FLG-020. The evaluator calls
    this on every evaluation and uses only its result."""
    if not isinstance(claims, AccessClaims):
        raise FlagError("FLG-020")
    try:
        check_live(claims, now)
    except IdentityError:
        raise FlagError("FLG-020") from None
    tenant, subject = claims.tenant, claims.subject
    if not valid_id(subject) or (tenant is not None and not valid_id(tenant)):
        raise FlagError("FLG-020")
    return tenant, subject
