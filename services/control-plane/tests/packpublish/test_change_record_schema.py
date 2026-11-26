"""Slice 4: the change record body is validated against its schema and rules before commit."""
import copy
import json

import pytest
from pp_support import HAVE_SCHEMA, schema_errors
from test_change_records import apply, code, sign_change, two_versions, withdraw

from packpublish.changerecord import validate_change_record
from packpublish.workflow import PackPublisher


def _record():
    w = two_versions()[0]
    return apply(w, withdraw(w))["changeRecord"]


def test_change_record_matches_schema_and_rules():
    r = _record()
    assert schema_errors("change-record", r) == []
    validate_change_record(r)


@pytest.mark.parametrize("mutate", [
    lambda r: r.__setitem__("signOffs", r["signOffs"][:1]),  # missing signer
    lambda r: r["signOffs"].__setitem__(1, copy.deepcopy(r["signOffs"][0])),  # same person and role twice
    lambda r: r["signOffs"][1].update(signerId=r["signOffs"][0]["signerId"]),  # same person, two roles
    lambda r: r["signOffs"][1]["mfa"].update(assertionRef=r["signOffs"][0]["mfa"]["assertionRef"]),
    lambda r: r.update(requestedBy="staff:someone-else"),
    lambda r: r["signOffs"][0].update(statementDigest="sha256:" + "00" * 32),
    lambda r: r.update(tenantId="t1"),  # no tenant fields
])
def test_invalid_change_record_refused(mutate):
    r = _record()
    mutate(r)
    assert code(validate_change_record, r) == "PP-062"


@pytest.mark.skipif(not HAVE_SCHEMA, reason="needs jsonschema and referencing")
def test_schema_refuses_missing_signer_and_extra_field():
    r = _record()
    assert schema_errors("change-record", {**r, "tenantId": "t1"}) != []
    r["signOffs"] = r["signOffs"][:1]
    assert schema_errors("change-record", r) != []


def test_apply_refuses_bad_record_before_commit(monkeypatch):
    w, _, _ = two_versions()
    c = withdraw(w)
    sos = sign_change(w, c)
    monkeypatch.setattr(PackPublisher, "_check_pair", lambda self, d, s, a: self.clock())  # skip the earlier gate
    assert code(apply, w, c, sos=[sos[0], sos[0]]) == "PP-062"
    assert json.loads(w.store.indexes["SA"])["withdrawn"] == [] and w.store.change_records == {}
