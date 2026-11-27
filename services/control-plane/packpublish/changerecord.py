"""Change record check (CMP-038 slice 4): every change record is validated before it is committed.

Two layers, both fail closed with PP-062. The built-in rules need nothing installed and cover what JSON Schema
cannot say (the schema's x-validator-rules: two different people, two different step-ups, the requester one of
them, the statement digest recomputed from the record, each step-up bound to its signer and that statement and at
most 300 seconds before signing, every signing at or before recording, the accountant's market the record's
country). The schema
(contracts/country-pack-change-record.schema.json) runs as well wherever `jsonschema` and `referencing` are
installed; the control-plane CI step installs only pytest, so there the built-in rules alone run."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .canon import canonical, digest
from .errors import PublishError

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
KEYS = {"v", "typ", "id", "kind", "countryCode", "target", "reasonRef", "baseIndexSeq", "baseIndexDigest",
        "statementDigest", "requestedBy", "recordedAt", "signOffs"}
try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ImportError:  # pragma: no cover
    Draft202012Validator = None


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _statement(rec: dict) -> str:
    """Same statement as workflow._change_statement (kept here to avoid an import cycle)."""
    return digest(canonical({"op": "pack_change", "countryCode": rec["countryCode"], "kind": rec["kind"],
                             "target": rec["target"], "reasonRef": rec["reasonRef"],
                             "baseIndexDigest": rec["baseIndexDigest"]}))


def _signoff_ok(rec: dict, s: dict) -> bool:
    gap = (_t(s["signedAt"]) - _t(s["mfa"]["authTime"])).total_seconds()
    return (s["mfa"]["boundTo"] == {"signerId": s["signerId"], "statementDigest": rec["statementDigest"]}
            and 0 <= gap <= 300 and _t(s["signedAt"]) <= _t(rec["recordedAt"])
            and (s["role"] != "market_accountant" or s.get("market") == rec["countryCode"]))


def _rules(rec: dict) -> bool:
    so = rec["signOffs"]
    return (set(rec) == KEYS and isinstance(so, list) and len(so) == 2 and all(isinstance(s, dict) for s in so)
            and sorted(s.get("role") for s in so) == ["founder", "market_accountant"]
            and len({s["signerId"] for s in so}) == 2 and rec["requestedBy"] in {s["signerId"] for s in so}
            and len({s["mfa"]["assertionRef"] for s in so}) == 2
            and rec["statementDigest"] == _statement(rec)
            and all(s["statementDigest"] == rec["statementDigest"] and _signoff_ok(rec, s) for s in so))


def _schema_ok(rec: dict) -> bool:
    if Draft202012Validator is None:
        return True
    reg = Registry()
    for f in CONTRACTS.glob("country-pack-*.schema.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        reg = reg.with_resource(d["$id"], Resource.from_contents(d))
    schema = json.loads((CONTRACTS / "country-pack-change-record.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=reg).is_valid(rec)


def validate_change_record(rec) -> None:
    try:
        ok = isinstance(rec, dict) and _rules(rec) and _schema_ok(rec)
    except Exception:  # missing schema file, malformed record: all refusals
        ok = False
    if not ok:
        raise PublishError("PP-062")
