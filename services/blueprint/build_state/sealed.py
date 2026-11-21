"""Append-only sealed log with per-tenant anchors (the PLT-013 pattern, reusable).

Every record carries a whole-record HMAC (key derived per purpose; the key id is inside the seal) chained to the
previous seal and bound to its tenant and stream, so editing, dropping, reordering or moving a record to another
stream or tenant fails closed (BS-011). A cut tail or a deleted stream is caught by two sealed anchors kept outside
the logs and written in the same step as every append: a per-stream head (seq and head seal) and a per-tenant
manifest (every stream with seq and head, plus a counter). Every read checks both. No key, no log (BS-012): there is
no unsealed or sha256 fallback. Rolling back logs, heads and manifest together needs an external anchor (Q-502).
A real store must write record, head and manifest in ONE atomic transaction with a unique key on (tenant, stream,
seq); this in-memory store assigns all three together."""
from __future__ import annotations

import copy
import hashlib
import hmac
import json

from .canon import plain
from .errors import BuildStateError

_KEYS = {"schema", "tenant_id", "stream", "seq", "prev", "body", "key_id", "seal"}


class SealedLog:
    def __init__(self, integrity_keys: dict, key_id: str, domain: str):
        if type(integrity_keys) is not dict or not integrity_keys or type(domain) is not str or not domain:
            raise BuildStateError("BS-012")
        if any(type(k) is not str or type(v) is not bytes or len(v) < 32 for k, v in integrity_keys.items()):
            raise BuildStateError("BS-012")
        if key_id not in integrity_keys:
            raise BuildStateError("BS-012")
        self._keys, self._active, self._domain = dict(integrity_keys), key_id, domain.encode()
        self._logs: dict = {}      # (tenant, stream) -> [record]
        self._heads: dict = {}     # (tenant, stream) -> sealed head
        self._manifests: dict = {}  # tenant -> sealed manifest

    # ----- sealing -------------------------------------------------------------------------------------------
    def _mac(self, rec: dict, purpose: bytes) -> str:
        master = self._keys.get(rec.get("key_id")) if type(rec.get("key_id")) is str else None
        if master is None:
            raise BuildStateError("BS-011", "key")
        key = hmac.new(master, self._domain + b"|" + purpose, hashlib.sha256).digest()
        body = json.dumps({k: v for k, v in rec.items() if k != "seal"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()

    def _seal(self, rec: dict, purpose: bytes) -> dict:
        rec = {**rec, "key_id": self._active}
        rec["seal"] = self._mac(rec, purpose)
        return rec

    def _manifest(self, tenant: str) -> dict:
        m = self._manifests.get(tenant)
        if m is None:
            if any(t == tenant for t, _ in self._logs) or any(t == tenant for t, _ in self._heads):
                raise BuildStateError("BS-011", "manifest")  # a tenant's logs with no manifest
            return {}
        try:
            if type(m) is not dict or set(m) != {"schema", "tenant_id", "n", "streams", "key_id", "seal"} or m["schema"] != "1" \
                    or m["tenant_id"] != tenant or type(m["n"]) is not int or type(m["seal"]) is not str \
                    or not hmac.compare_digest(m["seal"], self._mac(m, b"manifest")):
                raise BuildStateError("BS-011", "manifest")
            out = {}
            for sid, seq, hd in m["streams"]:
                if sid in out or type(seq) is not int:
                    raise BuildStateError("BS-011", "manifest")
                out[sid] = (seq, hd)
            return out
        except BuildStateError:
            raise
        except Exception:
            raise BuildStateError("BS-011", "manifest") from None

    # ----- reading: every read re-validates the log and both anchors ---------------------------------------
    def streams(self, tenant: str) -> list:
        mf = self._manifest(tenant)
        for t, s in list(self._logs) + list(self._heads):
            if t == tenant and s not in mf:
                raise BuildStateError("BS-011", "unanchored")
        return sorted(mf)

    def read(self, tenant: str, stream: str) -> tuple:
        """The verified records of one stream (deep copies), () when the stream does not exist."""
        mf = self._manifest(tenant)
        key = (tenant, stream)
        entry = mf.get(stream)
        log = self._logs.get(key)
        if entry is None:
            if log or key in self._heads:
                raise BuildStateError("BS-011", "unanchored")
            return ()
        if not log:
            raise BuildStateError("BS-011", "deleted")
        head = self._heads.get(key)
        try:
            if type(head) is not dict or set(head) != {"tenant_id", "stream", "seq", "head", "key_id", "seal"} \
                    or not hmac.compare_digest(str(head["seal"]), self._mac(head, b"head")) \
                    or (head["tenant_id"], head["stream"]) != key or head["seq"] != len(log) \
                    or head["head"] != log[-1].get("seal") or entry != (len(log), log[-1].get("seal")):
                raise BuildStateError("BS-011", "head")
            prev = ""
            for i, rec in enumerate(log, 1):
                if type(rec) is not dict or set(rec) != _KEYS or rec["schema"] != "1" or rec["tenant_id"] != tenant \
                        or rec["stream"] != stream or rec["seq"] != i or rec["prev"] != prev or type(rec["body"]) is not dict \
                        or type(rec["seal"]) is not str or not hmac.compare_digest(rec["seal"], self._mac(rec, b"record")):
                    raise BuildStateError("BS-011", "record")
                prev = rec["seal"]
        except BuildStateError:
            raise
        except Exception:
            raise BuildStateError("BS-011", "shape") from None
        return tuple(copy.deepcopy(log))

    def head(self, tenant: str, stream: str):
        """(seq, head seal) of a verified stream, or None."""
        recs = self.read(tenant, stream)
        return (len(recs), recs[-1]["seal"]) if recs else None

    # ----- writing ---------------------------------------------------------------------------------------------
    def append(self, tenant: str, stream: str, body: dict, check=None) -> dict:
        """Verify, run `check(existing_records)` (it raises to refuse), then seal and store record, head and
        manifest together. `body` is plain data."""
        existing = self.read(tenant, stream)
        if check is not None:
            check(existing)
        body = plain(body)
        mf = self._manifest(tenant)
        rec = {"schema": "1", "tenant_id": tenant, "stream": stream, "seq": len(existing) + 1,
               "prev": existing[-1]["seal"] if existing else "", "body": body, "key_id": self._active}
        rec["seal"] = self._mac(rec, b"record")
        mf[stream] = (rec["seq"], rec["seal"])
        head = self._seal({"tenant_id": tenant, "stream": stream, "seq": rec["seq"], "head": rec["seal"]}, b"head")
        old = self._manifests.get(tenant)
        manifest = self._seal({"schema": "1", "tenant_id": tenant, "n": (old["n"] if old else 0) + 1,
                               "streams": [[k, *mf[k]] for k in sorted(mf)]}, b"manifest")
        self._logs[(tenant, stream)] = list(self._logs.get((tenant, stream), [])) + [rec]
        self._heads[(tenant, stream)] = head
        self._manifests[tenant] = manifest
        return copy.deepcopy(rec)
