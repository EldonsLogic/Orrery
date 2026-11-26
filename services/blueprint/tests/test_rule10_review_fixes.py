"""BPL-038 review fixes: rule 10 hex strictness matches the resolver, and BP-BRAND-002 reports the pair that really failed."""
import colorsys

import pytest

from fixture_registry import load_example
from test_example import full_ctx
from validator import validate
from validator.colour import HEX_RE


def _validate(primary="#2443D0", accent=None):
    bp = load_example()
    bp["branding"]["primaryColour"] = primary
    bp["branding"].pop("accentColour", None)
    if accent is not None:
        bp["branding"]["accentColour"] = accent
    return validate(bp, full_ctx())


@pytest.mark.parametrize("bad", ["#2443D0\n", "#2443D0 ", "2443D0", "#2443D", "#2443D0FF", "", 5])
def test_invalid_accent_is_brand_error(bad):
    rep = _validate(accent=bad)
    assert any(e.code == "BP-BRAND-001" and e.path == "/branding/accentColour" for e in rep.errors), [str(e) for e in rep.errors]


@pytest.mark.parametrize("bad", ["#2443D0\n", "#2443D0 ", "#2443D0\r\n"])
def test_invalid_primary_never_validates(bad):
    assert not _validate(primary=bad).ok


def test_hex_re_is_full_match():
    assert HEX_RE.fullmatch("#2443D0") and not HEX_RE.fullmatch("#2443D0\n")


def _grid():
    out = []
    for h in range(0, 360, 20):
        for s, l in ((0.9, 0.5), (0.7, 0.4), (0.8, 0.6), (0.6, 0.65), (0.9, 0.7)):
            r, g, b = colorsys.hls_to_rgb(h / 360, l, s)
            out.append("#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255)))
    return sorted(set(out + ["#0F766E", "#8F8F24", "#2443D0"]))


def test_brand_002_reports_failing_pair_for_0f766e():
    rep = _validate(primary="#0F766E")
    adj = [a for a in rep.adjustments if a["path"] == "/branding/primaryColour"]
    assert adj, "expected a light-theme adjustment"
    a = adj[0]
    assert a["pair"] == "secondary-pressed/background"
    assert a["ratioBefore"] < 4.5 <= a["ratioAfter"]
    assert round(a["ratioBefore"], 2) == 4.11  # the pair the review named; the old code reported 4.97 (surface only)
    w = [w for w in rep.warnings if w.code == "BP-BRAND-002"]
    assert w and "secondary-pressed/background" in str(w[0])


@pytest.mark.parametrize("primary", _grid())
def test_brand_002_invariant_primary(primary):
    rep = _validate(primary=primary)
    for a in rep.adjustments:
        assert a["pair"]
        assert a["ratioBefore"] < a["threshold"] <= a["ratioAfter"], (primary, a)


@pytest.mark.parametrize("accent", _grid()[::2])
def test_brand_002_invariant_accent(accent):
    rep = _validate(accent=accent)
    for a in rep.adjustments:
        assert a["pair"]
        assert a["ratioBefore"] < a["threshold"] <= a["ratioAfter"], (accent, a)
