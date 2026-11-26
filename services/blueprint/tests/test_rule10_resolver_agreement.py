"""BPL-038 (Q-64): validator rule 10 and the token resolver must agree. A Blueprint that validates is never refused by the resolver."""
import colorsys

import pytest

from fixture_registry import REPO, load_example
from test_example import full_ctx
from tokens import layer_from_css, resolve_tokens
from validator import validate


_T = REPO / "docs" / "brand" / "tokens"
_BASE = layer_from_css((_T / "tokens.css").read_text(encoding="utf-8"))
_PRODUCT = layer_from_css((_T / "tokens.proposed.css").read_text(encoding="utf-8"))


def _grid():
    out = []
    for h in range(0, 360, 30):
        for s, l in ((0.9, 0.5), (0.6, 0.35), (0.7, 0.75), (0.05, 0.5), (1.0, 0.92), (0.8, 0.12)):
            r, g, b = colorsys.hls_to_rgb(h / 360, l, s)
            out.append("#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255)))
    return sorted(set(out + ["#FFFFFF", "#000000", "#FFFF00", "#2443D0", "#1F5FAE", "#E0552C", "#86A0FF"]))


def _verdicts(primary, accent):
    bp = load_example()
    bp["branding"]["primaryColour"] = primary
    bp["branding"].pop("accentColour", None)
    if accent:
        bp["branding"]["accentColour"] = accent
    rep = validate(bp, full_ctx())
    rule10_ok = not [e for e in rep.errors if e.code.startswith("BP-BRAND-")]
    b = {"primaryColour": primary}
    if accent:
        b["accentColour"] = accent
    return rule10_ok, resolve_tokens(_BASE, _PRODUCT, b, None, algo_version=1, tenant_slug="acme").ok


@pytest.mark.parametrize("primary", _grid())
def test_primary_verdict_matches_resolver(primary):
    rule10_ok, resolver_ok = _verdicts(primary, None)
    assert rule10_ok == resolver_ok, primary


@pytest.mark.parametrize("accent", _grid()[::3])
def test_accent_verdict_matches_resolver(accent):
    rule10_ok, resolver_ok = _verdicts("#2443D0", accent)
    assert rule10_ok == resolver_ok, accent


_ODD = ["#2443D0\n", "#2443D0 ", "2443D0", "#2443D", "#2443D0FF", ""]


@pytest.mark.parametrize("accent", _ODD)
def test_malformed_accent_verdict_matches_resolver(accent):
    rule10_ok, resolver_ok = _verdicts("#2443D0", accent if accent else None) if accent else (True, True)
    if accent:
        assert rule10_ok == resolver_ok is False, repr(accent)


@pytest.mark.parametrize("primary", [x for x in _ODD if x.startswith("#2443D0") or x == "#2443D0\n"])
def test_malformed_primary_never_validates_while_resolver_refuses(primary):
    bp = load_example()
    bp["branding"]["primaryColour"] = primary
    bp["branding"].pop("accentColour", None)
    assert not validate(bp, full_ctx()).ok
    assert not resolve_tokens(_BASE, _PRODUCT, {"primaryColour": primary}, None, algo_version=1, tenant_slug="acme").ok
