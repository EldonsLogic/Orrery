"""Resumable interview session: plain data, JSON round trip, validated on load (stored state is untrusted)."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Optional

from .catalog import Catalog, ValueRejected, validate_values

STATES = ("asking", "complete")
STATUSES = ("confirmed", "proposed", "default")
SOURCES = ("owner", "document", "template")
FLAG_KINDS = ("contradiction", "uncertain", "injection_suspected", "extraction_rejected",
              "ungrounded", "cross_check", "budget")
MAX_FLAGS = 200


class SessionInvalid(ValueError):
    pass


@dataclass
class Session:
    id: str
    language: str = "en"
    state: str = "asking"
    current: Optional[str] = None
    answers: dict = field(default_factory=dict)   # qid -> {"values", "source", "status", "doc"?}
    pending: dict = field(default_factory=dict)   # qid -> new values awaiting a contradiction decision
    flags: list = field(default_factory=list)     # {"kind", "qid", "detail", "turn"}
    retries: dict = field(default_factory=dict)   # qid -> failed attempts
    turns: int = 0
    port_calls: int = 0

    def flag(self, kind: str, qid: Optional[str], detail: str) -> None:
        if len(self.flags) < MAX_FLAGS:
            self.flags.append({"kind": kind, "qid": qid, "detail": detail[:200], "turn": self.turns})

    def to_dict(self) -> dict:
        return copy.deepcopy({"id": self.id, "language": self.language, "state": self.state,
                              "current": self.current, "answers": self.answers, "pending": self.pending,
                              "flags": self.flags, "retries": self.retries, "turns": self.turns,
                              "port_calls": self.port_calls})

    @classmethod
    def from_dict(cls, d: Any, catalog: Catalog) -> "Session":
        try:
            if not isinstance(d, dict) or not isinstance(d.get("id"), str) or not d["id"] or len(d["id"]) > 128:
                raise SessionInvalid("bad id")
            if d.get("language") not in ("ar", "en") or d.get("state") not in STATES:
                raise SessionInvalid("bad language or state")
            cur = d.get("current")
            if cur is not None and catalog.get(cur) is None:
                raise SessionInvalid("unknown current question")
            answers = {}
            for qid, a in (d.get("answers") or {}).items():
                q = catalog.get(qid)
                if q is None or not isinstance(a, dict) or a.get("status") not in STATUSES \
                        or a.get("source") not in SOURCES:
                    raise SessionInvalid(f"bad answer record {qid!r}")
                answers[qid] = {"values": validate_values(q, a.get("values")), "source": a["source"],
                                "status": a["status"], **({"doc": str(a["doc"])[:80]} if a.get("doc") else {})}
            pending = {}
            for qid, v in (d.get("pending") or {}).items():
                q = catalog.get(qid)
                if q is None:
                    raise SessionInvalid("unknown pending question")
                pending[qid] = validate_values(q, v)
            flags = d.get("flags") or []
            if (not isinstance(flags, list) or len(flags) > MAX_FLAGS
                    or any(not isinstance(f, dict) or f.get("kind") not in FLAG_KINDS for f in flags)):
                raise SessionInvalid("bad flags")
            flags = [{"kind": f["kind"], "qid": f.get("qid"), "detail": str(f.get("detail", ""))[:200],
                      "turn": int(f.get("turn", 0))} for f in flags]
            retries = {str(k): int(v) for k, v in (d.get("retries") or {}).items() if catalog.get(str(k))}
            turns, calls = int(d.get("turns", 0)), int(d.get("port_calls", 0))
            if turns < 0 or calls < 0:
                raise SessionInvalid("negative counters")
        except (ValueRejected, TypeError, ValueError, AttributeError) as e:
            raise SessionInvalid(str(e)) from e
        return cls(d["id"], d["language"], d["state"], cur, answers, pending, flags, retries, turns, calls)


class InMemoryStore:
    """Reference store. A real store persists `to_dict()` JSON per tenant; load goes through `from_dict`."""

    def __init__(self) -> None:
        self._rows: dict = {}

    def save(self, s: Session) -> None:
        self._rows[s.id] = s.to_dict()

    def load(self, sid: str, catalog: Catalog) -> Optional[Session]:
        row = self._rows.get(sid)
        return None if row is None else Session.from_dict(row, catalog)
