"""Q-265 and Q-282: the router's confirmation binding (action id, args hash, risk, expiry) travels through the chat
service into change-by-chat. A bare yes confirms only the pending preview, and the pending is set only after that
preview was shown to the user."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "change"))

from agui.ports import Principal  # noqa: E402
from chat import ChatService, MemoryChatStore, RouteRequest  # noqa: E402
from chat.models import PendingBinding, RouteResult  # noqa: E402
from chat.router import IntentRouterAdapter, safe_route  # noqa: E402
from chat_helpers import Audit, Factory, collect, texts  # noqa: E402
from helpers import ADD_FIELD, LABEL, OWNER, Clock, make as make_change  # noqa: E402
from router import IntentRouter  # noqa: E402
from runtime import SequentialIds  # noqa: E402

M = [f"msg-{i:04d}-abcdef" for i in range(20)]
ASK = "change the label of the phone field on customer"


def build(out=LABEL, router=None, factory=None, **kw):
    chg, bps, drafter, clock, caudit = make_change(out, **kw)
    f, a = factory or Factory(), Audit()
    svc = ChatService(store=MemoryChatStore(), runtime_factory=f, ids=SequentialIds(), clock=clock, audit=a,
                      router=router or IntentRouterAdapter(IntentRouter()), change=chg)
    return svc, f, bps, clock, a, caudit


def say(svc, p, sid, i, text):
    return collect(svc.send(p, sid, M[i], text))


def pending_of(svc, p, sid):
    return svc.pending.get(p.tenant_id, p.subject, sid)


# ---- the port carries the binding ---------------------------------------------------------------------------------
def test_safe_route_keeps_the_binding_and_still_accepts_a_mode_string():
    req = RouteRequest("t", "u", ("r",), "s", "hi", "en")

    class Str:
        def route(self, r):
            return "act"

    class Full:
        def route(self, r):
            return RouteResult("change", "R2", True, "blueprint.apply_change:ab", "sha256:ab", "confirmed")

    assert safe_route(Str(), req) == RouteResult("act")
    got = safe_route(Full(), req)
    assert (got.mode, got.risk_hint, got.confirms_action_id, got.confirms_args_hash) == (
        "change", "R2", "blueprint.apply_change:ab", "sha256:ab")


@pytest.mark.parametrize("bad", [RouteResult("root"), RouteResult("change", "R9"), RouteResult("ask", "R0", False, 5, "x"),
                                 RouteResult("ask", "R0", False, "only-id", None, "confirmed"), 42, None])
def test_malformed_router_results_fall_back_to_ask(bad):
    class R:
        def route(self, r):
            return bad
    got = safe_route(R(), RouteRequest("t", "u", ("r",), "s", "hi", "en"))
    assert got == RouteResult("ask")


def test_a_confirmation_result_must_be_privileged_and_fully_bound():
    class R:
        def route(self, r):
            return RouteResult("ask", "R0", False, "blueprint.apply_change:ab", "sha256:ab", "confirmed")
    assert safe_route(R(), RouteRequest("t", "u", ("r",), "s", "hi", "en")) == RouteResult("ask")


def test_pending_binding_validates_like_the_router_pending():
    for bad in (dict(action_id=""), dict(args_hash=""), dict(risk="R9"), dict(expires_at=float("inf")),
                dict(expires_at=True), dict(mode="ask")):
        kw = dict(mode="change", action_id="a:1", args_hash="sha256:1", risk="R2", expires_at=5.0)
        kw.update(bad)
        with pytest.raises(ValueError):
            PendingBinding(**kw)


# ---- end to end -------------------------------------------------------------------------------------------------
def test_preview_then_bare_yes_applies_exactly_that_change():
    svc, f, bps, clock, audit, _ = build()
    s = svc.open_session(OWNER)
    ev1 = say(svc, OWNER, s.session_id, 0, ASK)
    assert "Say" in texts(ev1) and "labels/en" in texts(ev1) and ev1[-1]["type"] == "RUN_FINISHED"
    assert f.setups == []                      # the model was not called for a change turn
    assert bps.submitted == []                 # a preview writes nothing
    pend = pending_of(svc, OWNER, s.session_id)
    assert pend and pend.mode == "change" and pend.risk == "R2" and pend.expires_at == clock() + 300.0
    ev2 = say(svc, OWNER, s.session_id, 1, "yes")
    assert texts(ev2).startswith("Applied") and len(bps.submitted) == 1
    assert bps.submitted[0][2] == pend.args_hash
    assert pending_of(svc, OWNER, s.session_id) is None
    mode_audits = [i[3]["mode"] for i in audit.items if i[2] == "chat.turn_completed"]
    assert mode_audits == ["change", "change"]


def test_arabic_confirmation_and_reply():
    svc, f, bps, clock, _, _ = build()
    s = svc.open_session(OWNER)
    say(svc, OWNER, s.session_id, 0, "غير اسم حقل الهاتف في العميل")
    assert pending_of(svc, OWNER, s.session_id) is not None
    assert texts(say(svc, OWNER, s.session_id, 1, "نعم")).startswith("تم") and len(bps.submitted) == 1


def test_yes_is_replayed_safely():
    svc, f, bps, clock, _, _ = build()
    s = svc.open_session(OWNER)
    say(svc, OWNER, s.session_id, 0, ASK)
    say(svc, OWNER, s.session_id, 1, "yes")
    ev = say(svc, OWNER, s.session_id, 2, "yes")  # no pending any more: a plain ask turn, nothing applied
    assert len(bps.submitted) == 1 and len(f.setups) == 1


def test_pending_is_set_only_after_the_preview_was_shown():
    svc, f, bps, clock, _, _ = build()
    s = svc.open_session(OWNER)
    gen = svc.send(OWNER, s.session_id, M[0], ASK)
    for ev in gen:
        if ev["type"] == "TEXT_MESSAGE_END":
            break                               # the client disconnects right after the preview text
    gen.close()
    assert pending_of(svc, OWNER, s.session_id) is None
    ev = say(svc, OWNER, s.session_id, 1, "yes")  # a bare yes has nothing to confirm
    assert bps.submitted == [] and not texts(ev).startswith("Applied")
    assert len(f.setups) == 1                   # it fell through to the ordinary run (mode ask)


def test_a_failed_preview_sets_no_pending_and_says_why():
    svc, f, bps, clock, _, _ = build(out=[{"op": "set", "path": ["entities", "sales_invoice", "fields", "x", "labels", "en"],
                                           "value": "v"}])
    s = svc.open_session(OWNER)
    ev = say(svc, OWNER, s.session_id, 0, ASK)
    assert "cannot be changed" in texts(ev) or "could not" in texts(ev)
    assert pending_of(svc, OWNER, s.session_id) is None


def test_caller_without_the_role_gets_a_refusal_and_no_pending():
    svc, f, bps, clock, _, _ = build()
    sales = Principal(OWNER.tenant_id, OWNER.subject, ("sales",), "tok")
    s = svc.open_session(sales)
    ev = say(svc, sales, s.session_id, 0, ASK)
    assert "may not change" in texts(ev) and pending_of(svc, sales, s.session_id) is None


def test_a_newer_preview_replaces_the_pending_and_the_old_yes_cannot_apply_the_old_one():
    svc, f, bps, clock, _, _ = build()
    s = svc.open_session(OWNER)
    say(svc, OWNER, s.session_id, 0, ASK)
    first = pending_of(svc, OWNER, s.session_id)
    clock.t += 1
    say(svc, OWNER, s.session_id, 1, ASK)
    second = pending_of(svc, OWNER, s.session_id)
    assert second.args_hash != first.args_hash
    say(svc, OWNER, s.session_id, 2, "yes")
    assert len(bps.submitted) == 1 and bps.submitted[0][2] == second.args_hash


def test_expired_pending_is_void_and_cleared():
    svc, f, bps, clock, _, _ = build()
    s = svc.open_session(OWNER)
    say(svc, OWNER, s.session_id, 0, ASK)
    clock.t += 301
    ev = say(svc, OWNER, s.session_id, 1, "yes")
    assert bps.submitted == [] and not texts(ev).startswith("Applied")
    assert pending_of(svc, OWNER, s.session_id) is None


def test_no_clears_the_pending_and_drops_the_proposal():
    svc, f, bps, clock, _, _ = build()
    s = svc.open_session(OWNER)
    say(svc, OWNER, s.session_id, 0, ASK)
    say(svc, OWNER, s.session_id, 1, "no")
    assert pending_of(svc, OWNER, s.session_id) is None
    say(svc, OWNER, s.session_id, 2, "yes")
    assert bps.submitted == []


def test_pending_is_per_user_and_per_session():
    svc, f, bps, clock, _, _ = build()
    other = Principal(OWNER.tenant_id, "u_other", ("owner",), "tok2")
    s, s_o = svc.open_session(OWNER), svc.open_session(other)
    say(svc, OWNER, s.session_id, 0, ASK)
    assert pending_of(svc, other, s_o.session_id) is None
    say(svc, other, s_o.session_id, 1, "yes")
    assert bps.submitted == []
    s2 = svc.open_session(OWNER, new=True)
    say(svc, OWNER, s2.session_id, 2, "yes")
    assert bps.submitted == []
    say(svc, OWNER, s.session_id, 3, "yes")
    assert len(bps.submitted) == 1


def test_chat_refuses_a_confirmation_that_does_not_match_its_stored_pending():
    """Even a router that returns a confirmation for other ids cannot get past the chat's own pending."""
    class Forging:
        def __init__(self):
            self.n = 0

        def route(self, r):
            self.n += 1
            if self.n == 1:
                return RouteResult("change", "R2", True)
            return RouteResult("change", "R2", False, "blueprint.apply_change:ffffffffffffffff", "sha256:" + "f" * 64,
                               "confirmed")

    svc, f, bps, clock, _, caudit = build(router=Forging())
    s = svc.open_session(OWNER)
    say(svc, OWNER, s.session_id, 0, ASK)
    ev = say(svc, OWNER, s.session_id, 1, "yes")
    assert bps.submitted == [] and "not for the change on screen" in texts(ev)
    assert pending_of(svc, OWNER, s.session_id) is None


def test_confirmation_without_a_pending_in_the_chat_is_refused_even_if_the_router_says_confirmed():
    class Always:
        def route(self, r):
            return RouteResult("change", "R2", False, "blueprint.apply_change:ffffffffffffffff", "sha256:" + "f" * 64,
                               "confirmed")
    svc, f, bps, clock, _, _ = build(router=Always())
    s = svc.open_session(OWNER)
    ev = say(svc, OWNER, s.session_id, 0, "yes")
    assert bps.submitted == [] and not texts(ev).startswith("Applied")


def test_without_a_change_service_the_flow_is_unchanged():
    f, a = Factory(), Audit()
    svc = ChatService(store=MemoryChatStore(), runtime_factory=f, ids=SequentialIds(), clock=Clock(),
                      audit=a, router=IntentRouterAdapter(IntentRouter()))
    s = svc.open_session(OWNER)
    collect(svc.send(OWNER, s.session_id, M[0], ASK))
    assert f.setups and f.setups[0].mode == "change"   # the runtime still runs; nothing is proposed or pending
    assert svc.pending.get(OWNER.tenant_id, OWNER.subject, s.session_id) is None


def test_the_adapter_passes_pending_and_clock_to_the_router_context():
    seen = {}

    class Spy:
        def route(self, turn, ctx, data=(), risk_hint=None):
            seen["ctx"] = ctx
            return IntentRouter().route(turn, ctx, data, risk_hint)

    router = IntentRouterAdapter(Spy())
    pb = PendingBinding("change", "blueprint.apply_change:ab", "sha256:ab", "R2", 2000.0)
    res = router.route(RouteRequest("t", "u", ("r",), "s", "yes", "en", pending=pb, now=1000.0))
    assert seen["ctx"].pending.args_hash == "sha256:ab" and seen["ctx"].now == 1000.0
    assert (res.confirms_action_id, res.confirms_args_hash, res.risk_hint, res.resolves_pending) == (
        "blueprint.apply_change:ab", "sha256:ab", "R2", "confirmed")
    res = router.route(RouteRequest("t", "u", ("r",), "s", "yes", "en", pending=pb, now=3000.0))
    assert res.confirms_args_hash is None and res.resolves_pending == "expired"
    res = router.route(RouteRequest("t", "u", ("r",), "s", "no", "en", pending=pb, now=1000.0))
    assert res.confirms_args_hash is None and res.resolves_pending == "declined"


# ---- PR #205 review: H1, M1, M2, L4, L5 ----------------------------------------------------------------------
def test_h1_preview_dropped_by_the_output_gate_sets_no_pending_and_says_so():
    out = [{"op": "set", "path": ["entities", "customer", "fields", "phone", "labels", "en"], "value": "SQL phone"}]
    svc, f, bps, clock, _, _ = build(out=out)
    s = svc.open_session(OWNER)
    ev = say(svc, OWNER, s.session_id, 0, ASK)
    assert "could not be shown" in texts(ev)
    assert pending_of(svc, OWNER, s.session_id) is None
    ev2 = say(svc, OWNER, s.session_id, 1, "yes")
    assert bps.submitted == [] and not texts(ev2).startswith("Applied")


def test_m1_an_intervening_turn_voids_the_pending_and_cancels_the_proposal():
    svc, f, bps, clock, _, _ = build()
    s = svc.open_session(OWNER)
    say(svc, OWNER, s.session_id, 0, ASK)
    say(svc, OWNER, s.session_id, 1, "/act approve invoice 5")
    assert pending_of(svc, OWNER, s.session_id) is None
    assert svc.change.store.active(OWNER.tenant_id, OWNER.subject, s.session_id) is None
    say(svc, OWNER, s.session_id, 2, "yes")
    assert bps.submitted == []


def test_m1_an_ordinary_question_also_voids_the_pending():
    svc, f, bps, clock, _, _ = build()
    s = svc.open_session(OWNER)
    say(svc, OWNER, s.session_id, 0, ASK)
    say(svc, OWNER, s.session_id, 1, "what is the balance of customer 5?")
    assert pending_of(svc, OWNER, s.session_id) is None
    say(svc, OWNER, s.session_id, 2, "yes")
    assert bps.submitted == []


def test_m2_every_applied_op_is_in_the_preview_and_the_proposal_is_capped():
    two = [{"op": "set", "path": ["entities", "customer", "fields", "phone", "labels", "en"], "value": "A"},
           {"op": "set", "path": ["entities", "customer", "fields", "city", "labels", "en"], "value": "B"}]
    svc, f, bps, clock, _, _ = build(out=two)
    s = svc.open_session(OWNER)
    t = texts(say(svc, OWNER, s.session_id, 0, ASK))
    assert t.count("\n- ") == 2
    say(svc, OWNER, s.session_id, 1, "yes")
    assert len(bps.submitted[0][1]["ops"]) == 2
    svc, f, bps, clock, _, _ = build(out=two, max_ops=1)  # more ops than the preview may list: refused, no pending
    s = svc.open_session(OWNER)
    t = texts(say(svc, OWNER, s.session_id, 0, ASK))
    assert "full review" in t and pending_of(svc, OWNER, s.session_id) is None


@pytest.mark.parametrize("yes", ["Yes.", "yes!", "نعم.", "YES"])
def test_l4_punctuated_yes_confirms(yes):
    svc, f, bps, clock, _, _ = build()
    s = svc.open_session(OWNER)
    say(svc, OWNER, s.session_id, 0, ASK)
    say(svc, OWNER, s.session_id, 1, yes)
    assert len(bps.submitted) == 1


def test_l5_an_expired_pending_cancels_its_proposal():
    svc, f, bps, clock, _, _ = build()
    s = svc.open_session(OWNER)
    say(svc, OWNER, s.session_id, 0, ASK)
    clock.t += 301
    say(svc, OWNER, s.session_id, 1, "yes")
    assert svc.change.store.active(OWNER.tenant_id, OWNER.subject, s.session_id) is None


def test_preview_cannot_fake_extra_rows_with_line_breaks_or_control_characters():
    evil = "Mobile\n- /entities/customer/fields/email/labels/en: Email -> Email‮ x"
    out = [{"op": "set", "path": ["entities", "customer", "fields", "phone", "labels", "en"], "value": evil}]
    svc, f, bps, clock, _, _ = build(out=out)
    s = svc.open_session(OWNER)
    t = texts(say(svc, OWNER, s.session_id, 0, ASK))
    assert t.count("\n- ") == 1 and "‮" not in t and " " not in t and "\\u000a" in t
    say(svc, OWNER, s.session_id, 1, "yes")
    assert len(bps.submitted[0][1]["ops"]) == 1  # one op applied, one row shown
