"""A plugged engine (STUDIO_ENGINE=module:factory) cannot list its unsupported value types (contract 0.1.2), so apply
retries once without 'attachment' fields when the preview is rejected, and says how many were dropped. The factory
here is the in-memory fake loaded through the plugged path, which rejects 'attachment' the same way the real adapter
does. The real BPL-012 adapter is also run when it can be imported here (it needs Python 3.10+ and pydantic)."""
import importlib
import sys

import pytest

import studio_testlib

CHANGE_ENGINE = studio_testlib.REPO / "apps" / "engine" / "change_engine"
REAL = "change_engine.adapter.harness:make_harness"


@pytest.fixture(params=["adapter.harness:FakeHarness", REAL])
def plugged(request, monkeypatch):
    if request.param == REAL:
        monkeypatch.syspath_prepend(str(CHANGE_ENGINE))
        try:
            importlib.import_module("change_engine.adapter.harness")
        except Exception as exc:  # noqa: BLE001  (an older Python or a missing dependency: skip, do not fail)
            for name in [m for m in sys.modules if m == "change_engine" or m.startswith("change_engine.")]:
                del sys.modules[name]
            pytest.skip(f"real adapter not importable here ({type(exc).__name__})")
    monkeypatch.setenv("STUDIO_ENGINE", request.param)
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


def test_two_applies_and_a_rollback_on_a_plugged_engine(plugged):
    """The base of an incremental compile is the engine-form Blueprint that was applied, attachment skip included."""
    first = plugged.post("/api/apply", {})[1]
    assert first["ok"] and first["droppedFields"] > 0, first
    base_hash = plugged.get("/api/export")[1]["exportHash"]
    plugged.put("/api/blueprint/entities/customer/labels", {"en": "Client", "ar": "عميل"})
    status, second, _ = plugged.post("/api/apply", {})
    assert status == 200 and second["ok"] and second["incremental"] is True, second
    assert second["exportHashMatches"] is True
    plugged.put("/api/blueprint/entities/customer/labels", {"en": "Account", "ar": "حساب"})
    status, third, _ = plugged.post("/api/apply", {})
    assert status == 200 and third["ok"] and third["incremental"] is True, third
    status, back, _ = plugged.post("/api/rollback")
    assert status == 200 and back["ok"], back
    assert plugged.get("/api/export")[1]["exportHash"] == second["exportHashAfter"]
    status, back, _ = plugged.post("/api/rollback")
    assert status == 200 and back["ok"], back
    assert plugged.get("/api/export")[1]["exportHash"] == base_hash
