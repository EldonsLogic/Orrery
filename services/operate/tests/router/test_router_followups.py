"""Follow-ups to the PR #194 re-review (N1 to N5): reads are not role grants, bad clocks fail closed, Arabic grants,
slash commands keep the ambiguous-reference check."""
import math

import pytest

from router import IntentRouter, Pending, RouteContext


def route(text, ctx=RouteContext(), clf=None):
    return IntentRouter(clf).route(text, ctx)


# -- N1 ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["Give me the list of roles", "Make a report of every admin",
                                  "Give me a summary of the permissions"])
def test_role_reads_do_not_route_to_change(text):
    d = route(text)
    assert d.mode != "change" and not d.requires_confirmation


def test_set_owner_of_a_record_is_not_a_role_grant():
    d = route("Set the owner of invoice 5 to Ahmed")
    assert d.mode == "act"


@pytest.mark.parametrize("text", ["Give Ahmed the admin role", "Grant Sara permissions on payroll",
                                  "Make Omar an administrator"])
def test_english_grants_still_route_to_change_r3(text):
    d = route(text)
    assert d.mode == "change" and d.risk_hint == "R3" and d.requires_confirmation


# -- N4 ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["اعطِ أحمد صلاحية المدير", "امنح سارة دور مدير", "اجعل عمر مديرا"])
def test_arabic_role_grants_route_to_change_r3(text):
    d = route(text)
    assert d.mode == "change" and d.risk_hint == "R3" and d.requires_confirmation


def test_arabic_read_of_roles_is_not_a_grant():
    assert route("اعرض لي قائمة الادوار").mode != "change"


# -- N2, N3 -----------------------------------------------------------------------------------------------------
def _pending():
    return Pending("change", "blueprint.apply_change:abc", "sha256:abc", "R2", 2000.0)


@pytest.mark.parametrize("now", ["5", True, None, math.nan, math.inf, object(), [1]])
def test_bad_clock_fails_closed_without_raising(now):
    d = route("yes", RouteContext(pending=_pending(), now=now))
    assert d.abstain and d.mode == "ask" and "pending_expired" in d.reasons and d.confirms_args_hash is None


@pytest.mark.parametrize("exp", [math.inf, -math.inf, math.nan, True, "9", None])
def test_pending_needs_a_finite_numeric_expiry(exp):
    with pytest.raises(ValueError):
        Pending("change", "a:1", "sha256:abc", "R2", exp)


# -- N5 ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["/act cancel the invoice", "/change delete the customer"])
def test_slash_commands_keep_the_ambiguous_reference_check(text):
    d = route(text)
    assert d.abstain and d.mode == "ask" and "ambiguous_reference" in d.reasons


def test_slash_command_with_a_reference_still_works():
    d = route("/act cancel invoice INV-0399")
    assert d.mode == "act" and d.explicit_command


# ---- PR #205 review: L3, L4 -----------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["اعطني صلاحية المدير", "امنحه دور المدير", "Set Ahmed as admin"])
def test_attached_pronoun_and_as_admin_grants_are_r3_change(text):
    d = route(text)
    assert d.mode == "change" and d.risk_hint == "R3"


def test_asking_for_a_list_of_roles_in_arabic_is_not_a_grant():
    assert route("اعطني قائمة الادوار").mode != "change"


@pytest.mark.parametrize("yes", ["Yes.", "yes!", "نعم.", "نعم،"])
def test_punctuated_yes_confirms_a_pending(yes):
    d = route(yes, RouteContext(pending=_pending(), now=1000.0))
    assert d.confirms_args_hash == "sha256:abc"
