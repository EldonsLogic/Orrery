"""Append-only sealed log of owner decisions (the PLT-013 / BPL-020 pattern, kept local so this package imports no
machine internals).

Every record carries a whole-record HMAC (key derived per purpose; the key id is inside the seal) chained to the
previous seal and bound to its tenant and stream, so editing, dropping, reordering or moving a record to another
stream or tenant fails closed. A cut tail or a deleted stream is caught by a sealed per-tenant manifest (every stream
with its seq and head, plus a counter) written in the same step as every append and checked on every read. No key,
no log: there is no unsealed fallback. Rolling back records and manifest together needs an external anchor (Q-521).

Storage is a port (`store`); `MemoryStore` is for tests and local runs only and loses everything on restart.
store.records(tenant, stream) -> list   the stored records of one stream, in seq order ([] when none).
store.manifest(tenant) -> dict | None   the stored sealed manifest of a tenant.
store.has_records(tenant) -> bool       True when any stream of the tenant has records (so a lost manifest is caught).
store.commit(tenant, stream, record, manifest)
                                        write record and manifest in ONE atomic transaction with a unique key on
                                        (tenant, stream, seq) AND a compare-and-swap on the tenant manifest counter
                                        (the stored `n` must be the new `n` - 1): the manifest is shared by every
                                        Blueprint stream of the tenant, so two streams must not both commit on the
                                        same old manifest; raise on any conflict or failure.
A store error on read is OA-009 (fail closed); on commit it is OA-004 and nothing counts as written. After every commit
the stream is read back and its head must be the new record, or it is OA-004 too."""
from __future__ import annotations

import copy
import hashlib
import hmac
import json

from .errors import OwnerApprovalError

_KEYS = {"schema", "tenant_id", "stream", "seq", "prev", "body", "key_id", "seal"}
MAX_DEPTH = 6


def _plain(v, depth=0):
    if depth > MAX_DEPTH:
        raise OwnerApprovalError("OA-001", "depth")
    t = type(v)
    if v is None or t is bool or t is int:
        if t is int and abs(v) > 10 ** 18:
            raise OwnerApprovalError("OA-001", "int")
        return v
    if t is str:
        try:
            v.encode("utf-8")
        except UnicodeEncodeError:
            raise OwnerApprovalError("OA-001", "text") from None
        return v
    if t in (list, tuple):
        return [_plain(x, depth + 1) for x in v]
    if t is dict:
        if any(type(k) is not str for k in v):
            raise OwnerApprovalError("OA-001", "key")
        return {k: _plain(x, depth + 1) for k, x in v.items()}
    raise OwnerApprovalError("OA-001", "type")  # floats, sets, iterators, objects


class MemoryStore:
    """In-process store (tests, local runs). Not durable: a restart forgets every decision, rejections included."""
    def __init__(self):
        self._logs: dict = {}
        self._manifests: dict = {}

    def records(self, tenant, stream):
        return self._logs.get((tenant, stream), [])

    def manifest(self, tenant):
        return self._manifests.get(tenant)

    def has_records(self, tenant):
        return any(t == tenant for t, _ in self._logs)

    def commit(self, tenant, stream, record, manifest):
        log = self._logs.get((tenant, stream), [])
        if record["seq"] != len(log) + 1:
            raise ValueError("seq")
        old = self._manifests.get(tenant)
        if manifest["n"] != (old["n"] if old else 0) + 1:
            raise ValueError("manifest")   # another stream of this tenant committed first
        self._logs[(tenant, stream)] = list(log) + [record]
        self._manifests[tenant] = manifest


class SealedLog:
    def __init__(self, integrity_keys, key_id, domain="seshna.ownerapproval.log.v1", store=None):
        if type(integrity_keys) is not dict or not integrity_keys or type(key_id) is not str:
            raise OwnerApprovalError("OA-010")
        if any(type(k) is not str or type(v) is not bytes or len(v) < 32 for k, v in integrity_keys.items()):
            raise OwnerApprovalError("OA-010")
        if key_id not in integrity_keys:
            raise OwnerApprovalError("OA-010")
        self._keys, self._active, self._domain = dict(integrity_keys), key_id, domain.encode()
        self._store = store if store is not None else MemoryStore()

    @property
    def _logs(self):        # direct access to a MemoryStore (tests)
        return self._store._logs

    @property
    def _manifests(self):
        return self._store._manifests

    def _get(self, fn, *a):
        try:
            return copy.deepcopy(fn(*a))
        except Exception:
            raise OwnerApprovalError("OA-009", "store") from None

    def _mac(self, rec: dict, purpose: bytes) -> str:
        master = self._keys.get(rec.get("key_id")) if type(rec.get("key_id")) is str else None
        if master is None:
            raise OwnerApprovalError("OA-009", "key")
        key = hmac.new(master, self._domain + b"|" + purpose, hashlib.sha256).digest()
        body = json.dumps({k: v for k, v in rec.items() if k != "seal"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()

    def _seal(self, rec: dict, purpose: bytes) -> dict:
        rec = {**rec, "key_id": self._active}
        rec["seal"] = self._mac(rec, purpose)
        return rec

    def _manifest(self, tenant: str) -> dict:
        return self._manifest_n(tenant)[1]

    def _manifest_n(self, tenant: str) -> tuple:
        """(n, streams) from ONE verified manifest read: the counter the store's CAS checks and the streams written
        under it must come from the same read, or a stream committed in between is dropped (partner review F1)."""
        m = self._get(self._store.manifest, tenant)
        if m is None:
            if self._get(self._store.has_records, tenant) is not False:
                raise OwnerApprovalError("OA-009", "manifest")
            return 0, {}
        try:
            if type(m) is not dict or set(m) != {"schema", "tenant_id", "n", "streams", "key_id", "seal"} or m["schema"] != "1" \
                    or m["tenant_id"] != tenant or type(m["n"]) is not int or type(m["seal"]) is not str \
                    or not hmac.compare_digest(m["seal"], self._mac(m, b"manifest")):
                raise OwnerApprovalError("OA-009", "manifest")
            out = {}
            for sid, seq, hd in m["streams"]:
                if sid in out or type(seq) is not int:
                    raise OwnerApprovalError("OA-009", "manifest")
                out[sid] = (seq, hd)
            return m["n"], out
        except OwnerApprovalError:
            raise
        except Exception:
            raise OwnerApprovalError("OA-009", "manifest") from None

    def read(self, tenant: str, stream: str) -> tuple:
        """The verified records of one stream (deep copies); () when the stream does not exist."""
        mf = self._manifest(tenant)
        key = (tenant, stream)
        entry, log = mf.get(stream), self._get(self._store.records, *key)
        if type(log) is not list:
            raise OwnerApprovalError("OA-009", "store")
        if entry is None:
            if log:
                raise OwnerApprovalError("OA-009", "unanchored")
            return ()
        if not log:
            raise OwnerApprovalError("OA-009", "deleted")
        try:
            if entry != (len(log), log[-1].get("seal")):
                raise OwnerApprovalError("OA-009", "head")
            prev = ""
            for i, rec in enumerate(log, 1):
                if type(rec) is not dict or set(rec) != _KEYS or rec["schema"] != "1" or rec["tenant_id"] != tenant \
                        or rec["stream"] != stream or rec["seq"] != i or rec["prev"] != prev or type(rec["body"]) is not dict \
                        or type(rec["seal"]) is not str or not hmac.compare_digest(rec["seal"], self._mac(rec, b"record")):
                    raise OwnerApprovalError("OA-009", "record")
                prev = rec["seal"]
        except OwnerApprovalError:
            raise
        except Exception:
            raise OwnerApprovalError("OA-009", "shape") from None
        return tuple(log)

    def append(self, tenant: str, stream: str, body: dict, check=None) -> dict:
        """Verify, run `check(existing_records)` (it raises to refuse), then seal and store record and manifest together."""
        existing = self.read(tenant, stream)
        if check is not None:
            check(existing)
        body = _plain(body)
        n, mf = self._manifest_n(tenant)
        if mf.get(stream) != ((len(existing), existing[-1]["seal"]) if existing else None):
            raise OwnerApprovalError("OA-004", "conflict")   # this stream moved since it was read: refuse, write nothing
        rec = {"schema": "1", "tenant_id": tenant, "stream": stream, "seq": len(existing) + 1,
               "prev": existing[-1]["seal"] if existing else "", "body": body, "key_id": self._active}
        rec["seal"] = self._mac(rec, b"record")
        mf[stream] = (rec["seq"], rec["seal"])
        manifest = self._seal({"schema": "1", "tenant_id": tenant, "n": n + 1,
                               "streams": [[k, *mf[k]] for k in sorted(mf)]}, b"manifest")
        try:
            self._store.commit(tenant, stream, copy.deepcopy(rec), manifest)
        except Exception:
            raise OwnerApprovalError("OA-004", "store") from None
        back = self.read(tenant, stream)   # a store that returns without writing must not look like a write
        if not back or back[-1]["seq"] != rec["seq"] or not hmac.compare_digest(back[-1]["seal"], rec["seal"]):
            raise OwnerApprovalError("OA-004", "readback")
        return copy.deepcopy(rec)
