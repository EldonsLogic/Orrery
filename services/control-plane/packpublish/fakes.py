"""In-memory fakes for tests only. Never import from production code."""
from __future__ import annotations

import copy
import json


class FakeTrustedSigners:
    def __init__(self, accountants: dict, founders: dict):
        self.accountants, self.founders = accountants, founders  # {(market, id): name}, {id: login}

    def accountant_name(self, market, signer_id):
        return self.accountants.get((market, signer_id))

    def founder_login(self, signer_id):
        return self.founders.get(signer_id)


def fake_signature(signer_id: str, statement_digest: str) -> dict:
    return {"format": "webauthn.get.v1", "credentialId": "cred-" + signer_id.replace(":", "-").ljust(16, "x"),
            "authenticatorData": "A" * 49, "clientDataJSON": "B" * 20, "signature": "fake" + signer_id.replace(":", "-") + statement_digest[7:]}


class FakeSignerVerifier:
    def verify(self, signer_id, statement_digest, signature, key_env):
        if signature is None:
            return key_env != "production"  # Q-652: only the publisher key alone, and only outside production
        return signature == fake_signature(signer_id, statement_digest)


class FakeAuditStore:
    def __init__(self):
        self.entries, self.fail = {}, False

    def write(self, audit_id, entry):
        if self.fail:
            raise OSError("audit down")
        self.entries[audit_id] = copy.deepcopy(entry)


class FakePackStore:
    def __init__(self):
        self.indexes, self.records, self.pins, self.requests, self.pin_log = {}, {}, {}, {}, []

    def latest_index(self, country):
        return self.indexes.get(country)

    def get_request(self, request_id):
        r = self.requests.get(request_id)
        return None if r is None else (r[0], copy.deepcopy(r[1]))

    def get_pin(self, tenant_id, country):
        p = self.pins.get((tenant_id, country))
        return None if p is None else copy.deepcopy(p)

    def commit_publish(self, country, expected_seq, record, index_bytes, request_id, fingerprint, result):
        cur = self.indexes.get(country)
        if (json.loads(cur)["indexSeq"] if cur else 0) != expected_seq or request_id in self.requests:
            raise RuntimeError("conflict")
        self.indexes[country] = index_bytes
        self.records[record["publishId"]] = copy.deepcopy(record)
        self.requests[request_id] = (fingerprint, copy.deepcopy(result))

    def commit_pin(self, tenant_id, country, expected_pin_seq, pin, request_id, fingerprint, result):
        cur = self.pins.get((tenant_id, country))
        if (cur["pinSeq"] if cur else 0) != expected_pin_seq or request_id in self.requests:
            raise RuntimeError("conflict")
        self.pins[(tenant_id, country)] = copy.deepcopy(pin)
        self.pin_log.append(copy.deepcopy(pin))
        self.requests[request_id] = (fingerprint, copy.deepcopy(result))
