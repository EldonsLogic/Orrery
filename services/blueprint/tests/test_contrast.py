import copy

from fixture_registry import load_example
from test_example import full_ctx
from validator import validate
from validator.colour import contrast, passes_all
from validator.theme_surfaces import SURFACES


def _with(primary=None, accent=None):
    bp = load_example()
    if primary:
        bp["branding"]["primaryColour"] = primary
    if accent:
        bp["branding"]["accentColour"] = accent
    return bp


def test_known_good_colour_passes_without_adjustment():
    # Rule 10 calls the token resolver's OKLCH derive (Q-64): one primary yields both themes, so a colour
    # that already reaches AA in the light theme (Cobalt) passes with no warning at all.
    rep = validate(_with(primary="#2443D0"), full_ctx())
    assert rep.ok
    assert not [a for a in rep.adjustments if a["path"].endswith("primaryColour")]


def test_contrast_values_are_wcag():
    assert round(contrast("#000000", "#FFFFFF"), 2) == 21.0
    assert round(contrast("#FFFFFF", "#FFFFFF"), 2) == 1.0


def test_light_yellow_is_adjusted_or_rejected_and_adjustment_passes():
    rep = validate(_with(primary="#FFFF00"), full_ctx())
    light = [a for a in rep.adjustments if a["theme"] == "light" and a["path"].endswith("primaryColour")]
    rejected = [e for e in rep.errors if e.code == "BP-BRAND-001"]
    assert light or rejected
    for a in light:
        bgs = list(SURFACES["light"].values())
        assert passes_all(a["proposed"], bgs, 4.5)
        assert a["proposed"] != a["original"]
    # yellow is fine on the dark theme
    assert not [a for a in rep.adjustments if a["theme"] == "dark"]


def test_auto_adjust_yields_warning_not_error():
    rep = validate(_with(primary="#8F8F24", accent="#2443D0"), full_ctx())  # too light for AA on the light theme; the derive darkens it
    assert rep.ok
    adj = [a for a in rep.adjustments if a["theme"] == "light" and a["path"].endswith("primaryColour")]
    assert adj and passes_all(adj[0]["proposed"], list(SURFACES["light"].values()), 4.5)
    assert adj[0]["ratioAfter"] >= 4.5 > adj[0]["ratioBefore"]


def test_white_is_rejected_in_light_theme():
    rep = validate(_with(primary="#FFFFFF"), full_ctx())
    assert any(e.code == "BP-BRAND-001" for e in rep.errors)
    assert not rep.ok


def test_accent_uses_the_lower_graphics_threshold():
    # 3.47:1 on the light background: fine as an accent (3:1), would fail as a text colour (4.5:1)
    colour = "#E0552C"
    assert 3.0 <= contrast(colour, SURFACES["light"]["background"]) < 4.5
    rep = validate(_with(accent=colour), full_ctx())
    assert not [a for a in rep.adjustments if a["theme"] == "light" and a["path"].endswith("accentColour")]
    # as a primary the derive refuses it (too close to Seshna Crimson), the same verdict the resolver gives
    rep = validate(_with(primary=colour), full_ctx())
    assert any(e.code == "BP-BRAND-001" and e.path.endswith("primaryColour") for e in rep.errors)
