"""Per-tenant, per-user memory (OPR-014). Tier 3: tenancy and agent authority.

Rules this module enforces (design: docs/architecture/tenant-memory.md):
- A memory is DATA. It is handed to a model only as an L3 `DataItem`, never in the instruction position, and it has
  no way to grant authority: this module imports nothing from the allow-list and no entry field names a tool or role.
- Agent-facing: `remember` and `recall`. Owner-facing (host exposes them only on a verified human session, never as
  an agent tool): `list_entries`, `confirm`, `delete`, `erase_user`, `erase_tenant`.
- Tainted writes (content read from documents or tool output) are stored `unverified`, are never recalled, and are
  promoted only by `confirm` with the exact text hash. Instruction-like text is stored `unverified` too.
- Every error path fails closed: a refusal code and nothing stored. Audit carries ids, hash and length only; if the
  audit sink fails, the operation is refused (and a write is rolled back)."""
from __future__ import annotations

import dataclasses
import math
import re
import threading

from runtime.untrusted import args_hash, sanitise_text, sha, wrap_data
from runtime.untrusted import _san as _sanitise

from .errors import MemoryRefused
from .models import AUTHORS, KINDS, UNVERIFIED, VERIFIED, MemoryEntry, Scope, check_id
from .redact import redact

DAY = 86400.0
MAX_EPOCH = 4102444800.0  # year 2100: a larger clock reading is a fault, not a time
_RULE = re.compile(
    r"(?i)\b(?:always|never|whenever|must|auto[- ]?approve|approve|approving|without\s+(?:asking|confirm\w*|approval)|"
    r"do\s+not\s+ask|don'?t\s+ask|transfer|pay|payments?|send\s+(?:it\s+|them\s+)?to|forward\s+to|wire|grant|allow)\b"
    r"|دائما|ابدا|وافق|موافقه|اعتمد|حول|ادفع|دفع|ارسل\s+الى|بدون\s+(?:سوال|تاكيد|موافقه)|تلقائي|اسمح")


@dataclasses.dataclass(frozen=True)
class MemoryConfig:
    max_chars: int = 500
    max_entries_per_user: int = 200          # verified entries
    max_unverified_per_user: int = 20        # oldest unverified evicted first; never evicts verified
    unverified_ttl_s: float = 7 * DAY
    max_entries_per_tenant: int = 5000
    default_ttl_s: float = 90 * DAY
    max_ttl_s: float = 365 * DAY
    recall_limit: int = 5
    recall_max_limit: int = 10
    recall_max_chars: int = 2000


@dataclasses.dataclass(frozen=True)
class Erasure:
    count: int
    audit_failed: bool = False  # the erasure happened; only its audit record is missing (retry the audit)


class MemoryService:
    def __init__(self, store, clock, ids, sink=None, config: MemoryConfig | None = None, salt=None):
        """clock() returns epoch seconds; ids.new_id(prefix) returns a fresh id; sink.emit(tenant_id, subject, type,
        data, trace) is the audit port (data is hash and length only)."""
        self._store, self._clock, self._ids, self._sink = store, clock, ids, sink
        self._cfg, self._salt = config or MemoryConfig(), salt  # salt: bytes, or a callable tenant_id -> bytes|None
        self._lock = threading.RLock()

    # ---- helpers -------------------------------------------------------------------------------------------
    def _now(self) -> float:
        try:
            t = self._clock()
        except Exception:
            raise MemoryRefused("clock_invalid") from None
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0 \
                or t > MAX_EPOCH:
            raise MemoryRefused("clock_invalid")  # no stored high-water mark: a bad reading cannot poison later calls
        return float(t)

    def _audit(self, scope, type_, **data):
        if self._sink is None:
            raise MemoryRefused("audit_failed")  # no audit port, no memory: fail closed
        try:
            self._sink.emit(scope.tenant_id, scope.user_id, type_, data, None)
        except Exception:
            raise MemoryRefused("audit_failed") from None

    def _guard(self, scope):
        if not isinstance(scope, Scope):
            raise MemoryRefused("invalid_scope")
        return scope

    def _store_call(self, fn, *a):
        try:
            return fn(*a)
        except MemoryRefused:
            raise
        except Exception:
            raise MemoryRefused("store_failed") from None

    def _live(self, scope, now):
        self._store_call(self._store.delete_expired, scope.tenant_id, now)  # retention is real deletion
        return [e for e in self._store_call(self._store.list, scope) if e.expires_at > now]

    def _h(self, scope, text):
        salt = self._salt(scope.tenant_id) if callable(self._salt) else self._salt
        return args_hash(text, salt)

    def sweep(self, tenant_id: str) -> int:
        """Host sweeper: hard-delete a tenant's expired memories. Needs a sane clock, like a write."""
        with self._lock:
            return self._store_call(self._store.delete_expired, check_id(tenant_id), self._now())

    def _after_delete(self, scope, type_, **data) -> Erasure:
        """The data is already gone: an audit fault is reported beside the success, never as a failure."""
        try:
            self._audit(scope, type_, **data)
            return Erasure(data.get("count", 1), False)
        except MemoryRefused:
            return Erasure(data.get("count", 1), True)

    # ---- host-facing write (the host fills provenance from the verified run; see AgentMemoryTool) -------------
    def remember(self, scope, *, kind, text, source_turn, author, tainted, source_content_ids=(), ttl_s=None):
        """Store one short memory. `tainted`, `author` and `source_content_ids` come from the host's run state, never
        from model arguments (use `AgentMemoryTool` for the model-facing call). Returns the entry."""
        with self._lock:
            self._guard(scope)
            now = self._now()
            if kind not in KINDS:
                raise MemoryRefused("kind_not_allowed")
            if author not in AUTHORS or not isinstance(tainted, bool) or not isinstance(text, str):
                raise MemoryRefused("invalid_input")
            check_id(source_turn)
            if not isinstance(source_content_ids, (tuple, list)) or len(source_content_ids) > 20:
                raise MemoryRefused("invalid_input")
            cids = tuple(check_id(c) for c in source_content_ids)
            if len(text) > self._cfg.max_chars:
                raise MemoryRefused("too_large")
            ttl = self._cfg.default_ttl_s if ttl_s is None else ttl_s
            if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or not math.isfinite(ttl) or ttl <= 0 \
                    or ttl > self._cfg.max_ttl_s:
                raise MemoryRefused("invalid_input")
            try:
                clean, flags = sanitise_text(text, self._cfg.max_chars)
            except Exception:
                raise MemoryRefused("invalid_input") from None
            if "truncated" in flags:
                raise MemoryRefused("too_large")
            clean, rflags = redact(clean)
            clean = clean.strip()
            if not clean or not _sanitise.comparison_copy(clean.replace("[redacted]", "")).strip():
                raise MemoryRefused("empty_after_redaction")
            flags = tuple(sorted(set(flags) | set(rflags)))
            if _RULE.search(_sanitise.comparison_copy(clean)):
                flags = tuple(sorted(set(flags) | {"rule_like"}))
            quarantined = tainted or bool(cids and author == "assistant") or "instruction_like" in flags \
                or "rule_like" in flags
            status = UNVERIFIED if quarantined else VERIFIED
            digest = sha(clean)
            live = self._live(scope, now)
            for e in live:
                if e.content_hash == digest and e.kind == kind:
                    if e.status == VERIFIED or status == UNVERIFIED:
                        return e  # duplicate: no second row, no extension of its life
                    self._store_call(self._store.delete, scope, e.entry_id)  # the user's own words replace a pending copy
                    live = [x for x in live if x.entry_id != e.entry_id]
            if status == UNVERIFIED:
                pending = sorted((x for x in live if x.status == UNVERIFIED), key=lambda x: x.created_at)
                for old in pending[:max(0, len(pending) - self._cfg.max_unverified_per_user + 1)]:
                    self._store_call(self._store.delete, scope, old.entry_id)  # oldest unverified out; never verified
                ttl = min(ttl, self._cfg.unverified_ttl_s)
            elif sum(x.status == VERIFIED for x in live) >= self._cfg.max_entries_per_user:
                raise MemoryRefused("quota_exceeded")
            if self._store_call(self._store.count_tenant, scope.tenant_id, now) >= self._cfg.max_entries_per_tenant:
                raise MemoryRefused("quota_exceeded")
            entry = MemoryEntry(
                entry_id=self._ids.new_id("mem"), tenant_id=scope.tenant_id, user_id=scope.user_id, kind=kind,
                text=clean, content_hash=digest, status=status, flags=flags,
                author=author, source_turn=source_turn, source_content_ids=cids, created_at=now,
                expires_at=now + float(ttl))
            self._store_call(self._store.put, entry)
            try:
                self._audit(scope, "memory.write_quarantined" if quarantined else "memory.written",
                            entry_id=entry.entry_id, kind=kind, length=len(clean), hash=self._h(scope, clean),
                            author=author, source_turn=source_turn, expires_at=entry.expires_at)
            except MemoryRefused:
                self._store_call(self._store.delete, scope, entry.entry_id)  # roll back: no unaudited memory
                raise
            return entry

    def recall(self, scope, query: str = "", limit: int | None = None) -> list:
        """Verified, unexpired memories of this user as L3 DataItems. Unverified ones are never returned here."""
        with self._lock:
            self._guard(scope)
            now = self._now()
            if not isinstance(query, str) or len(query) > 500:
                raise MemoryRefused("invalid_input")
            lim = self._cfg.recall_limit if limit is None else limit
            if isinstance(lim, bool) or not isinstance(lim, int) or lim < 1:
                raise MemoryRefused("invalid_input")
            lim = min(lim, self._cfg.recall_max_limit)
            rows = [e for e in self._live(scope, now) if e.status == VERIFIED]
            q = set(_sanitise.comparison_copy(query).lower().split())
            if q:
                scored = [(len(q & set(_sanitise.comparison_copy(e.text).lower().split())), e) for e in rows]
                rows = [e for s, e in sorted(scored, key=lambda p: (-p[0], -p[1].created_at)) if s > 0]
            else:
                rows = sorted(rows, key=lambda e: -e.created_at)
            out, used = [], 0
            for e in rows[:lim]:
                if used + len(e.text) > self._cfg.recall_max_chars:
                    break
                used += len(e.text)
                item = wrap_data(f"mem_{e.entry_id}", f"memory:{e.kind}", e.text, self._cfg.max_chars)
                out.append(dataclasses.replace(item, flags=tuple(sorted(set(item.flags) | set(e.flags)
                                                                       | {"memory_read"}))))
            self._audit(scope, "memory.read", count=len(out), length=used,
                        hash=self._h(scope, query) if query else None, entry_ids=[e.content_id for e in out])
            return out

    # ---- owner-facing (verified human session only; never an agent tool) ---------------------------------------
    def list_entries(self, scope) -> list:
        """All unexpired entries of this user, verified and unverified, for the owner's review screen. The screen
        should show each entry's flags (instruction_like, rule_like, id_redacted) before the owner confirms."""
        with self._lock:
            self._guard(scope)
            now = self._now()
            rows = sorted(self._live(scope, now), key=lambda e: e.created_at)
            self._audit(scope, "memory.listed", count=len(rows))
            return rows

    def confirm(self, scope, entry_id: str, expected_hash: str, actor_user_id: str):
        """The owner confirms the exact stored text (by hash) of an unverified entry. `actor_user_id` is the verified
        session user and must be the entry's owner: nobody confirms another user's memory."""
        with self._lock:
            self._guard(scope)
            if check_id(actor_user_id) != scope.user_id:
                raise MemoryRefused("not_owner")
            now = self._now()
            e = self._store_call(self._store.get, scope, entry_id) if isinstance(entry_id, str) else None
            if e is None or e.expires_at <= now:
                raise MemoryRefused("not_found")
            if e.status != UNVERIFIED:
                raise MemoryRefused("not_unverified")
            if e.content_hash != expected_hash:
                raise MemoryRefused("invalid_input")
            if sum(x.status == VERIFIED for x in self._live(scope, now)) >= self._cfg.max_entries_per_user:
                raise MemoryRefused("quota_exceeded")
            new = dataclasses.replace(e, status=VERIFIED, confirmed_by=actor_user_id, confirmed_at=now,
                                      expires_at=now + self._cfg.default_ttl_s)
            self._store_call(self._store.replace, new)
            try:
                self._audit(scope, "memory.confirmed", entry_id=e.entry_id, length=len(e.text),
                            hash=self._h(scope, e.text))
            except MemoryRefused:
                self._store_call(self._store.replace, e)
                raise
            return new

    # Erasure never depends on the clock: a bad clock must not block the right to erasure.
    def delete(self, scope, entry_id: str) -> Erasure:
        with self._lock:
            self._guard(scope)
            if not isinstance(entry_id, str) or not self._store_call(self._store.delete, scope, entry_id):
                raise MemoryRefused("not_found")
            return self._after_delete(scope, "memory.deleted", entry_id=entry_id, count=1)

    def erase_user(self, scope) -> Erasure:
        """Right to erasure: remove every memory of this user (expired ones included)."""
        with self._lock:
            self._guard(scope)
            n = self._store_call(self._store.delete_scope, scope)
            return self._after_delete(scope, "memory.erased", count=n)

    def erase_tenant(self, tenant_id: str, requested_by: str) -> Erasure:
        """Tenant offboarding. `requested_by` must be a verified tenant admin or platform operator (host check)."""
        with self._lock:
            scope = Scope(tenant_id, requested_by)
            n = self._store_call(self._store.delete_tenant, tenant_id)
            return self._after_delete(scope, "memory.tenant_erased", count=n)


class AgentMemoryTool:
    """The only memory write a model may call: `remember(kind, text)`. Author, taint and source ids are fixed by the
    host from the verified run (`run`: scope, source_turn, tainted(), content_ids()), never by model arguments."""

    def __init__(self, service: MemoryService, scope: Scope, source_turn: str, tainted, content_ids):
        self._svc, self._scope, self._turn = service, scope, source_turn
        self._tainted, self._cids = tainted, content_ids

    def remember(self, kind, text):
        try:
            tainted = bool(self._tainted())
            cids = tuple(self._cids())
        except Exception:
            tainted, cids = True, ()  # unknown taint state: treat as tainted
        return self._svc.remember(self._scope, kind=kind, text=text, source_turn=self._turn, author="assistant",
                                  tainted=tainted or bool(cids), source_content_ids=cids)

    def recall(self, query: str = "", limit: int | None = None):
        return self._svc.recall(self._scope, query, limit)
