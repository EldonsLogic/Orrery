"""ERP-029 reconciliation of admitted engine actions: applied, failed, unknown."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import sqlite3
import threading

import pytest

from change_engine.guarded_apply import action_policy_enforcer as policy

NOW = datetime(2026, 11, 21, tzinfo=timezone.utc)
LATER = NOW + timedelta(minutes=30)  # Past the handler deadline, before the stuck threshold.
KEY = b"k" * 32


@pytest.fixture
def recon():
    # Import at test time so a missing module fails each test, not collection.
    from change_engine.guarded_apply import action_outcome_reconciler

    return action_outcome_reconciler


def _request(n: int, tenant: str = "tenant-a") -> policy.ActionRequest:
    return policy.ActionRequest(
        tenant, f"request-{n}", "AP-FIN-01", 1, "sec-019-v1", f"key-{n}",
        {"delivery_ids": ["delivery-a"], "customer": "customer-a",
         "lines": [{"item": "item-a", "quantity": 2, "price": "20.00", "discount": "0.00"}],
         "total": "40.00", "currency": "SAR"},
        {"delivery-a": 3},
    )


def _context(request: policy.ActionRequest) -> policy.ActionContext:
    submitter = policy.Principal("finance-a", "human", frozenset({"finance"}))
    drafter = policy.Principal("agent-a", "agent", frozenset(), "owner-b")
    approver = policy.Principal("owner-a", "human", frozenset({"owner"}))
    approval = policy.Approval(
        f"approval-{request.tenant_id}-{request.request_id}", request.tenant_id, request.action_id,
        request.table_version, policy.payload_hash(request, submitter.id), approver,
        NOW + timedelta(hours=1), "approved", step_up=True,
    )
    return policy.ActionContext(
        request.tenant_id, request.request_id, request.action_id, submitter, drafter,
        in_scope=True, active=True, approvals=(approval,), amount="40.00", currency="SAR",
    )


def _admit(path, request, handler=None):
    """Admit through the real ERP-023 enforcer; run the handler when one is given."""
    context = _context(request)
    guard = policy.ActionPolicyEnforcer(
        lambda: policy.starter_table(invoice_cap="100.00", currency="SAR"),
        lambda session, req: context,
        policy.ActionPolicyStore(path),
        clock=lambda: NOW,
    )
    action = guard.authorize("trusted-session", request, session_tenant_id=request.tenant_id)
    assert action is not None
    if handler is not None:
        try:
            guard.execute_admitted(action, lambda run: run(object()), handler)
        except Exception:
            pass
    return policy.payload_hash(request, "finance-a")


def _applied(engine, action):
    return "posted"


def _failed(engine, action):
    raise policy.ActionEffectFailed("rolled back")


def _unknown(engine, action):
    raise RuntimeError("connection reset after commit?")


class Engine:
    """Injected read-only engine state keyed by (tenant, submitter, idempotency key)."""

    def __init__(self, recon):
        self.recon = recon
        self.effects: dict[tuple[str, str, str], tuple[str, str, str]] = {}
        self.calls: list[tuple[str, str, str]] = []
        self.error: Exception | None = None
        self.tenant_override: str | None = None

    def read(self, tenant_id, submitter_id, idempotency_key):
        self.calls.append((tenant_id, submitter_id, idempotency_key))
        if self.error is not None:
            raise self.error
        tenant = self.tenant_override or tenant_id
        found = self.effects.get((tenant_id, submitter_id, idempotency_key))
        if found is None:
            return self.recon.EngineReadback(tenant, submitter_id, idempotency_key, "pending")
        state, request_id, digest = found
        if state == "not_applied":
            return self.recon.EngineReadback(tenant, submitter_id, idempotency_key, "not_applied")
        return self.recon.EngineReadback(tenant, submitter_id, idempotency_key, state, request_id, digest)


def _reconciler(recon, path, engine, *, tenant="tenant-a", clock=lambda: NOW, stuck_after=timedelta(hours=1),
                read=None):
    return recon.ActionOutcomeReconciler(
        path, tenant_id=tenant, read_engine_state=read or engine.read, journal_key=KEY,
        clock=clock, stuck_after=stuck_after, handler_deadline=timedelta(minutes=10),
    )


def _states(results):
    return {r.request_id: (r.state, r.reason, r.stuck) for r in results}


def _journal(path):
    with sqlite3.connect(path) as db:
        return db.execute(
            "SELECT tenant_id, request_id, state, reason, stuck FROM action_outcome_reconciliation ORDER BY sequence"
        ).fetchall()


def test_applied_failed_and_unknown_then_unknown_resolved_by_readback(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _applied)
    _admit(path, _request(2), _failed)
    digest3 = _admit(path, _request(3), _unknown)
    digest4 = _admit(path, _request(4))  # Crash before any outcome was written.
    engine = Engine(recon)
    reconciler = _reconciler(recon, path, engine)

    first = _states(reconciler.reconcile())
    assert first == {
        "request-1": ("applied", "recorded", False),
        "request-2": ("failed", "recorded", False),
        "request-3": ("unknown", "readback_pending", False),
        "request-4": ("unknown", "readback_pending", False),
    }
    # Recorded terminal outcomes are not re-read; unknown ones are read by exact key only.
    assert engine.calls == [("tenant-a", "finance-a", "key-3"), ("tenant-a", "finance-a", "key-4")]

    engine.effects[("tenant-a", "finance-a", "key-3")] = ("applied", "request-3", digest3)
    engine.effects[("tenant-a", "finance-a", "key-4")] = ("not_applied", None, None)
    second = _states(reconciler.reconcile())
    assert second["request-3"] == ("applied", "readback", False)
    # No outcome was recorded and the handler may still be running: not_applied is not final yet.
    assert second["request-4"] == ("unknown", "handler_in_flight", False)
    third = _states(_reconciler(recon, path, engine, clock=lambda: LATER).reconcile())
    assert third["request-4"] == ("failed", "readback", False)
    assert _journal(path) == [
        ("tenant-a", "request-1", "applied", "recorded", 0),
        ("tenant-a", "request-2", "failed", "recorded", 0),
        ("tenant-a", "request-3", "unknown", "readback_pending", 0),
        ("tenant-a", "request-4", "unknown", "readback_pending", 0),
        ("tenant-a", "request-3", "applied", "readback", 0),
        ("tenant-a", "request-4", "unknown", "handler_in_flight", 0),
        ("tenant-a", "request-4", "failed", "readback", 0),
    ]
    assert digest4  # Bound digest was produced at admission.


def test_readback_must_match_request_and_payload_exactly(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    digest = _admit(path, _request(1), _unknown)
    engine = Engine(recon)
    reconciler = _reconciler(recon, path, engine)
    for found in (("applied", "request-9", digest), ("applied", "request-1", "sha256:" + "0" * 64),
                  ("applied", None, None), ("bogus", "request-1", digest)):
        engine.effects[("tenant-a", "finance-a", "key-1")] = found
        assert _states(reconciler.reconcile())["request-1"][0] == "unknown"
    engine.effects[("tenant-a", "finance-a", "key-1")] = ("applied", "request-1", digest)
    assert _states(reconciler.reconcile())["request-1"] == ("applied", "readback", False)


@pytest.mark.parametrize("error", [RuntimeError("engine down"), TimeoutError(), ValueError("bad")])
def test_reader_error_fails_closed_to_unknown(recon, tmp_path, error):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _unknown)
    engine = Engine(recon)
    engine.error = error
    results = _states(_reconciler(recon, path, engine).reconcile())
    assert results["request-1"] == ("unknown", "reader_error", False)
    assert [row[2] for row in _journal(path)] == ["unknown"]


def test_reader_returning_wrong_type_fails_closed(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _unknown)
    reconciler = _reconciler(recon, path, None, read=lambda *a: {"state": "applied"})
    assert _states(reconciler.reconcile())["request-1"] == ("unknown", "readback_invalid", False)


def test_duplicate_reconcile_is_idempotent(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _applied)
    digest = _admit(path, _request(2), _unknown)
    _admit(path, _request(3), _unknown)
    engine = Engine(recon)
    engine.effects[("tenant-a", "finance-a", "key-2")] = ("applied", "request-2", digest)
    reconciler = _reconciler(recon, path, engine)
    first = reconciler.reconcile()
    journal = _journal(path)
    assert reconciler.reconcile() == first
    assert _reconciler(recon, path, engine).reconcile() == first
    assert _journal(path) == journal
    # A resolved outcome is never read again.
    assert engine.calls.count(("tenant-a", "finance-a", "key-2")) == 1


def test_concurrent_reconcilers_append_one_terminal_entry(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    digest = _admit(path, _request(1), _unknown)
    engine = Engine(recon)
    engine.effects[("tenant-a", "finance-a", "key-1")] = ("applied", "request-1", digest)
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: _reconciler(recon, path, engine).reconcile(), range(8)))
    assert {_states(r)["request-1"] for r in results} == {("applied", "readback", False)}
    assert [row[2] for row in _journal(path)] == ["applied"]


def test_stuck_unknown_escalates_once_and_keeps_claims(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _unknown)
    engine = Engine(recon)
    later = NOW + timedelta(hours=2)
    reconciler = _reconciler(recon, path, engine, clock=lambda: later)
    assert _states(reconciler.reconcile())["request-1"] == ("unknown", "readback_pending", True)
    assert _states(reconciler.reconcile())["request-1"] == ("unknown", "readback_pending", True)
    assert [row[3:] for row in _journal(path)] == [("readback_pending", 1)]
    # Escalation never releases the replay claim: the same request is still refused.
    context = _context(_request(1))
    guard = policy.ActionPolicyEnforcer(
        lambda: policy.starter_table(invoice_cap="100.00", currency="SAR"),
        lambda session, req: context, policy.ActionPolicyStore(path), clock=lambda: NOW,
    )
    assert guard.authorize("trusted-session", _request(1), session_tenant_id="tenant-a") is None
    assert guard.store.audit_log()[-1].reason == "replay"


def test_unknown_then_stuck_journals_escalation(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _unknown)
    engine = Engine(recon)
    times = iter((NOW, NOW + timedelta(hours=2)))
    reconciler = _reconciler(recon, path, engine, clock=lambda: next(times))
    reconciler.reconcile()
    assert _states(reconciler.reconcile())["request-1"] == ("unknown", "readback_pending", True)
    assert [row[3:] for row in _journal(path)] == [("readback_pending", 0), ("readback_pending", 1)]


def test_journal_update_and_delete_are_refused(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _applied)
    _reconciler(recon, path, Engine(recon)).reconcile()
    with sqlite3.connect(path) as db:
        for sql in ("UPDATE action_outcome_reconciliation SET state = 'failed'",
                    "DELETE FROM action_outcome_reconciliation",
                    "INSERT OR REPLACE INTO action_outcome_reconciliation "
                    "SELECT * FROM action_outcome_reconciliation"):
            with pytest.raises(sqlite3.IntegrityError, match="Append-only reconciliation"):
                db.execute(sql)


@pytest.mark.parametrize("tamper", [
    "UPDATE action_outcome_reconciliation SET state = 'failed' WHERE request_id = 'request-1'",
    "UPDATE action_outcome_reconciliation SET request_id = 'request-3' WHERE request_id = 'request-1'",
    "UPDATE action_outcome_reconciliation SET tenant_id = 'tenant-b'",
    "DELETE FROM action_outcome_reconciliation WHERE request_id = 'request-1'",
    "UPDATE action_outcome_reconciliation SET mac = 'x' || substr(mac, 2)",
])
def test_tampered_journal_is_refused(recon, tmp_path, tamper):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _applied)
    _admit(path, _request(2), _applied)
    engine = Engine(recon)
    _reconciler(recon, path, engine).reconcile()
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER action_outcome_reconciliation_no_update")
        db.execute("DROP TRIGGER action_outcome_reconciliation_no_delete")
        db.execute(tamper)
    before = _journal(path)
    with pytest.raises(recon.ReconciliationRefused, match="journal_tampered"):
        _reconciler(recon, path, engine).reconcile()
    assert _journal(path) == before


def test_forged_journal_insert_is_refused(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _unknown)
    engine = Engine(recon)
    _reconciler(recon, path, engine).reconcile()
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT * FROM action_outcome_reconciliation").fetchone()
        columns = [c[1] for c in db.execute("PRAGMA table_info(action_outcome_reconciliation)")]
        forged = dict(zip(columns, row), sequence=row[0] + 1, state="applied", reason="readback")
        db.execute(f"INSERT INTO action_outcome_reconciliation ({','.join(columns)}) "
                   f"VALUES ({','.join('?' * len(columns))})", [forged[c] for c in columns])
    with pytest.raises(recon.ReconciliationRefused, match="journal_tampered"):
        _reconciler(recon, path, engine).reconcile()


def test_wrong_journal_key_is_refused(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _applied)
    engine = Engine(recon)
    _reconciler(recon, path, engine).reconcile()
    other = recon.ActionOutcomeReconciler(
        path, tenant_id="tenant-a", read_engine_state=engine.read, journal_key=b"z" * 32,
        clock=lambda: NOW, stuck_after=timedelta(hours=1), handler_deadline=timedelta(minutes=10),
    )
    with pytest.raises(recon.ReconciliationRefused, match="journal_tampered"):
        other.reconcile()


def test_tampered_admission_binding_never_resolves(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    digest = _admit(path, _request(1), _unknown)
    _admit(path, _request(2), _applied)
    engine = Engine(recon)
    engine.effects[("tenant-a", "finance-a", "key-9")] = ("applied", "request-1", digest)
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER action_policy_admission_keys_no_update")
        # Another request's key is already bound: one key binds one request.
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE action_policy_admission_keys SET idempotency_key = 'key-2' "
                       "WHERE request_id = 'request-1'")
        # A key with no committed idempotency claim never reaches the engine reader.
        db.execute("UPDATE action_policy_admission_keys SET idempotency_key = 'key-9' "
                   "WHERE request_id = 'request-1'")
    results = _states(_reconciler(recon, path, engine).reconcile())
    assert results["request-1"] == ("unknown", "admission_unbound", False)
    assert ("tenant-a", "finance-a", "key-9") not in engine.calls


def test_cross_tenant_request_is_refused(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _applied)
    _admit(path, _request(7, tenant="tenant-b"), _unknown)
    engine = Engine(recon)
    reconciler = _reconciler(recon, path, engine)
    assert set(_states(reconciler.reconcile())) == {"request-1"}
    with pytest.raises(recon.ReconciliationRefused, match="unknown_request"):
        reconciler.reconcile(request_ids=("request-7",))
    assert all(call[0] == "tenant-a" for call in engine.calls)
    assert {row[0] for row in _journal(path)} == {"tenant-a"}


def test_cross_tenant_readback_never_resolves(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    digest = _admit(path, _request(1), _unknown)
    engine = Engine(recon)
    engine.tenant_override = "tenant-b"
    engine.effects[("tenant-a", "finance-a", "key-1")] = ("applied", "request-1", digest)
    assert _states(_reconciler(recon, path, engine).reconcile())["request-1"] == (
        "unknown", "readback_mismatch", False)


def test_tenant_b_journal_rows_stay_separate(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _applied)
    _admit(path, _request(1, tenant="tenant-b"), _failed)
    engine = Engine(recon)
    a = _states(_reconciler(recon, path, engine).reconcile())
    b = _states(_reconciler(recon, path, engine, tenant="tenant-b").reconcile())
    assert a == {"request-1": ("applied", "recorded", False)}
    assert b == {"request-1": ("failed", "recorded", False)}
    # Re-verifying tenant-a's chain is unaffected by tenant-b's entries.
    assert _states(_reconciler(recon, path, engine).reconcile()) == a


@pytest.mark.parametrize("kwargs", [
    {"tenant_id": ""}, {"tenant_id": None}, {"journal_key": b"short"}, {"journal_key": "k" * 32},
    {"stuck_after": timedelta(0)}, {"stuck_after": 3600},
    {"handler_deadline": timedelta(0)}, {"handler_deadline": 600}, {"handler_deadline": timedelta(hours=1)},
    {"read_engine_state": None}, {"clock": None},
])
def test_invalid_configuration_is_refused(recon, tmp_path, kwargs):
    base = dict(tenant_id="tenant-a", read_engine_state=lambda *a: None, journal_key=KEY,
                clock=lambda: NOW, stuck_after=timedelta(hours=1), handler_deadline=timedelta(minutes=10))
    with pytest.raises(ValueError):
        recon.ActionOutcomeReconciler(tmp_path / "policy.sqlite3", **{**base, **kwargs})
    with pytest.raises(ValueError):
        recon.ActionOutcomeReconciler(":memory:", **base)


@pytest.mark.parametrize("clock", [
    lambda: datetime(2026, 11, 21), lambda: "now", lambda: 1 / 0,
    lambda: NOW - timedelta(seconds=1),  # Earlier than the admission.
])
def test_untrusted_clock_refuses_run(recon, tmp_path, clock):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _unknown)
    with pytest.raises(recon.ReconciliationRefused, match="clock_unavailable"):
        _reconciler(recon, path, Engine(recon), clock=clock).reconcile()
    assert _journal(path) == []


def test_enforcer_admission_is_unchanged_by_binding(tmp_path):
    """The store hook adds a binding row only for admissions; denials and replays add none."""
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1))
    context = _context(_request(1))
    guard = policy.ActionPolicyEnforcer(
        lambda: policy.starter_table(invoice_cap="100.00", currency="SAR"),
        lambda session, req: context, policy.ActionPolicyStore(path), clock=lambda: NOW,
    )
    assert guard.authorize("trusted-session", _request(1), session_tenant_id="tenant-a") is None
    denied = replace(_request(2), action_id="AP-PAY-01")
    assert guard.authorize("trusted-session", denied, session_tenant_id="tenant-a") is None
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT tenant_id, request_id, submitter_id, idempotency_key "
                          "FROM action_policy_admission_keys").fetchall()
    assert rows == [("tenant-a", "request-1", "finance-a", "key-1")]


# ---------------------------------------------------------------- review fix round (PR #260)
def _journal_failed_request_2(recon, path, engine):
    """request-1 applied, request-2 journaled failed by read-back, request-3 still unknown."""
    _admit(path, _request(1), _applied)
    _admit(path, _request(2))  # No outcome recorded.
    digest3 = _admit(path, _request(3), _unknown)
    engine.effects[("tenant-a", "finance-a", "key-2")] = ("not_applied", None, None)
    results = _reconciler(recon, path, engine, clock=lambda: LATER).reconcile(request_ids=("request-2",))
    assert _states(results) == {"request-2": ("failed", "readback", False)}
    return digest3


def test_outcome_conflict_is_journaled_once_escalated_and_sticky(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    engine = Engine(recon)
    _journal_failed_request_2(recon, path, engine)
    policy.ActionPolicyStore(path).record_outcome("tenant-a", "request-2", "applied")
    later = NOW + timedelta(hours=2)
    reconciler = _reconciler(recon, path, engine, clock=lambda: later)
    first = _states(reconciler.reconcile())
    assert first == {
        "request-1": ("applied", "recorded", False),
        "request-2": ("unknown", "outcome_conflict", True),
        "request-3": ("unknown", "readback_pending", True),
    }
    expected = [
        ("tenant-a", "request-2", "failed", "readback", 0),
        ("tenant-a", "request-2", "unknown", "outcome_conflict", 1),
        ("tenant-a", "request-1", "applied", "recorded", 0),
        ("tenant-a", "request-3", "unknown", "readback_pending", 1),
    ]
    assert _journal(path) == expected
    # Sticky and written once: repeat runs on the same or a new instance add no duplicate entry.
    assert _states(reconciler.reconcile()) == first
    assert _states(_reconciler(recon, path, engine, clock=lambda: later).reconcile()) == first
    assert _journal(path) == expected


def test_unrelated_stuck_request_still_journals_and_escalates_when_conflict_exists(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    engine = Engine(recon)
    _journal_failed_request_2(recon, path, engine)
    policy.ActionPolicyStore(path).record_outcome("tenant-a", "request-2", "applied")
    later = NOW + timedelta(hours=2)
    reconciler = _reconciler(recon, path, engine, clock=lambda: later)
    assert _states(reconciler.reconcile(("request-3",))) == {
        "request-3": ("unknown", "readback_pending", True),
    }
    assert _journal(path) == [
        ("tenant-a", "request-2", "failed", "readback", 0),
        ("tenant-a", "request-2", "unknown", "outcome_conflict", 1),
        ("tenant-a", "request-3", "unknown", "readback_pending", 1),
    ]
    # A subsequent full run writes no duplicate conflict or stuck entry.
    assert _states(reconciler.reconcile()) == {
        "request-1": ("applied", "recorded", False),
        "request-2": ("unknown", "outcome_conflict", True),
        "request-3": ("unknown", "readback_pending", True),
    }
    assert [r for r in _journal(path) if r[3] == "outcome_conflict"] == [
        ("tenant-a", "request-2", "unknown", "outcome_conflict", 1),
    ]


def test_new_not_applied_readback_stays_unknown_while_conflict_is_open(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    engine = Engine(recon)
    digest3 = _journal_failed_request_2(recon, path, engine)
    _admit(path, _request(4))  # Missing outcome, read-back says not_applied.
    policy.ActionPolicyStore(path).record_outcome("tenant-a", "request-2", "applied")
    engine.effects[("tenant-a", "finance-a", "key-3")] = ("applied", "request-3", digest3)
    engine.effects[("tenant-a", "finance-a", "key-4")] = ("not_applied", None, None)

    first = _states(_reconciler(recon, path, engine, clock=lambda: LATER).reconcile())
    assert first == {
        "request-1": ("applied", "recorded", False),
        "request-2": ("unknown", "outcome_conflict", True),
        "request-3": ("applied", "readback", False),
        "request-4": ("unknown", "readback_pending", False),
    }
    # After stuck_after, the unfinalised not_applied request escalates while the conflict stays open.
    second = _states(_reconciler(recon, path, engine, clock=lambda: NOW + timedelta(hours=2)).reconcile())
    assert second["request-2"] == ("unknown", "outcome_conflict", True)
    assert second["request-4"] == ("unknown", "readback_pending", True)


def test_outcome_conflict_recorded_during_the_run_is_journaled_under_the_lock(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    engine = Engine(recon)
    digest3 = _journal_failed_request_2(recon, path, engine)
    _admit(path, _request(4), _unknown)

    def read(tenant_id, submitter_id, key):
        if key == "key-3":
            policy.ActionPolicyStore(path).record_outcome("tenant-a", "request-2", "applied")
            return recon.EngineReadback(tenant_id, submitter_id, key, "applied", "request-3", digest3)
        return recon.EngineReadback(tenant_id, submitter_id, key, "not_applied")

    results = _states(_reconciler(recon, path, engine, clock=lambda: LATER, read=read).reconcile())
    assert results == {
        "request-1": ("applied", "recorded", False),
        "request-2": ("unknown", "outcome_conflict", True),
        "request-3": ("applied", "readback", False),
        "request-4": ("unknown", "readback_pending", False),
    }


def test_outcome_recorded_during_the_readback_wins(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1))  # No outcome yet: the handler is slow.

    def read(tenant_id, submitter_id, key):
        policy.ActionPolicyStore(path).record_outcome("tenant-a", "request-1", "applied")
        return recon.EngineReadback(tenant_id, submitter_id, key, "not_applied")

    reconciler = _reconciler(recon, path, None, clock=lambda: LATER, read=read)
    assert _states(reconciler.reconcile()) == {"request-1": ("applied", "recorded", False)}
    assert _journal(path) == [("tenant-a", "request-1", "applied", "recorded", 0)]
    assert _states(reconciler.reconcile()) == {"request-1": ("applied", "recorded", False)}


def _mismatched_reader(recon):
    return lambda t, s, k: recon.EngineReadback("tenant-b", s, k, "pending")


def _invalid_reader(recon):
    return lambda t, s, k: {"state": "applied"}


def _failing_reader(recon):
    def read(t, s, k):
        raise RuntimeError("engine down")
    return read


@pytest.mark.parametrize("reason, make_reader", [
    ("readback_mismatch", _mismatched_reader),
    ("readback_invalid", _invalid_reader),
    ("reader_error", _failing_reader),
    ("admission_unbound", _mismatched_reader),
])
def test_stuck_keeps_the_specific_reason_and_escalates_once(recon, tmp_path, reason, make_reader):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _unknown)
    if reason == "admission_unbound":
        with sqlite3.connect(path) as db:
            db.execute("DELETE FROM action_policy_claims WHERE kind = 'idempotency'")
    later = NOW + timedelta(hours=2)
    times = iter((NOW, later, later))
    reconciler = _reconciler(recon, path, None, clock=lambda: next(times), read=make_reader(recon))
    assert _states(reconciler.reconcile())["request-1"] == ("unknown", reason, False)
    assert _states(reconciler.reconcile())["request-1"] == ("unknown", reason, True)
    assert _states(reconciler.reconcile())["request-1"] == ("unknown", reason, True)
    assert _journal(path) == [
        ("tenant-a", "request-1", "unknown", reason, 0),
        ("tenant-a", "request-1", "unknown", reason, 1),
    ]


def test_journal_sequence_must_be_positive(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _applied)
    _reconciler(recon, path, Engine(recon)).reconcile()
    with sqlite3.connect(path) as db, pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO action_outcome_reconciliation "
                   "SELECT 0, tenant_id, 'request-9', state, reason, stuck, timestamp, mac "
                   "FROM action_outcome_reconciliation")


@pytest.mark.parametrize("tamper", [
    # A forged final entry outside the checked range would block request-3 forever.
    "INSERT INTO action_outcome_reconciliation SELECT 0, tenant_id, 'request-3', 'applied', "
    "'readback', 0, timestamp, mac FROM action_outcome_reconciliation WHERE sequence = 1",
    "INSERT INTO action_outcome_reconciliation SELECT -7, tenant_id, request_id, state, reason, stuck, "
    "timestamp, mac FROM action_outcome_reconciliation WHERE sequence = 3",
    "UPDATE action_outcome_reconciliation SET sequence = -1 WHERE sequence = 3",
    "UPDATE action_outcome_reconciliation SET sequence = 0 WHERE sequence = 1",
])
def test_out_of_range_sequence_is_refused_without_integrity_error(recon, tmp_path, tamper):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _applied)
    _admit(path, _request(2), _applied)
    digest = _admit(path, _request(3), _unknown)
    engine = Engine(recon)
    reconciler = _reconciler(recon, path, engine)
    reconciler.reconcile()
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA ignore_check_constraints = ON")
        db.execute("DROP TRIGGER action_outcome_reconciliation_no_update")
        db.execute(tamper)
        if "SELECT 0," in tamper:
            reconciler._prev = ""
            for seq, *fields in db.execute(
                "SELECT sequence, tenant_id, request_id, state, reason, stuck, timestamp "
                "FROM action_outcome_reconciliation ORDER BY sequence"
            ).fetchall():
                mac = reconciler._mac(seq, tuple(fields))
                db.execute("UPDATE action_outcome_reconciliation SET mac = ? WHERE sequence = ?", (mac, seq))
                reconciler._prev = mac
    before, calls = _journal(path), list(engine.calls)
    engine.effects[("tenant-a", "finance-a", "key-3")] = ("applied", "request-3", digest)
    with pytest.raises(recon.ReconciliationRefused, match="journal_tampered"):
        _reconciler(recon, path, engine).reconcile()
    assert _journal(path) == before
    assert engine.calls == calls


@pytest.mark.parametrize("ddl", [
    "CREATE TABLE action_outcome_reconciliation (sequence INTEGER PRIMARY KEY CHECK (sequence > 0), "
    "tenant_id TEXT NOT NULL, request_id TEXT NOT NULL, state TEXT NOT NULL, "
    "reason TEXT NOT NULL, timestamp TEXT NOT NULL, mac TEXT NOT NULL)",
    "CREATE TABLE action_outcome_reconciliation (sequence INTEGER PRIMARY KEY, "
    "tenant_id TEXT NOT NULL, request_id TEXT NOT NULL, state TEXT NOT NULL, "
    "reason TEXT NOT NULL, stuck INTEGER NOT NULL, timestamp TEXT NOT NULL, mac TEXT NOT NULL)",
])
def test_journal_with_an_older_schema_is_refused(recon, tmp_path, ddl):
    path = tmp_path / "policy.sqlite3"
    policy.ActionPolicyStore(path)
    with sqlite3.connect(path) as db:
        db.execute(ddl)
    with pytest.raises(ValueError, match="schema"):
        _reconciler(recon, path, Engine(recon))


def test_clock_earlier_than_the_journal_refuses_the_run(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _unknown)
    engine = Engine(recon)
    _reconciler(recon, path, engine, clock=lambda: NOW + timedelta(hours=2)).reconcile()
    before = _journal(path)
    with pytest.raises(recon.ReconciliationRefused, match="clock_unavailable"):
        _reconciler(recon, path, engine, clock=lambda: LATER).reconcile()
    assert _journal(path) == before


@pytest.mark.parametrize("echo", [{"submitter_id": "finance-b"}, {"idempotency_key": "key-9"}])
def test_readback_must_echo_submitter_and_key(recon, tmp_path, echo):
    path = tmp_path / "policy.sqlite3"
    digest = _admit(path, _request(1), _unknown)

    def read(tenant_id, submitter_id, key):
        found = recon.EngineReadback(tenant_id, submitter_id, key, "applied", "request-1", digest)
        return replace(found, **echo)

    results = _states(_reconciler(recon, path, None, read=read).reconcile())
    assert results["request-1"] == ("unknown", "readback_mismatch", False)


@pytest.mark.parametrize("extra", [{"request_id": "request-1"}, {"payload_hash": "sha256:" + "0" * 64}])
def test_not_applied_must_carry_no_effect_fields(recon, tmp_path, extra):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _unknown)

    def read(tenant_id, submitter_id, key):
        return recon.EngineReadback(tenant_id, submitter_id, key, "not_applied", **extra)

    results = _states(_reconciler(recon, path, None, read=read).reconcile())
    assert results["request-1"] == ("unknown", "readback_mismatch", False)
    # A recorded unknown also waits for handler_deadline before accepting a clean not_applied.
    clean_now = _reconciler(recon, path, None, read=lambda t, s, k: recon.EngineReadback(t, s, k, "not_applied"))
    assert _states(clean_now.reconcile())["request-1"] == ("unknown", "handler_in_flight", False)
    results_later = _states(_reconciler(recon, path, None, clock=lambda: LATER, read=read).reconcile())
    assert results_later["request-1"] == ("unknown", "readback_mismatch", False)
    clean_later = _reconciler(
        recon, path, None, clock=lambda: LATER, read=lambda t, s, k: recon.EngineReadback(t, s, k, "not_applied"))
    assert _states(clean_later.reconcile())["request-1"] == ("failed", "readback", False)


def test_binding_submitter_must_match_the_audited_submitter(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    digest = _admit(path, _request(1), _unknown)
    engine = Engine(recon)
    engine.effects[("tenant-a", "finance-b", "key-1")] = ("applied", "request-1", digest)
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER action_policy_admission_keys_no_update")
        db.execute("INSERT INTO action_policy_claims VALUES ('tenant-a', 'idempotency', ?)",
                   ('["finance-b", "key-1"]',))
        db.execute("UPDATE action_policy_admission_keys SET submitter_id = 'finance-b'")
    results = _states(_reconciler(recon, path, engine).reconcile())
    assert results["request-1"] == ("unknown", "admission_unbound", False)
    assert engine.calls == []


def test_admission_binding_is_read_for_the_bound_tenant_only(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, replace(_request(1, tenant="tenant-b"), idempotency_key="key-b"), _unknown)
    digest = _admit(path, _request(1), _unknown)
    engine = Engine(recon)
    engine.effects[("tenant-a", "finance-a", "key-1")] = ("applied", "request-1", digest)
    results = _states(_reconciler(recon, path, engine).reconcile())
    assert results["request-1"] == ("applied", "readback", False)
    assert engine.calls == [("tenant-a", "finance-a", "key-1")]


def test_racing_reconcilers_with_contradictory_readbacks_append_one_final_entry(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    digest = _admit(path, _request(1), _unknown)
    barrier = threading.Barrier(2, timeout=10)

    def reader(state):
        def read(tenant_id, submitter_id, key):
            barrier.wait()  # Both runs hold a read-back before either appends.
            if state == "applied":
                return recon.EngineReadback(tenant_id, submitter_id, key, state, "request-1", digest)
            return recon.EngineReadback(tenant_id, submitter_id, key, state)
        return read

    reconcilers = [_reconciler(recon, path, None, clock=lambda: LATER, read=reader(s)) for s in ("applied", "not_applied")]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda r: r.reconcile(), reconcilers))
    assert len({_states(r)["request-1"] for r in results}) == 1
    journal = _journal(path)
    assert len(journal) == 1 and journal[0][2] in ("applied", "failed")


def test_one_instance_shared_across_threads(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    digest = _admit(path, _request(1), _unknown)
    _admit(path, _request(2), _applied)
    engine = Engine(recon)
    engine.effects[("tenant-a", "finance-a", "key-1")] = ("applied", "request-1", digest)
    reconciler = _reconciler(recon, path, engine)
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda _: reconciler.reconcile(), range(16)))
    assert {_states(r)["request-1"] for r in results} == {("applied", "readback", False)}
    assert [row[1:3] for row in _journal(path)] == [("request-1", "applied"), ("request-2", "applied")]


# ---------------------------------------------------------------- fix round 2 (PR #260)
@pytest.mark.parametrize("handler", [None, _unknown])
def test_handler_deadline_boundary_for_missing_and_recorded_unknown(recon, tmp_path, handler):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), handler)
    engine = Engine(recon)
    engine.effects[("tenant-a", "finance-a", "key-1")] = ("not_applied", None, None)
    before_deadline = NOW + timedelta(minutes=10) - timedelta(seconds=1)
    at_deadline = NOW + timedelta(minutes=10)
    times = iter((before_deadline, at_deadline))
    reconciler = _reconciler(recon, path, engine, clock=lambda: next(times))
    assert _states(reconciler.reconcile())["request-1"] == ("unknown", "handler_in_flight", False)
    assert _states(reconciler.reconcile())["request-1"] == ("failed", "readback", False)
    assert _journal(path) == [
        ("tenant-a", "request-1", "unknown", "handler_in_flight", 0),
        ("tenant-a", "request-1", "failed", "readback", 0),
    ]


def test_stuck_after_boundary(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _unknown)
    engine = Engine(recon)
    before_stuck = NOW + timedelta(hours=1) - timedelta(seconds=1)
    at_stuck = NOW + timedelta(hours=1)
    times = iter((before_stuck, at_stuck))
    reconciler = _reconciler(recon, path, engine, clock=lambda: next(times))
    assert _states(reconciler.reconcile())["request-1"] == ("unknown", "readback_pending", False)
    assert _states(reconciler.reconcile())["request-1"] == ("unknown", "readback_pending", True)
    assert _journal(path) == [
        ("tenant-a", "request-1", "unknown", "readback_pending", 0),
        ("tenant-a", "request-1", "unknown", "readback_pending", 1),
    ]


def test_reason_change_before_stuck_threshold_is_journaled(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    digest = _admit(path, _request(1), _unknown)
    engine = Engine(recon)
    reconciler = _reconciler(recon, path, engine)
    assert _states(reconciler.reconcile())["request-1"] == ("unknown", "readback_pending", False)
    engine.effects[("tenant-a", "finance-a", "key-1")] = ("applied", "request-9", digest)
    assert _states(reconciler.reconcile())["request-1"] == ("unknown", "readback_mismatch", False)
    assert _states(reconciler.reconcile())["request-1"] == ("unknown", "readback_mismatch", False)
    assert _journal(path) == [
        ("tenant-a", "request-1", "unknown", "readback_pending", 0),
        ("tenant-a", "request-1", "unknown", "readback_mismatch", 0),
    ]


def test_rolled_back_commit_restores_in_memory_head(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _applied)
    _admit(path, _request(2), _applied)
    engine = Engine(recon)
    reconciler = _reconciler(recon, path, engine)
    assert _states(reconciler.reconcile(("request-1",))) == {"request-1": ("applied", "recorded", False)}

    _admit(path, _request(3), _applied)
    real_insert = reconciler._insert
    calls = 0

    def flaky_insert(db, rid, state, reason, stuck, now):
        nonlocal calls
        calls += 1
        real_insert(db, rid, state, reason, stuck, now)
        if calls == 2:
            raise sqlite3.OperationalError("simulated disk I/O error mid-commit")

    reconciler._insert = flaky_insert
    with pytest.raises(sqlite3.OperationalError, match="mid-commit"):
        reconciler.reconcile()
    assert _journal(path) == [("tenant-a", "request-1", "applied", "recorded", 0)]

    reconciler._insert = real_insert
    assert _states(reconciler.reconcile()) == {
        "request-1": ("applied", "recorded", False),
        "request-2": ("applied", "recorded", False),
        "request-3": ("applied", "recorded", False),
    }
    assert len(_journal(path)) == 3


def test_tampered_stuck_column_is_caught_by_mac(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _unknown)
    engine = Engine(recon)
    _reconciler(recon, path, engine).reconcile()
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER action_outcome_reconciliation_no_update")
        db.execute("UPDATE action_outcome_reconciliation SET stuck = 1 WHERE request_id = 'request-1'")
    with pytest.raises(recon.ReconciliationRefused, match="journal_tampered"):
        _reconciler(recon, path, engine).reconcile()


def test_journal_shrinkage_on_same_instance_is_refused(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _applied)
    _admit(path, _request(2), _applied)
    engine = Engine(recon)
    reconciler = _reconciler(recon, path, engine)
    reconciler.reconcile()
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER action_outcome_reconciliation_no_delete")
        db.execute("DELETE FROM action_outcome_reconciliation WHERE sequence = 2")
    with pytest.raises(recon.ReconciliationRefused, match="journal_tampered"):
        reconciler.reconcile()


def test_integrity_error_in_commit_maps_to_journal_tampered(recon, tmp_path):
    path = tmp_path / "policy.sqlite3"
    _admit(path, _request(1), _applied)
    engine = Engine(recon)
    reconciler = _reconciler(recon, path, engine)
    reconciler.reconcile()
    # A valid-MAC unknown row appended after a terminal row hits the unique terminal index on commit.
    fields = ("tenant-a", "request-1", "unknown", "readback_pending", 0, NOW.isoformat())
    mac = reconciler._mac(2, fields)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO action_outcome_reconciliation VALUES (2, ?, ?, ?, ?, ?, ?, ?)", (*fields, mac))
    with pytest.raises(recon.ReconciliationRefused, match="journal_tampered"):
        reconciler.reconcile()
