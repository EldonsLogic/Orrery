"""Plain data types of the chat service (OPR-010). No behaviour, no I/O."""
from __future__ import annotations

from dataclasses import dataclass, field

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


@dataclass(frozen=True)
class RouteRequest:
    tenant_id: str
    user_id: str
    role_ids: tuple
    session_id: str
    text: str
    locale: str
    previous_mode: str = DEFAULT_MODE


@dataclass(frozen=True)
class RunSetup:
    """Per-run inputs for the runtime factory."""
    window: Window
    mode: str
    locale: str
    cancel: object = field(default=None)  # runtime.CancelToken
