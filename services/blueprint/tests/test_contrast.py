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


def test_known_good_colour_passes_in_its_theme():
    # No colour reaches 4.5:1 on both a near-white and a near-black surface, so each theme is judged
    # separately and the other theme gets its own derived colour (theming.md). Cobalt (light) and its
    # dark counterpart must each pass in their own theme without any adjustment there.
    light = validate(_with(primary="#2443D0"), full_ctx())
    assert light.ok
    assert not [a for a in light.adjustments if a["theme"] == "light" and a["path"].endswith("primaryColour")]
    dark = validate(_with(primary="#86A0FF"), full_ctx())
    assert dark.ok
    assert not [a for a in dark.adjustments if a["theme"] == "dark" and a["path"].endswith("primaryColour")]


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
    rep = validate(_with(primary="#1F5FAE"), full_ctx())  # fails 4.5:1 on the dark theme
    assert rep.ok
    adj = [a for a in rep.adjustments if a["theme"] == "dark" and a["path"].endswith("primaryColour")]
    assert adj and passes_all(adj[0]["proposed"], list(SURFACES["dark"].values()), 4.5)
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
    rep = validate(_with(primary=colour), full_ctx())
    assert [a for a in rep.adjustments if a["theme"] == "light" and a["path"].endswith("primaryColour")]
