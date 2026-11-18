"""Access-token encoding and verification (ADR-0007 items 3, 7, 10).

Compact form: base64url(header).base64url(claims).base64url(signature).
Claims carry no roles or permissions. One tenant per customer token; the
customer audience names that tenant. Staff tokens carry no tenant. Every check
fails closed with a typed IDN code."""

import base64
import json
import re
import secrets
from dataclasses import dataclass
from typing import Optional

from .errors import IdentityError
from .models import Realm
from .signing import FORBIDDEN_ALGS, Signer, check_signer

TOKEN_TYPE = "access"
MAX_TOKEN_LEN = 4096
MIN_TTL, MAX_TTL = 300, 900  # ADR-0007 item 10: access tokens live 5-15 minutes
CLAIM_KEYS = frozenset({"iss", "aud", "sub", "tid", "realm", "sv", "mfa",
                        "auth_time", "iat", "nbf", "exp", "jti"})
_B64 = re.compile(r"[A-Za-z0-9_-]*")


@dataclass(frozen=True)
class RealmConfig:
    realm: Realm
    issuer: str
    audience: str  # customer tokens use "<audience>/tenant/<tenant_id>"
    signer: Signer
    access_ttl: int = 600

    def __post_init__(self):
        check_signer(self.signer)
        if (not isinstance(self.realm, Realm) or not self.issuer or not self.audience
                or not MIN_TTL <= self.access_ttl <= MAX_TTL):
            raise IdentityError("IDN-051")

    def audience_for(self, tenant_id: Optional[str]) -> str:
        if self.realm is Realm.CUSTOMER:
            return f"{self.audience}/tenant/{tenant_id}"
        return self.audience


@dataclass(frozen=True)
class AccessClaims:
    issuer: str
    audience: str
    subject: str
    tenant: Optional[str]
    realm: Realm
    session_version: int
    mfa_satisfied: bool
    auth_time: int
    issued_at: int
    not_before: int
    expires_at: int
    token_id: str


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    if not _B64.fullmatch(text) or len(text) % 4 == 1:
        raise IdentityError("IDN-001")
    raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    if _b64e(raw) != text:  # reject non-canonical encodings (malleability)
        raise IdentityError("IDN-001")
    return raw


def _no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise IdentityError("IDN-001")
        out[key] = value
    return out


def _bad_constant(_):
    raise IdentityError("IDN-001")


def _json(raw: bytes) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates,
                           parse_constant=_bad_constant)
    except (UnicodeDecodeError, ValueError):
        raise IdentityError("IDN-001") from None
    if not isinstance(value, dict):
        raise IdentityError("IDN-001")
    return value


def _dump(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _header(cfg: RealmConfig) -> dict:
    return {"alg": cfg.signer.alg, "kid": cfg.signer.key_id, "typ": TOKEN_TYPE}


def encode(cfg: RealmConfig, *, subject: str, tenant: Optional[str], session_version: int,
           mfa_satisfied: bool, auth_time: int, now: int) -> tuple:
    """Return (token, expires_at). Callers have already made every policy check."""
    if (cfg.realm is Realm.CUSTOMER) != bool(tenant):
        raise IdentityError("IDN-051")
    exp = now + cfg.access_ttl
    claims = {"iss": cfg.issuer, "aud": cfg.audience_for(tenant), "sub": subject,
              "tid": tenant, "realm": cfg.realm.value, "sv": session_version,
              "mfa": bool(mfa_satisfied), "auth_time": auth_time, "iat": now,
              "nbf": now, "exp": exp, "jti": secrets.token_urlsafe(16)}
    signing_input = _b64e(_dump(_header(cfg))) + "." + _b64e(_dump(claims))
    sig = cfg.signer.sign(signing_input.encode("ascii"))
    return signing_input + "." + _b64e(sig), exp


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_str(v) -> bool:
    return isinstance(v, str) and 0 < len(v) <= 256


def decode(token, cfg: RealmConfig, *, now: int, tenant: Optional[str]) -> AccessClaims:
    """Verify signature, header, claims, realm, tenant and time. Order matters:
    nothing in the payload is trusted before the signature is checked."""
    if not isinstance(token, str) or not 0 < len(token) <= MAX_TOKEN_LEN:
        raise IdentityError("IDN-001")
    parts = token.split(".")
    if len(parts) != 3:
        raise IdentityError("IDN-001")
    header = _json(_b64d(parts[0]))
    alg = header.get("alg")
    if not isinstance(alg, str) or alg in FORBIDDEN_ALGS or alg != cfg.signer.alg:
        raise IdentityError("IDN-002")
    if header != _header(cfg):
        raise IdentityError("IDN-002")
    sig = _b64d(parts[2])
    if not sig or not cfg.signer.verify((parts[0] + "." + parts[1]).encode("ascii"), sig):
        raise IdentityError("IDN-003")
    c = _json(_b64d(parts[1]))
    if set(c) != CLAIM_KEYS:
        raise IdentityError("IDN-008")
    if not (all(_is_str(c[k]) for k in ("iss", "aud", "sub", "realm", "jti"))
            and all(_is_int(c[k]) for k in ("sv", "auth_time", "iat", "nbf", "exp"))
            and isinstance(c["mfa"], bool) and (c["tid"] is None or _is_str(c["tid"]))):
        raise IdentityError("IDN-008")
    try:
        realm = Realm(c["realm"])
    except ValueError:
        raise IdentityError("IDN-050") from None
    if realm is not cfg.realm or c["iss"] != cfg.issuer:
        raise IdentityError("IDN-006")
    if c["tid"] != tenant:
        raise IdentityError("IDN-007")
    if c["aud"] != cfg.audience_for(tenant):
        raise IdentityError("IDN-006")
    if c["nbf"] > now or c["iat"] > now:
        raise IdentityError("IDN-005")
    if c["exp"] <= now:
        raise IdentityError("IDN-004")
    if c["exp"] - c["iat"] > MAX_TTL or c["auth_time"] > c["iat"]:
        raise IdentityError("IDN-008")
    return AccessClaims(c["iss"], c["aud"], c["sub"], c["tid"], realm, c["sv"], c["mfa"],
                        c["auth_time"], c["iat"], c["nbf"], c["exp"], c["jti"])
