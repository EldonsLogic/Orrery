import copy
import math
import pickle

import pytest

from featureflags import (EvalContext, FlagDef, FlagError, FlagEvaluator, Registry, bucket,
                          label, missing)

K = "ui.new_viewer"


def test_unknown_and_malformed_keys_are_off(w):
    c = w.ctx()
    for key in ("nope", "", None, 5, "UI.new_viewer", "ui.new_viewer\n", "a" * 100, ["x"], b"ui"):
        d = w.ev.evaluate(c, key)
        assert d.enabled is False and d.reason == "error.unknown_flag"


def test_default_applies_only_when_unset(w):
    c = w.ctx()
    assert w.ev.is_enabled(c, K) is False
    assert w.ev.evaluate(c, "ui.dark_default").reason == "default"
    assert w.ev.is_enabled(c, "ui.dark_default") is True
    w.admin.set_global(w.staff(), "ui.dark_default", False, "turn it off")
    w.clock.advance(100)  # past the cache ttl
    assert w.ev.is_enabled(w.ctx(), "ui.dark_default") is False


def test_context_only_from_verified_claims(w):
    for bad in ("t-a", {"tenant": "t-a"}, None, w.customer().tenant):
        with pytest.raises(FlagError):
            EvalContext.from_claims(bad, w.clock())
    with pytest.raises(FlagError):  # direct construction
        EvalContext(w.customer(), "t-a", "u-1")
    with pytest.raises(FlagError):  # forged tenant on a real claims object
        EvalContext(w.customer(), "t-b", "u-1")
    # evaluating with a non-context is OFF, not an error
    for bad in (None, "t-a", {"tenant_id": "t-a"}, object()):
        assert w.ev.evaluate(bad, K).reason == "error.context"


def test_context_copy_is_refused_or_still_verified(w):
    c = w.ctx()
    with pytest.raises(Exception):
        pickle.dumps(c.claims)
    with pytest.raises(Exception):
        copy.deepcopy(c.claims)


def test_expired_claims_fail_closed(w):
    w.admin.set_global(w.staff(), K, True, "roll out")
    c = w.ctx()
    assert w.ev.is_enabled(c, K) is True
    w.clock.advance(24 * 3600)
    d = w.ev.evaluate(c, K)
    assert d.enabled is False and d.reason == "error.context"


def test_hostile_ids_cannot_match(w):
    # a rule for t-a never matches look-alike ids; ids in tokens are checked
    w.admin.set_tenant(w.staff(), K, "t-a", True, "pilot tenant")
    assert w.ev.is_enabled(w.ctx(), K) is True
    assert w.ev.is_enabled(w.ctx("u-b", "t-b"), K) is False


def test_tenant_rule_user_rule_isolation(w):
    s = w.staff()
    w.admin.set_tenant(s, K, "t-a", True, "pilot tenant")
    w.admin.set_user(s, "ui.user_beta", "t-b", "u-b", True, "beta user")
    assert w.ev.is_enabled(w.ctx("u-1", "t-a"), K)
    assert not w.ev.is_enabled(w.ctx("u-b", "t-b"), K)
    assert w.ev.is_enabled(w.ctx("u-b", "t-b"), "ui.user_beta")
    # same user id in another tenant does not inherit
    assert not w.ev.is_enabled(w.ctx("u-1", "t-a"), "ui.user_beta")


def test_percentage_is_deterministic_and_monotone(w):
    units = [f"t-{i}" for i in range(2000)]
    a = {u for u in units if bucket(K, u) < 2500}
    b = {u for u in units if bucket(K, u) < 5000}
    assert a <= b and a == {u for u in units if bucket(K, u) < 2500}
    assert 0.2 < len(a) / len(units) < 0.3
    assert bucket(K, "t-1") != bucket("ui.other", "t-1") or bucket(K, "t-2") != bucket("ui.other", "t-2")
    assert all(bucket(K, u) < 10000 for u in units)


def test_percent_zero_and_full(w):
    s = w.staff()
    w.admin.set_percent(s, K, 10000, "everyone")
    w.clock.advance(100)
    assert w.ev.is_enabled(w.ctx(), K)
    w.admin.set_percent(s, K, 0, "nobody")
    w.clock.advance(100)
    assert not w.ev.is_enabled(w.ctx(), K)


def test_percent_by_user_differs_within_tenant(w):
    s = w.staff()
    w.admin.set_percent(s, "ui.user_beta", 5000, "half the users")
    hits = {u: bucket("ui.user_beta", f"t-a\x00{u}") < 5000 for u in ("u-1", "u-2")}
    w.clock.advance(100)
    for u, h in hits.items():
        assert w.ev.is_enabled(w.ctx(u, "t-a"), "ui.user_beta") is h


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, 0, True, None, "1900000000", 1.5e9])
def test_bad_clock_is_off(w, bad):
    w.admin.set_global(w.staff(), K, True, "roll out")
    c = w.ctx()
    ev = FlagEvaluator(w.registry, w.store, lambda: bad)
    d = ev.evaluate(c, K)
    assert d.enabled is False and d.reason == "error.clock"


def test_clock_going_backwards_fails_closed_and_clears_cache(w):
    w.admin.set_global(w.staff(), K, True, "roll out")
    c = w.ctx()
    assert w.ev.is_enabled(c, K)
    w.clock.t -= 5
    assert w.ev.evaluate(c, K).reason == "error.clock"
    assert w.ev._cache == {} or len(w.ev._cache) == 0
    w.clock.t += 10
    assert w.ev.is_enabled(c, K)


def test_store_outage_is_off_even_with_default_true(w):
    c = w.ctx()
    w.store.fail = True
    for key in (K, "ui.dark_default"):
        d = w.ev.evaluate(c, key)
        assert d.enabled is False and d.reason == "error.store"


def test_evaluator_never_raises_on_odd_registry_or_store(w):
    class Boom:
        def kill_state(self):
            raise RuntimeError("x")
    ev = FlagEvaluator(w.registry, Boom(), w.clock)
    assert ev.evaluate(w.ctx(), K).enabled is False


def test_cache_ttl_bounded_and_size_bounded(w):
    ev = FlagEvaluator(w.registry, w.store, w.clock, ttl=10**9, max_entries=10**9)
    assert ev.ttl == 60 and ev.max_entries == 1024
    ev = FlagEvaluator(w.registry, w.store, w.clock, ttl="x", max_entries=2)
    assert ev.ttl == 0
    ev = FlagEvaluator(w.registry, w.store, w.clock, ttl=30, max_entries=2)
    c = w.ctx()
    for k in ("ui.new_viewer", "ui.user_beta", "ui.dark_default"):
        ev.evaluate(c, k)
    assert len(ev._cache) == 2


def test_cache_staleness_is_bounded_by_ttl(w):
    c = w.ctx()
    assert not w.ev.is_enabled(c, K)  # caches OFF
    w.admin.set_global(w.staff(), K, True, "roll out")
    w.clock.advance(14)
    assert not w.ev.is_enabled(w.ctx(), K)  # still inside the ttl
    w.clock.advance(2)
    assert w.ev.is_enabled(w.ctx(), K)


def test_registry_rules():
    for bad in (FlagDef("Bad"), FlagDef("x", category="other"), FlagDef("x", default=1),
                FlagDef("pay.x", "money", default=True), FlagDef("x", percent_by="ip")):
        with pytest.raises(FlagError):
            Registry([bad])
    with pytest.raises(FlagError):
        Registry([FlagDef("dup"), FlagDef("dup")])
    with pytest.raises(FlagError):
        Registry(["not a def"])


def test_bilingual_labels():
    reg = Registry([FlagDef("ui.a")])
    en = {"flags.ui.a.label": "New viewer", "flags.ui.a.description": "d"}
    ar = {"flags.ui.a.label": "العارض الجديد"}
    assert missing(reg, {"en": en, "ar": ar}) == [("ar", "flags.ui.a.description")]
    assert missing(reg, {}) and len(missing(reg, {})) == 4
    assert label(reg, {"en": en, "ar": ar}, "ui.a", "ar") == "العارض الجديد"
    assert label(reg, {"en": en}, "ui.a", "ar") == "flags.ui.a.label"
    assert label(reg, {"en": en}, "nope", "en") == "nope"
