"""Plain types and ports of change-by-chat (OPR-009). Ports are injected; tests use fakes. No model calls here."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

# impact class of a diff operation (bpdiff.classify.IMPACTS) -> action-policy risk class
IMPACT_RISK = {"cosmetic": "R1", "branding": "R1", "config": "R2", "data_shape": "R2",
               "destructive": "R3", "access": "R4", "compliance": "R4"}
MAX_CHAT_RISK = "R2"          # a chat change above this is refused: it needs the full Studio review (Q-280)
ACTION_ID = "blueprint.apply_change"
DEFAULT_TTL_S = 300.0


@dataclass(frozen=True)
class DraftRequest:
    """What the drafter sees: the user's own words, the locale and the ids that exist. No data items, no labels."""
    turn: str
    locale: str
    outline: dict          # {"entities": {entity_id: [field_id, ...]}, "workflows": [...], "reports": [...]}


class ChangeDrafterPort(Protocol):
    def draft(self, request: DraftRequest) -> object:
        """Return {"edits": [{"op": "set|add|remove", "path": [...], "value": ...}]} or the list itself. The result is
        untrusted: it is decoded and applied by code, then validated, diffed and risk-classified."""


class BlueprintPort(Protocol):
    """The existing Blueprint path. The only way a change reaches the engine; chat never writes the engine."""

    def current(self, tenant_id: str) -> dict:
        """The tenant's current Blueprint (a copy)."""

    def validation_context(self, tenant_id: str) -> object:
        """A validator.ValidationContext (registry, tool set) or None."""

    def submit_change(self, tenant_id: str, diff: dict, proposal_digest: str, idempotency_key: str) -> dict:
        """Hand the diff to the Blueprint apply path (preview digest, DDL plan gate, guarded apply: BPL-007). That path
        re-checks the base hash and its own gates. Raise on refusal; return a small result dict."""


@dataclass(frozen=True)
class Proposal:
    tenant_id: str
    user_id: str
    session_id: str
    edits: tuple                 # of edits.Edit, as drafted and accepted
    base_hash: str
    target_hash: str
    diff_hash: str
    diff: dict
    risk: str
    digest: str                  # binds tenant, user, session, base, target, diff, risk, expiry (see service.digest_of)
    created_at: float
    expires_at: float

    @property
    def action_id(self) -> str:
        return f"{ACTION_ID}:{self.digest[7:23]}"


@dataclass(frozen=True)
class Preview:
    """What the user sees before confirming. Everything comes from the diff; no model prose."""
    action_id: str
    digest: str
    risk: str
    expires_at: float
    ops: tuple                   # of {code, impact, subject, property, pointer, before, after, labels}
    counts: dict
    needs_ddl_plan_gate: bool
    text: str                    # deterministic bilingual summary line
    locale: str


@dataclass(frozen=True)
class Outcome:
    status: str                  # applied
    digest: str
    result: dict = field(default_factory=dict)
    text: str = ""


class ProposalStore(Protocol):
    def put(self, p: Proposal) -> None: ...
    def active(self, tenant_id: str, user_id: str, session_id: str) -> Optional[Proposal]: ...
    def consume(self, p: Proposal) -> bool:
        """Atomically mark this proposal used. True only for the first caller."""
    def used(self, digest: str) -> bool: ...
    def drop(self, tenant_id: str, user_id: str, session_id: str) -> None: ...
