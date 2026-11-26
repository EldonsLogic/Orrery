"""BPL-039 slice 2: edit, incremental apply and a real rollback through the Studio session (synthetic fixture only)."""
import re

import pytest

from studio_testlib import STATIC


def _field(s, eid, fid):
    entity = next(e for e in s.blueprint["entities"] if e["id"] == eid)
    return next(f for f in entity["fields"] if f["id"] == fid)


def _set_max_length(s, eid, fid, value):
    """No Studio endpoint edits a field, so the test edits the working Blueprint the way an endpoint would."""
    _field(s, eid, fid)["maxLength"] = value
    s._touch()


@pytest.fixture
def s(server, client):
    return server[0].session


def test_first_apply_edit_incremental_apply_then_rollback_restores_the_base(client, s):
    first = client.post("/api/apply", {})[1]
    assert first["ok"] and first["incremental"] is False and s.last_applied_bp["meta"]["revision"] == 1
    base_hash = client.get("/api/export")[1]["exportHash"]
    status, body, _ = client.put("/api/blueprint/entities/customer/labels", {"en": "Client", "ar": "عميل"})
    assert status == 200 and body["blueprint"]["revision"] == 2
    comp = client.post("/api/compile")[1]
    assert comp["ok"] and comp["incremental"] and 0 < comp["stepCount"] < first["stepCount"]
    second = client.post("/api/apply", {})[1]
    assert second["ok"] and second["incremental"] is True and second["stepCount"] == comp["stepCount"]
    assert second["exportHashMatches"] and second["exportHashAfter"] != base_hash
    status, back, _ = client.post("/api/rollback")
    assert status == 200 and back["ok"] and back["siteChanged"] is True
    assert client.get("/api/export")[1]["exportHash"] == base_hash


def test_history_moves_back_after_a_rollback(client, s):
    client.post("/api/apply", {})
    initial = s.last_applied["artifactId"]
    client.put("/api/blueprint/entities/customer/labels", {"en": "Client", "ar": "عميل"})
    second = client.post("/api/apply", {})[1]
    assert second["ok"], second
    assert s.last_applied["artifactId"] != initial and len(s.history) == 2
    assert client.get("/api/state")[1]["site"]["historyDepth"] == 2
    assert client.post("/api/rollback")[1]["ok"]
    assert s.last_applied["artifactId"] == initial and len(s.history) == 1
    assert s.last_applied_bp["meta"]["revision"] == 1
    site = client.get("/api/state")[1]["site"]
    assert site["appliedArtifactId"] == initial and site["canRollback"] is False  # the initial build has no inverse


def test_a_narrowing_inverse_gets_gate_approved(client, s):
    client.post("/api/apply", {})
    _set_max_length(s, "customer", "customer_name", 200)  # widening forward; the inverse narrows back to 140
    assert client.post("/api/apply", {})[1]["ok"]
    back = client.post("/api/rollback")[1]
    assert back["ok"] and back["approvalsGranted"] == ["gateApproved", "rollbackApproved"]


def test_an_irreversible_change_is_flagged_and_its_rollback_is_refused_with_the_reason(client, s):
    client.post("/api/apply", {})
    _set_max_length(s, "customer", "customer_name", 20)
    comp = client.post("/api/compile")[1]
    flagged = [x for x in comp["steps"] if x["irreversibleReason"]]
    assert comp["irreversibleCount"] == 1 and flagged[0]["irreversibleReason"] == "length_reduction"
    assert client.post("/api/apply", {})[1]["ok"]
    hash_before = client.get("/api/export")[1]["exportHash"]
    status, back, _ = client.post("/api/rollback")
    assert status == 409 and back["status"] == "rejected"
    assert back["error"]["code"] == "rollback_not_possible" and back["error"]["reasonCode"] == "irreversible_step"
    assert back["siteChanged"] is False and client.get("/api/export")[1]["exportHash"] == hash_before
    assert len(s.history) == 2


def test_new_ui_strings_exist_in_both_languages():
    src = (STATIC / "i18n.js").read_text(encoding="utf-8")
    for key in ("compile.incremental", "steps.irreversible", "apply.history", "apply.kind", "apply.incremental", "apply.full", "steps.reversible", "apply.rolledBack", "reason.irreversible_step",
                "reason.length_reduction", "reason.type_change", "reason.link_target_change", "reason.precision_reduction",
                "reason.no_inverse", "reason.not_latest"):
        assert len(re.findall(r"'%s':" % re.escape(key), src)) == 2, key
