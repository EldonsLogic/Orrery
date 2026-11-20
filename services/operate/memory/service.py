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
import threading

from runtime.untrusted import args_hash, sanitise_text, sha, wrap_data
from runtime.untrusted import _san as _sanitise

from .errors import MemoryRefused
from .models import AUTHORS, KINDS, UNVERIFIED, VERIFIED, MemoryEntry, Scope, check_id
from .redact import redact

DAY = 86400.0


@dataclasses.dataclass(frozen=True)
class MemoryConfig:
    max_chars: int = 500
    max_entries_per_user: int = 200
    max_entries_per_tenant: int = 5000
    default_ttl_s: float = 90 * DAY
    max_ttl_s: float = 365 * DAY
    recall_limit: int = 5
    recall_max_limit: int = 10
    recall_max_chars: int = 2000


class MemoryService:
    def __init__(self, store, clock, ids, sink=None, config: MemoryConfig | None = None, salt: bytes | None = None):
        """clock() returns epoch seconds; ids.new_id(prefix) returns a fresh id; sink.emit(tenant_id, subject, type,
        data, trace) is the audit port (data is hash and length only)."""
        self._store, self._clock, self._ids, self._sink = store, clock, ids, sink
        self._cfg, self._salt = config or MemoryConfig(), salt
        self._lock = threading.RLock()
        self._high = 0.0

    # ---- helpers -------------------------------------------------------------------------------------------
    def _now(self) -> float:
        try:
            t = self._clock()
        except Exception:
            raise MemoryRefused("clock_invalid") from None
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0 or t < self._high:
            raise MemoryRefused("clock_invalid")
        self._high = float(t)
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
        return [e for e in self._store_call(self._store.list, scope) if e.expires_at > now]

    def _h(self, text):
        return args_hash(text, self._salt)

    # ---- agent-facing --------------------------------------------------------------------------------------
    def remember(self, scope, *, kind, text, source_turn, author, tainted, source_content_ids=(), ttl_s=None):
        """Store one short memory. `tainted` has no default: the caller must say whether the text came from
        documents or tool output. Returns the entry (status may be `unverified`)."""
        with self._lock:
            self._guard(scope)
            now = self._now()
            if kind not in KINDS:
                raise MemoryRefused("kind_not_allowed")
            if author not in AUTHORS or not isinstance(tainted, bool) or not isinstance(text, str):
                raise MemoryRefused("invalid_input")
            check_turn = check_id(source_turn) if isinstance(source_turn, str) else None
            if check_turn is None:
                raise MemoryRefused("invalid_input")
            if not isinstance(source_content_ids, (tuple, list)) or len(source_content_ids) > 20:
                raise MemoryRefused("invalid_input")
            cids = tuple(check_id(c) for c in source_content_ids)
            if len(text) > self._cfg.max_chars:
                raise MemoryRefused("too_large")
            ttl = self._cfg.default_ttl_s if ttl_s is None else ttl_s
            if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or not math.isfinite(ttl) or ttl <= 0 \
                    or ttl > self._cfg.max_ttl_s:
                raise MemoryRefused("invalid_input")
            clean, flags = sanitise_text(text, self._cfg.max_chars)
            if "truncated" in flags:
                raise MemoryRefused("too_large")
            clean, rflags = redact(clean)
            clean = clean.strip()
            if not clean or not _sanitise.comparison_copy(clean.replace("[redacted]", "")).strip():
                raise MemoryRefused("empty_after_redaction")
            flags = tuple(sorted(set(flags) | set(rflags)))
            quarantined = tainted or bool(cids and author == "assistant") or "instruction_like" in flags
            digest = sha(clean)
            for e in self._live(scope, now):
                if e.content_hash == digest and e.kind == kind:
                    return e  # duplicate: no second row, no extension of its life
            if len(self._live(scope, now)) >= self._cfg.max_entries_per_user or \
                    self._store_call(self._store.count_tenant, scope.tenant_id) >= self._cfg.max_entries_per_tenant:
                raise MemoryRefused("quota_exceeded")
            entry = MemoryEntry(
                entry_id=self._ids.new_id("mem"), tenant_id=scope.tenant_id, user_id=scope.user_id, kind=kind,
                text=clean, content_hash=digest, status=UNVERIFIED if quarantined else VERIFIED, flags=flags,
                author=author, source_turn=source_turn, source_content_ids=cids, created_at=now,
                expires_at=now + float(ttl))
            self._store_call(self._store.put, entry)
            try:
                self._audit(scope, "memory.write_quarantined" if quarantined else "memory.written",
                            entry_id=entry.entry_id, kind=kind, length=len(clean), hash=self._h(clean),
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
                        hash=self._h(query) if query else None, entry_ids=[e.content_id for e in out])
            return out

    # ---- owner-facing --------------------------------------------------------------------------------------
    def list_entries(self, scope) -> list:
        """All unexpired entries of this user, verified and unverified, for the owner's review screen."""
        with self._lock:
            self._guard(scope)
            now = self._now()
            rows = sorted(self._live(scope, now), key=lambda e: e.created_at)
            self._audit(scope, "memory.listed", count=len(rows))
            return rows

    def confirm(self, scope, entry_id: str, expected_hash: str, confirmed_by: str):
        """A human confirms the exact stored text (by hash) of an unverified entry; only then it becomes verified."""
        with self._lock:
            self._guard(scope)
            now = self._now()
            e = self._store_call(self._store.get, scope, entry_id) if isinstance(entry_id, str) else None
            if e is None or e.expires_at <= now:
                raise MemoryRefused("not_found")
            if e.status != UNVERIFIED:
                raise MemoryRefused("not_unverified")
            if e.content_hash != expected_hash:
                raise MemoryRefused("invalid_input")
            new = dataclasses.replace(e, status=VERIFIED, confirmed_by=check_id(confirmed_by), confirmed_at=now)
            self._store_call(self._store.replace, new)
            try:
                self._audit(scope, "memory.confirmed", entry_id=e.entry_id, length=len(e.text),
                            hash=self._h(e.text))
            except MemoryRefused:
                self._store_call(self._store.replace, e)
                raise
            return new

    def delete(self, scope, entry_id: str) -> None:
        with self._lock:
            self._guard(scope)
            self._now()
            if not isinstance(entry_id, str) or not self._store_call(self._store.delete, scope, entry_id):
                raise MemoryRefused("not_found")
            self._audit(scope, "memory.deleted", entry_id=entry_id)

    def erase_user(self, scope) -> int:
        """Right to erasure: remove every memory of this user (expired ones included). Returns the count."""
        with self._lock:
            self._guard(scope)
            self._now()
            n = self._store_call(self._store.delete_scope, scope)
            self._audit(scope, "memory.erased", count=n)
            return n

    def erase_tenant(self, tenant_id: str, requested_by: str) -> int:
        """Tenant offboarding (data-retention step 5): remove all memory of a tenant."""
        with self._lock:
            scope = Scope(tenant_id, requested_by)
            self._now()
            n = self._store_call(self._store.delete_tenant, tenant_id)
            self._audit(scope, "memory.tenant_erased", count=n)
            return n
