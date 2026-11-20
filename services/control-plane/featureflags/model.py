"""Typed flag definitions and state. Flags are boolean and decide whether a code
path is reached; they carry no value, role, permission, rate or text, so there is
nothing in one that can be a secret. The checks behind the path still run."""

import re
from dataclasses import dataclass
from typing import Optional

from .errors import FlagError

KEY_RE = re.compile(r"[a-z][a-z0-9_]{0,31}(\.[a-z][a-z0-9_]{0,31}){0,3}")
ID_RE = re.compile(r"[A-Za-z0-9_.:\-]{1,128}")
RESTRICTED_CATEGORIES = frozenset({"agent_authority", "money", "compliance"})
CATEGORIES = RESTRICTED_CATEGORIES | {"rollout"}
PERCENT_BY = ("tenant", "user")
MAX_BP = 10_000
MAX_ENTRIES = 10_000  # tenants or users per flag


def valid_key(value) -> bool:
    return isinstance(value, str) and len(value) <= 64 and KEY_RE.fullmatch(value) is not None


def valid_id(value) -> bool:
    return isinstance(value, str) and ID_RE.fullmatch(value) is not None


@dataclass(frozen=True)
class FlagDef:
    key: str
    category: str = "rollout"  # rollout | agent_authority | money | compliance
    default: bool = False
    percent_by: str = "tenant"  # bucket by tenant or by (tenant, user)

    @property
    def restricted(self) -> bool:
        """Agent authority, money and compliance flags gate paths that act on those
        things: enabling needs two staff humans (ADR-0027, ADR-0047, ADR-0048)."""
        return self.category in RESTRICTED_CATEGORIES

    @property
    def label_key(self) -> str:
        return f"flags.{self.key}.label"

    @property
    def description_key(self) -> str:
        return f"flags.{self.key}.description"


class Registry:
    """Flags exist only if defined here, in code. Anything else is unknown (OFF)."""

    def __init__(self, defs):
        table = {}
        for d in defs:
            if (not isinstance(d, FlagDef) or not valid_key(d.key) or d.key in table
                    or d.category not in CATEGORIES or not isinstance(d.default, bool)
                    or d.percent_by not in PERCENT_BY):
                raise FlagError("FLG-001")
            if d.restricted and d.default is not False:
                raise FlagError("FLG-001")  # a restricted flag starts and stays OFF
            table[d.key] = d
        self._defs = table

    def get(self, key) -> Optional[FlagDef]:
        return self._defs.get(key) if valid_key(key) else None

    def keys(self):
        return sorted(self._defs)

    def __iter__(self):
        return iter(self._defs.values())


@dataclass(frozen=True)
class FlagState:
    global_value: Optional[bool] = None  # None: unset, use the definition default
    tenants: frozenset = frozenset()  # tenant ids switched on
    users: frozenset = frozenset()  # (tenant_id, user_id) pairs switched on
    percent_bp: int = 0  # 0..10000, deterministic bucket


@dataclass(frozen=True)
class KillState:
    platform: bool = False
    flags: frozenset = frozenset()
    tenants: frozenset = frozenset()


@dataclass(frozen=True)
class AuditRecord:
    seq: int
    at: int
    staff_id: str
    approved_by: Optional[str]  # second staff human for approved changes
    action: str
    flag_key: Optional[str]
    tenant_id: Optional[str]
    user_id: Optional[str]
    old: object  # bool, int or None
    new: object
    reason: str
    key_id: str
    prev_seal: str
    seal: str  # HMAC over the record and prev_seal (keyed, see store.AuditSealer)


@dataclass(frozen=True)
class TenantAuditView:
    """What a tenant may see of a change scoped to it: no staff ids, no free text."""
    seq: int
    at: int
    action: str
    flag_key: Optional[str]
    old: object
    new: object


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    kind: str  # global | tenant | user | percent | release_platform_kill
    flag_key: Optional[str]
    tenant_id: Optional[str]
    user_id: Optional[str]
    value: object
    reason: str
    proposer: str
    expires_at: int
