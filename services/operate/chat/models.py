"""Plain data types of the chat service (OPR-010). No behaviour, no I/O."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Protocol

MODES = ("discover", "ask", "act", "change")
DEFAULT_MODE = "ask"  # least privileged: reads and explains, never starts a change on its own


@dataclass(frozen=True)
class Session:
    """One conversation of one user in one tenant. `thread_id` is the AG-UI thread."""
    tenant_id: str
    user_id: str
    session_id: str
    thread_id: str
    locale: str = "en"
    created_at: float = 0.0
    last_active: float = 0.0


@dataclass(frozen=True)
class Entry:
    """One history turn. Stored as data: it is replayed to the model only as an L3 data item."""
    seq: int
    role: str            # user | assistant
    text: str
    message_id: str
    locale: str = "en"
    cancelled: bool = False


@dataclass(frozen=True)
class MessageRecord:
    """Client message id bookkeeping for dedup: which text it carried and how its run ended."""
    message_id: str
    text_hash: str
    status: str          # running | done | cancelled | failed
    assistant_message_id: str = ""
    run_id: str = ""


@dataclass(frozen=True)
class Window:
    """What one run may see: the pinned frame (instructions) and the newest turns that fit as data items."""
    frame: str
    items: tuple         # of runtime.DataItem
    dropped: int = 0


@dataclass(frozen=True)
class ChatLimits:
    max_message_chars: int = 8_000
    max_history_chars: int = 24_000     # total characters of history shown to the model
    max_history_items: int = 40
    max_entry_chars: int = 4_000        # one old turn is cut to this when it is shown
    max_stored_entries: int = 400       # store-side cap until the retention policy (OPR-012) takes over
    run_ttl_s: float = 300.0            # an active-run mark older than this is stale (crash) and is taken over
    max_numbers: int = 20


PRIVILEGED = ("act", "change")
RISKS = ("R0", "R1", "R2", "R3", "R4")  # same order as router.models.RISK_ORDER (tested equal)


@dataclass(frozen=True)
class PendingBinding:
    """The one confirmation the chat is waiting for in a session. Set by the chat service from its own trusted state
    after the preview was shown (Q-282), never from message text. A bare yes can confirm only this."""
    mode: str
    action_id: str
    args_hash: str
    risk: str
    expires_at: float

    def __post_init__(self):
        if (self.mode not in PRIVILEGED or not self.action_id or not self.args_hash or self.risk not in RISKS
                or type(self.expires_at) not in (int, float) or not math.isfinite(self.expires_at)):
            raise ValueError("a pending binding needs a privileged mode, action_id, args_hash, risk and a finite expiry")


@dataclass(frozen=True)
class RouteRequest:
    tenant_id: str
    user_id: str
    role_ids: tuple
    session_id: str
    text: str
    locale: str
    previous_mode: str = DEFAULT_MODE
    pending: Optional[PendingBinding] = None   # the chat's pending confirmation for this session, if any
    now: Optional[float] = None                # the chat's trusted clock reading (same clock as the change service)


@dataclass(frozen=True)
class RouteResult:
    """What the router port returns: the mode plus the confirmation binding it established. Advisory only: the
    chat re-checks the binding against its own pending and the change service re-checks it again (Q-265)."""
    mode: str
    risk_hint: str = "R0"
    requires_confirmation: bool = False
    confirms_action_id: Optional[str] = None
    confirms_args_hash: Optional[str] = None
    resolves_pending: Optional[str] = None    # confirmed | declined | expired: the pending the turn answered
    decision: object = field(default=None, compare=False, repr=False)  # the router's own decision, passed to confirm


class ChangePort(Protocol):
    """change.ChangeService as the chat sees it. `propose` returns a Preview, `confirm` an Outcome; both raise
    ChangeRefused (a code and bilingual text from a closed table) and nothing else is shown to the customer."""

    def propose(self, principal, session_id: str, turn: str, decision, locale: str = "en", data: tuple = ()): ...

    def confirm(self, principal, session_id: str, decision, locale: str = "en"): ...

    def cancel(self, principal, session_id: str) -> None: ...


@dataclass(frozen=True)
class RunSetup:
    """Per-run inputs for the runtime factory."""
    window: Window
    mode: str
    locale: str
    cancel: object = field(default=None)  # runtime.CancelToken
