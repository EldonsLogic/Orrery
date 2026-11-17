"""A plugged engine (STUDIO_ENGINE=module:factory) cannot list its unsupported value types (contract 0.1.2), so apply
retries once without 'attachment' fields when the preview is rejected, and says how many were dropped. The factory
here is the in-memory fake loaded through the plugged path, which rejects 'attachment' the same way the real adapter
does (checked against the BPL-012 adapter by hand in the PR that added this test)."""
import pytest

import studio_testlib


@pytest.fixture
def plugged(monkeypatch):
    monkeypatch.setenv("STUDIO_ENGINE", "adapter.harness:FakeHarness")
    srv, client = studio_testlib.start_server()
    yield client
    srv.shutdown()
    srv.server_close()


def test_state_reports_a_plugged_engine(plugged):
    status, body, _ = plugged.get("/api/state")
    assert status == 200 and body["engine"]["kind"] == "plugged"


def test_apply_on_a_plugged_engine_retries_without_unsupported_fields(plugged):
    status, body, _ = plugged.post("/api/apply", {})
    assert status == 200, body
    assert body["ok"] and body["status"] == "applied", body
    assert body["droppedFields"] > 0
    assert body["exportHashMatches"] is True
