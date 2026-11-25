"""Sealed store for BPL-019 sign-off records (answers Q-274).

A SignOffRecord read back from a plain store is only shape-checked, so anyone who could write the store could forge
an acceptance. This ledger stores each record in a SealedLog stream per simulation (whole-record HMAC with key id,
chained, per-tenant anchors, so an edit, a deleted record or a cut tail is BS-011) and enforces the unique key
(simulation id, report digest, role) on append (BS-014), so a race or a replay cannot store two decisions and nothing
can hide an earlier rejection. The writer is the gateway handler that just ran `signoff.record_decision` (host
trust); nothing here decides for anyone. Reads re-validate every record again and fail closed."""
from __future__ import annotations

from simulator import review

from .canon import ident, tenant as _tenant
from .errors import BuildStateError
from .sealed import SealedLog

_FIELDS = ("tenant_id", "simulation_id", "report_digest", "role", "user_id", "decision", "decided_at", "note", "acknowledged")


def _row(r) -> dict:
    return {**{f: getattr(r, f) for f in _FIELDS if f != "acknowledged"}, "acknowledged": list(r.acknowledged)}


def _rec(d) -> review.SignOffRecord:
    if type(d) is not dict or set(d) != set(_FIELDS) or type(d["acknowledged"]) is not list:
        raise BuildStateError("BS-011", "signoff_shape")
    return review.SignOffRecord(**{**d, "acknowledged": tuple(d["acknowledged"])})


class SignOffLedger:
    def __init__(self, integrity_keys: dict, key_id: str):
        self._log = SealedLog(integrity_keys, key_id, "seshna.signoff.ledger.v1")

    def append(self, record) -> None:
        if not isinstance(record, review.SignOffRecord) or not review._valid_record(record):
            raise BuildStateError("BS-001", "record")
        t, sim = _tenant(record.tenant_id), ident(record.simulation_id, "simulation")

        def check(existing):
            for e in existing:
                old = _rec(e["body"]["record"])
                if (old.report_digest, old.role) == (record.report_digest, record.role) \
                        or (old.report_digest, old.user_id) == (record.report_digest, record.user_id):
                    raise BuildStateError("BS-014")  # the unique key (simulation, digest, role)
        self._log.append(t, sim, {"type": "signoff", "record": _row(record)}, check)

    def records(self, tenant_id, simulation_id) -> tuple:
        """Every verified record of one simulation of one tenant. Anything off is BS-011 (no evidence)."""
        t, sim = _tenant(tenant_id), ident(simulation_id, "simulation")
        out = []
        for e in self._log.read(t, sim):
            if type(e["body"]) is not dict or set(e["body"]) != {"type", "record"} or e["body"]["type"] != "signoff":
                raise BuildStateError("BS-011", "signoff_shape")
            out.append(_rec(e["body"]["record"]))
        try:
            out = review.check_records(out)
        except review.ReviewError:
            raise BuildStateError("BS-011", "signoff_record") from None
        if any(r.tenant_id != t or r.simulation_id != sim for r in out):
            raise BuildStateError("BS-011", "signoff_tenant")
        return out
