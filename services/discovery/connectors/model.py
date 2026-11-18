"""Connector protocol, limits, budget, run context and the registry (PI-006)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

# What "sandbox" means in this package (PI-006): a LOGICAL boundary only. Connectors run in the
# caller's process; the runner restricts what they may declare and return (capability allow-list,
# tier/capability/output consistency, labelled and sanitised output, platform-owned budget). It does
# NOT stop a connector from calling the network or the filesystem. OS-level isolation (worker
# process, no network, rlimits, wall-clock kill) is a later infra row; until then only reviewed
# first-party connectors may be registered.
SANDBOX = "logical"

TIERS = {1: "api_read_only", 2: "file_upload", 3: "document_ocr", 4: "inbox_forward", 5: "isolated_browser"}
# Allow-list: a connector may only declare read-side capabilities. Anything else (network, send,
# write, exec, ...) is refused at registration and at run (PI-006).
ALLOWED_CAPABILITIES = frozenset({"read", "parse", "ocr", "decode"})
# Capabilities each tier may declare, and the output a capability unlocks (checked at registration
# and again against what the connector returns).
TIER_CAPABILITIES = {1: frozenset({"read", "parse"}), 2: frozenset({"read", "parse", "decode"}),
                     3: frozenset({"read", "parse", "ocr", "decode"}), 4: frozenset({"read", "parse", "decode"}),
                     5: frozenset()}
ID_RE = re.compile(r"^[a-z][a-z0-9_.\-]{0,63}$")
VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+\-]{0,31}$")
DATA_CLASSES = ("C0", "C1", "C2", "C3", "C4")


class ConnectorRefusal(Exception):
    """Coded refusal. `code` is a stable CON- code; never partial output."""

    def __init__(self, code: str, reason: str):
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


class BudgetExceeded(Exception):
    def __init__(self, kind: str, limit: int):
        super().__init__(f"{kind} limit {limit}")
        self.kind = kind
        self.limit = limit


@dataclass(frozen=True)
class Limits:
    max_input_bytes: int = 5_000_000
    max_items: int = 1_000
    max_fields: int = 20_000
    max_field_chars: int = 20_000
    max_total_chars: int = 2_000_000
    # About 16 steps per cell end to end (parse, JSON check twice, label). max_fields (20,000) is the
    # tighter cap, so 500,000 steps cover a full default job; a test pins that alignment.
    max_steps: int = 500_000
    max_depth: int = 8


class Budget:
    """Deterministic time-like budget: connectors call tick(); no clocks are read.

    The limit is set once by the platform. `max_steps` and `used` are read-only properties, and the
    runner hands connectors a `handle()` (tick only) and re-checks the real budget after each phase."""
    __slots__ = ("_max", "_used")

    def __init__(self, max_steps: int):
        self._max = max_steps
        self._used = 0

    @property
    def max_steps(self) -> int:
        return self._max

    @property
    def used(self) -> int:
        return self._used

    def tick(self, n: int = 1) -> None:
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise BudgetExceeded("steps", self._max)  # a negative tick would refund budget
        self._used += n
        if self._used > self._max:
            raise BudgetExceeded("steps", self._max)

    def handle(self) -> "BudgetHandle":
        """What a connector receives: it can spend, never read internals or change the limit."""
        return BudgetHandle(self.tick)


class BudgetHandle:
    __slots__ = ("tick",)

    def __init__(self, tick: Callable[..., None]):
        object.__setattr__(self, "tick", tick)

    def __setattr__(self, k: str, v: Any) -> None:
        raise AttributeError("budget handle is read-only")


@dataclass(frozen=True)
class RunContext:
    """Set by the platform, never by the connector or the content."""
    tenant_id: str
    job_id: str
    data_class: str = "C3"  # uploads are C3 until scanned and classified (data-classification.md)
    limits: Limits = field(default_factory=Limits)
    protected_names: tuple = ()  # tenant domains, role and tool names for the confusable check
    sender_allowlist: tuple = ()  # owner-set (T19); empty means none configured
    include_hidden: bool = False  # owner opted in during mapping (D-6 proposal)


@runtime_checkable
class Connector(Protocol):
    id: str
    version: str
    tier: int
    writes: bool
    capabilities: frozenset

    def extract(self, source: bytes, budget: Budget) -> list: ...

    def normalise(self, raw: list, budget: Budget) -> dict: ...


def check_connector(c: Any) -> None:
    """Raise ConnectorRefusal unless the connector may run at all."""
    for attr, rx in (("id", ID_RE), ("version", VERSION_RE)):
        v = getattr(c, attr, None)
        if not isinstance(v, str) or not rx.match(v):  # these strings reach every envelope's source
            raise ConnectorRefusal("CON-003", f"connector missing or malformed {attr}")
    for m in ("extract", "normalise"):
        if not callable(getattr(c, m, None)):
            raise ConnectorRefusal("CON-003", f"connector missing {m}")
    tier = getattr(c, "tier", None)
    if isinstance(tier, bool) or tier not in TIERS:
        raise ConnectorRefusal("CON-001", "connector has no valid tier (1-5)")
    if tier == 5:
        raise ConnectorRefusal("CON-005", "tier 5 needs its own ADR and security review")
    if getattr(c, "writes", None) is not False:
        raise ConnectorRefusal("CON-002", "connector must declare writes=False (PI-006)")
    caps = getattr(c, "capabilities", None)
    if not isinstance(caps, (set, frozenset, tuple, list)):
        raise ConnectorRefusal("CON-002", "connector must declare capabilities")
    bad = sorted(str(x) for x in caps if x not in ALLOWED_CAPABILITIES)
    if bad:
        raise ConnectorRefusal("CON-002", f"side-effecting or unknown capability: {', '.join(bad)} (PI-006)")
    extra = sorted(str(x) for x in caps if x not in TIER_CAPABILITIES[tier])
    if extra:
        raise ConnectorRefusal("CON-018", f"capability not allowed for tier {tier}: {', '.join(extra)}")


class Registry:
    def __init__(self) -> None:
        self._items: dict[str, Any] = {}

    def register(self, c: Any) -> None:
        check_connector(c)
        if c.id in self._items:
            raise ConnectorRefusal("CON-004", f"duplicate connector id {c.id}")
        self._items[c.id] = c

    def get(self, cid: str) -> Any:
        try:
            return self._items[cid]
        except KeyError:
            raise ConnectorRefusal("CON-006", f"unknown connector {cid}") from None

    def ids(self) -> list:
        return sorted(self._items)
