"""BPL-020: the sealed transition log, replay, apply outcomes, the host clock, labels."""
import copy
import re
from pathlib import Path

import pytest

import build_state
from build_state import BuildStateError, BuildStateMachine, label, label_keys, CODES
from bs_support import BP, KEYS, T, World, code, P


def stream(w):
    return w.m._log._logs[(T, BP)]


# ---------- sealed log ----------
def test_no_key_no_machine_and_no_sha256_fallback():
    for keys in ({}, None, {"k1": b"short"}, {"k1": "x" * 40}, {"k1": b"k" * 31}):
        assert code(World, keys=keys) == "BS-012"
    src = Path(build_state.__file__).parent
    text = "".join(p.read_text() for p in src.glob("*.py"))
    assert "hmac.new" in text
    w = World().to("owner_approved")
    w.m._log._keys.clear()
    assert code(w.m.status, T, BP) == "BS-011"
    assert code(w.review) == "BS-011"


def test_key_rotation_keeps_old_records_readable():
    w = World(keys=KEYS).to("owner_approved")
    w.m._log._active = "k2"
    w.review()
    ids = {r["key_id"] for r in stream(w)}
    assert ids == {"k1", "k2"} and w.state() == "team_reviewed"


@pytest.mark.parametrize("name,edit", [
    ("edit_data", lambda log: log[1]["body"]["data"].update(digest="f" * 64)),
    ("edit_actor", lambda log: log[1]["body"]["actor"].update(subject="u-evil")),
    ("edit_type", lambda log: log[1]["body"].update(type="revised")),
    ("edit_time", lambda log: log[1]["body"].update(at=log[1]["body"]["at"] + 5)),
    ("edit_tenant", lambda log: log[1].update(tenant_id="t_other")),
    ("edit_seq", lambda log: log[1].update(seq=9)),
    ("drop_middle", lambda log: log.pop(1)),
    ("swap", lambda log: log.__setitem__(slice(0, 2), [log[1], log[0]])),
    ("extra_key", lambda log: log[0].update(extra=1)),
    ("bad_seal", lambda log: log[0].update(seal="0" * 64)),
    ("non_dict", lambda log: log.__setitem__(0, "x")),
])
def test_tampered_log_fails_closed(name, edit):
    w = World().to("team_reviewed")
    edit(stream(w))
    assert code(w.m.status, T, BP) == "BS-011"
    assert code(w.sandbox) == "BS-011"
    assert w.m.verify_tenant(T) == [(BP, "BS-011")]


def test_cut_tail_deleted_stream_and_rolled_back_log_are_detected():
    w = World().to("simulated")
    full = copy.deepcopy(stream(w))
    stream(w).pop()                                        # cut tail: the sealed head and the manifest still say 5 records
    assert code(w.m.status, T, BP) == "BS-011"
    assert code(w.cutover) == "BS-011"                     # a cut tail can never lead to a promotion
    w.m._log._logs[(T, BP)] = full
    assert w.state() == "simulated"
    old_log, old_head = copy.deepcopy(full[:3]), copy.deepcopy(w.m._log._heads[(T, BP)])
    w.m._log._logs[(T, BP)] = old_log                      # rollback of the log and the head, manifest left alone
    w.m._log._heads[(T, BP)] = {**old_head}
    assert code(w.m.status, T, BP) == "BS-011"
    w.m._log._logs[(T, BP)] = full
    w.m._log._heads[(T, BP)] = old_head
    del w.m._log._logs[(T, BP)]                            # deleted log, head and manifest remain
    assert code(w.m.status, T, BP) == "BS-011"
    w.m._log._logs[(T, BP)] = full
    del w.m._log._heads[(T, BP)]
    assert code(w.m.status, T, BP) == "BS-011"
    w.m._log._heads[(T, BP)] = old_head
    assert w.state() == "simulated"
    del w.m._log._manifests[T]                             # the tenant manifest removed
    assert code(w.m.status, T, BP) == "BS-011"
    assert code(w.m.verify_tenant, T) == "BS-011"


def test_a_violating_record_with_a_valid_seal_is_still_refused():
    """A record sealed by the real key but breaking the rules (a gate by an agent, a skipped state) fails the fold."""
    w = World().to("draft")
    log = w.m._log
    forged = {"type": "team_reviewed", "at": 1_800_000_100, "actor": {"subject": "agent-1", "kind": "agent", "realm": "staff", "role": "team_reviewer"},
              "data": {"digest": w.status()["contentDigest"], "itemId": "item-1", "pinSeq": 1, "pinHead": "h", "reviewDigest": "a" * 64, "approvedBy": "x"}}
    log.append(T, BP, forged)                              # sealed fine, but a draft cannot jump to team_reviewed
    assert code(w.m.status, T, BP) == "BS-011"
    w2 = World().to("draft")
    w2.m._log.append(T, BP, {**forged, "type": "owner_approved", "data": {"digest": w2.status()["contentDigest"], "confirmations": ["gaps", "quote", "summary"]},
                             "actor": {"subject": "agent-1", "kind": "agent", "realm": "tenant", "role": "owner"}})
    assert code(w2.m.status, T, BP) == "BS-011"            # an agent owner-approval is not a promotion, even sealed


def test_replay_of_a_valid_record_into_another_tenant_or_blueprint():
    a = World().to("owner_approved")
    log = a.m._log
    rec = copy.deepcopy(stream(a)[1])
    for tenant, bp in (("t_other", BP), (T, "bp-other")):
        log._logs[(tenant, bp)] = [copy.deepcopy(stream(a)[0]), copy.deepcopy(rec)]
        log._heads[(tenant, bp)] = copy.deepcopy(log._heads[(T, BP)])
        assert code(a.m.status, tenant, bp) == "BS-011"
    # a record from one tenant's stream appended to another stream of the same log
    b = World().to("draft")
    b.m._log._logs[(T, BP)].append(copy.deepcopy(rec))
    assert code(b.m.status, T, BP) == "BS-011"


def test_two_blueprints_and_tenants_do_not_mix():
    w = World().to("owner_approved")
    w.bps.d[(T, "bp-two")] = {"meta": {"id": "bp-two", "revision": 3}}
    w.m.create("author", tenant_id=T, blueprint_id="bp-two")
    assert w.m.status(T, "bp-two")["state"] == "draft" and w.state() == "owner_approved"
    assert w.m.verify_tenant(T) == []
    assert code(w.m.verify_tenant, "t_empty") is None


# ---------- clock ----------
@pytest.mark.parametrize("v", [1.5e9, True, "1800000000", 5, -1, 10 ** 12])
def test_host_clock_must_be_a_sane_int(v):
    w = World()
    w.clock.value = v
    assert code(w.create) == "BS-002"


def test_clock_error_and_backwards_time():
    w = World().to("draft")
    def boom():
        raise RuntimeError
    w.m._clock = boom
    assert code(w.approve) == "BS-002"
    w.m._clock = lambda: 1_700_000_000      # earlier than the last record
    assert code(w.approve) == "BS-002"
    assert w.state() == "draft"


# ---------- apply ----------
def test_unknown_outcome_never_marks_live_and_blocks_everything_else():
    w = World().to("cutover"); w.sign()
    w.engine.script = ["unknown"]
    assert code(w.live) == "BS-010"
    s = w.status()
    assert s["state"] == "simulated" and s["pending"]["status"] == "unknown"
    assert code(w.live) == "BS-010"                                    # no second go-live while unknown
    assert code(lambda: w.m.roll_back("owner", **w.args(to_state="draft", reason="other"))) == "BS-010"
    assert code(w.cutover) is not None
    w.engine.status_script = ["unknown"]
    assert code(w.m.resolve_apply, "runner", **w.args()) == "BS-010"
    w.engine.status_script = [RuntimeError("down")]
    assert code(w.m.resolve_apply, "runner", **w.args()) == "BS-010"
    assert w.state() == "simulated"
    w.engine.status_script = ["confirmed"]
    assert w.m.resolve_apply("runner", **w.args())["state"] == "live"
    keys = {c[2] for c in w.engine.calls}
    assert len([c for c in w.engine.calls if c[1] == "live"]) == 1 and len(keys) == 2
    assert code(w.m.resolve_apply, "runner", **w.args()) == "BS-005"   # nothing pending any more


@pytest.mark.parametrize("answer", [RuntimeError("timeout"), None, True, 1, "ok", "CONFIRMED", ["confirmed"], {"outcome": "confirmed"}, ""])
def test_anything_but_confirmed_is_unknown(answer):
    w = World().to("simulated"); w.cutover(); w.sign()
    w.engine.script = [answer]
    assert code(w.live) == "BS-010"
    assert w.status()["pending"]["status"] == "unknown" and w.state() == "simulated"


def test_crash_after_apply_started_stays_applying():
    w = World().to("cutover"); w.sign()
    calls = {"n": 0}
    real = w.m._now
    def flaky():
        calls["n"] += 1
        if calls["n"] == 2:        # the clock fails when the outcome is about to be recorded
            raise BuildStateError("BS-002")
        return real()
    w.m._now = flaky
    err = code(w.live)
    w.m._now = real
    s = w.status()
    assert err == "BS-002" and s["state"] == "simulated" and s["pending"]["status"] == "applying"
    w.engine.status_script = ["confirmed"]
    assert w.m.resolve_apply("runner", **w.args())["state"] == "live"


def test_failed_apply_changes_nothing_and_retry_uses_a_new_key():
    w = World().to("simulated"); w.cutover(); w.sign()
    w.engine.script = ["failed", "confirmed"]
    assert code(w.live) == "BS-015"
    s = w.status()
    assert s["state"] == "simulated" and s["pending"] is None
    assert w.live()["state"] == "live"
    live = [c for c in w.engine.calls if c[1] == "live"]
    assert len(live) == 2 and live[0][2] != live[1][2] and live[0][3] == live[1][3]


def test_failed_sandbox_stays_team_reviewed():
    w = World().to("team_reviewed")
    w.engine.script = [RuntimeError("x")]
    assert code(w.sandbox) == "BS-010"
    assert w.state() == "team_reviewed" and code(w.sandbox) == "BS-010"
    w.engine.status_script = ["failed"]
    assert code(w.m.resolve_apply, "runner", **w.args()) == "BS-015"
    assert w.status()["pending"] is None
    assert w.sandbox()["state"] == "built_in_sandbox"


def test_idempotency_key_is_bound_to_tenant_blueprint_kind_digest_attempt():
    k = build_state.idempotency_key
    base = k(T, BP, "live", "a" * 64, 1)
    assert len({base, k("t2", BP, "live", "a" * 64, 1), k(T, "bp2", "live", "a" * 64, 1), k(T, BP, "sandbox", "a" * 64, 1),
                k(T, BP, "live", "b" * 64, 1), k(T, BP, "live", "a" * 64, 2)}) == 6


def test_only_humans_start_live_but_an_agent_cannot_resolve_without_a_pending_apply():
    w = World().to("cutover"); w.sign()
    assert code(w.m.resolve_apply, "agent", **w.args()) == "BS-005"   # it cannot promote
    w.engine.status_script = ["confirmed"]
    assert w.state() == "simulated"
    assert code(w.m.resolve_apply, "author", **w.args()) == "BS-003"


# ---------- labels, names, audit ----------
def test_labels_both_languages_and_no_engine_name():
    for lang in ("en", "ar"):
        assert all(k in build_state._LABELS[lang] and build_state._LABELS[lang][k].strip() for k in label_keys())
    assert set(build_state._LABELS["en"]) == set(build_state._LABELS["ar"]) == label_keys()
    assert all(re.search("[؀-ۿ]", build_state._LABELS["ar"][k]) for k in label_keys())
    assert label("bs.state.live", "en") == "Live"
    s = World().to("draft").status()
    assert s["stateKey"] in label_keys() and all(k in label_keys() for k in (s["stateKey"],))
    root = Path(build_state.__file__).parent
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in (".py", ".json") and p.parent.name != "tests":
            assert not re.search(r"frappe|erpnext", p.read_text(), re.I), p
    assert set(CODES) == {f"BS-{i:03d}" for i in range(1, 18)}


def test_audit_records_allow_and_deny_without_content_and_a_broken_audit_does_not_allow():
    w = World()
    w.create()
    assert code(w.approve, "agent") == "BS-003"
    assert [a["code"] for a in w.audit] == ["OK", "BS-003"]
    def boom(_):
        raise RuntimeError
    w.m._audit_cb = boom
    assert code(w.approve, "agent") == "BS-003"
    assert w.state() == "draft"


def test_status_pending_labels():
    w = World().to("simulated"); w.cutover(); w.sign()
    w.engine.script = ["unknown"]
    code(w.live)
    p = w.status()["pending"]
    assert p["kindKey"] in label_keys() and p["statusKey"] in label_keys()
