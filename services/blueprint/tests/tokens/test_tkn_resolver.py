import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tkn_helpers import aa_failures
from tokens import TENANT_TOKENS, layer_from_css, merge, resolve_tokens
from tokens import codes as C

COBALT = {"primaryColour": "#2443D0"}
GOOD = {"primaryColour": "#0F8A7E", "accentColour": "#B8741A"}
SAMPLE_PRIMARIES = ["#2443D0", "#0F766E", "#9333EA", "#0F8A7E", "#B45309", "#7C3AED", "#0369A1", "#15803D", "#4F46E5", "#0EA5E9", "#14B8A6", "#FFD400"]


def codes(res, severity=None):
    return sorted(f.code for f in res.findings if severity is None or f.severity == severity)


# ---------- determinism and the no-branding case ----------
def test_deterministic_repeat(run):
    a, b = run(GOOD, "dark"), run(GOOD, "dark")
    assert a == b and a.to_json() == b.to_json() and a.css == b.css


def test_deterministic_input_order(base, product):
    """Reordering dict keys in every input must not change one byte of output."""
    br = {"accentColour": "#B8741A", "primaryColour": "#0F8A7E", "displayName": {"en": "A", "ar": "ب"}}
    br2 = dict(reversed(list(br.items())))
    rev = lambda L: {k: dict(reversed(list(v.items()))) for k, v in reversed(list(L.items()))}
    a = resolve_tokens(base, product, br, None, algo_version=1, tenant_slug="x")
    b = resolve_tokens(rev(base), rev(product), br2, None, algo_version=1, tenant_slug="x")
    assert a.to_json() == b.to_json()


def test_deterministic_across_processes():
    """Different hash seeds, separate interpreters: identical bytes."""
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from tokens import resolve_tokens\n"
        "r = resolve_tokens({'shared': {'--a-b': '1'}}, None, {'primaryColour': '#0F8A7E', 'accentColour': '#B8741A'}, 'dark', algo_version=1, tenant_slug='t')\n"
        "sys.stdout.write(r.to_json())\n" % str(Path(__file__).resolve().parents[2])
    )
    outs = []
    for seed in ("1", "2", "99"):
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env={"PYTHONHASHSEED": seed, "PATH": ""})
        assert p.returncode == 0, p.stderr
        outs.append(p.stdout)
    assert len(set(outs)) == 1 and outs[0]


def test_css_has_no_timestamp_or_comment(run):
    css = run(GOOD).css
    assert "/*" not in css and not re.search(r"20\d\d", css)


@pytest.mark.parametrize("branding", [None, {}])
def test_no_branding_is_exactly_product_theme(run, base, product, branding):
    r = run(branding)
    assert r.ok and r.resolved == merge(base, product)
    assert r.css == "" and r.tenant_tokens == {"light": {}, "dark": {}} and r.theme_algo is None and r.to_store is None
    assert r.html_attributes == {} and r.findings == ()


def test_no_branding_with_no_slug_still_fine(base, product):
    r = resolve_tokens(base, product, None, None, algo_version=1)
    assert r.ok and r.css == ""


def test_name_only_branding_adds_no_css(run, base, product):
    r = run({"displayName": {"en": "Acme"}})
    assert r.ok and r.css == "" and r.resolved == merge(base, product) and r.theme_algo is None


def test_product_overrides_base(base):
    m = merge({"shared": {"--x-y": "1"}, "light": {"--c-d": "a"}}, {"shared": {"--x-y": "2"}, "dark": {"--c-d": "b"}})
    assert m["light"] == {"--c-d": "a", "--x-y": "2"} and m["dark"] == {"--c-d": "b", "--x-y": "2"}


def test_generated_layers_parse(base, product):
    assert "--color-primary" in base["light"] and "--color-primary" in base["dark"] and "--font-heading" in base["shared"]
    assert base["light"]["--color-primary"] == "#2443D0" and base["dark"]["--color-primary"] == "#86A0FF"
    assert "--color-primary-hover" in product["light"] and "--chart-1" in product["dark"]


# ---------- locked tokens ----------
def _all_names(base, product):
    m = merge(base, product)
    return sorted(set(m["light"]) | set(m["dark"]))


def test_locked_name_count(base, product):
    locked = [n for n in _all_names(base, product) if n not in TENANT_TOKENS]
    assert len(locked) > 80


def test_every_locked_token_override_refused(run, base, product):
    reference = run(COBALT)
    for name in _all_names(base, product):
        if name in TENANT_TOKENS:
            continue
        r = run({**COBALT, "tokens": {name: "#FF00FF"}})
        assert C.TOKEN_LOCKED in codes(r, C.REFUSAL), name
        assert "#FF00FF" not in r.css and not r.ok
        # Never silently applied: the output is exactly what the valid colour alone gives.
        assert r.resolved == reference.resolved and r.css == reference.css, name


@pytest.mark.parametrize("name", TENANT_TOKENS)
def test_derived_tokens_cannot_be_set_directly(run, name):
    r = run({**COBALT, "tokens": {name: "#FF00FF"}})
    assert C.TOKEN_DERIVED_ONLY in codes(r, C.REFUSAL) and "#FF00FF" not in r.css


@pytest.mark.parametrize("name", ["--nope", "--color-brand-new", "--font-heading-2"])
def test_unknown_token_refused(run, name):
    r = run({**COBALT, "tokens": {name: "red"}})
    assert codes(r, C.REFUSAL) == [C.TOKEN_UNKNOWN] and "red" not in r.css


@pytest.mark.parametrize("name", ["color-primary", "--Color-Primary", "--a;}", "--a b", "", "-- ", "--x{", "--" + "a" * 70, 5])
def test_bad_token_name_refused(run, name):
    r = run({**COBALT, "tokens": {name: "#FF00FF"}})
    assert C.TOKEN_BAD_NAME in codes(r, C.REFUSAL) and "#FF00FF" not in r.css


def test_tokens_not_a_mapping(run):
    assert C.FIELD_TYPE in codes(run({**COBALT, "tokens": ["--color-text"]}), C.REFUSAL)


@pytest.mark.parametrize("fld", ["typography", "fonts", "spacing", "radii", "motion", "focusRing", "statusColours", "chartPalette", "neutrals", "danger"])
def test_locked_fields_refused(run, fld):
    r = run({**COBALT, fld: {"x": 1}})
    assert codes(r, C.REFUSAL) == [C.FIELD_LOCKED]
    assert r.resolved == run(COBALT).resolved


def test_unknown_field_refused(run):
    assert codes(run({**COBALT, "customCss": "body{}"}), C.REFUSAL) == [C.FIELD_UNKNOWN]


def test_locked_values_unchanged_by_tenant(run, base, product):
    r, m = run(GOOD), merge(base, product)
    for theme in ("light", "dark"):
        for k, v in m[theme].items():
            if k not in TENANT_TOKENS:
                assert r.resolved[theme][k] == v
        assert set(r.tenant_tokens[theme]) <= set(TENANT_TOKENS)


# ---------- injection ----------
BAD_SLUGS = ['a"b', "a'b", "a{b}", "a;b", "a</style>", "a url(x)", "@import 'x'", "A", "UPPER", "a b", "a\nb", "a\\b", "-a", "a-", "", "a" * 64,
             'x"] { color: red } :root[data-tenant="y', "../x", "a.b", "a_b", "é", "a]", "a[b", "a=b", "ａ"]


@pytest.mark.parametrize("slug", BAD_SLUGS)
def test_slug_injection_refused(run, slug):
    r = run(GOOD, slug=slug)
    assert C.SLUG_INVALID in codes(r, C.REFUSAL) and r.css == "" and r.tenant_slug is None and "data-tenant" not in r.html_attributes
    assert r.tenant_tokens == {"light": {}, "dark": {}}


@pytest.mark.parametrize("slug", ["a", "acme", "al-waha", "a1-b2", "0", "x" * 63])
def test_valid_slugs(run, slug):
    r = run(GOOD, slug=slug)
    assert r.ok and r.tenant_slug == slug and f'[data-tenant="{slug}"]' in r.css


def test_slug_not_a_string(run):
    assert C.SLUG_INVALID in codes(run(GOOD, slug=123), C.REFUSAL)


def test_slug_missing(run):
    r = run(GOOD, slug=None)
    assert codes(r, C.REFUSAL) == [C.SLUG_MISSING] and r.css == ""


BAD_HEX = ["#FFF", "FFFFFF", "#GGGGGG", "#12345", "#1234567", "#2443D0;}", "#2443D0}", "#2443D0 ", " #2443D0", "#2443D0\n", "#2443D0\n}", "red", "rgb(1,2,3)",
           "url(x)", "@import 'x'", "#2443D0</style>", "#2443D0; --color-text: red", "#２４４３D0", "", "javascript:1", 5, 1.5, True, ["#2443D0"], {"a": 1}]


@pytest.mark.parametrize("val", BAD_HEX)
def test_primary_hex_injection_refused(run, val):
    r = run({"primaryColour": val})
    assert codes(r, C.REFUSAL) == [C.COLOUR_INVALID_HEX] and r.css == "" and r.theme_algo is None


@pytest.mark.parametrize("val", BAD_HEX[:12] + [5])
def test_accent_hex_injection_refused(run, val):
    r = run({"primaryColour": "#2443D0", "accentColour": val})
    assert C.COLOUR_INVALID_HEX in codes(r, C.REFUSAL) and r.css == ""


def test_primary_null_refused(run):
    assert C.COLOUR_INVALID_HEX in codes(run({"primaryColour": None}), C.REFUSAL)


def test_accent_null_ok(run):
    assert run({**COBALT, "accentColour": None}).ok


def test_lowercase_hex_accepted_and_normalised(run):
    assert run({"primaryColour": "#0f8a7e"}).tenant_tokens == run({"primaryColour": "#0F8A7E"}).tenant_tokens


def test_hex_spelling_alias_and_conflict(run):
    assert run({"primary": "#0F8A7E", "accent": "#B8741A"}).css == run(GOOD).css
    r = run({"primaryColour": "#0F8A7E", "primary": "#2443D0"})
    assert C.FIELD_CONFLICT in codes(r, C.REFUSAL) and r.css == ""


def test_output_is_allowlisted_declarations_only(run):
    for br in (GOOD, COBALT, {**COBALT, "accentColour": "#B8741A"}):
        css = run(br).css
        for line in css.splitlines():
            if not line.strip() or line.strip() in ("}", "") or line.startswith((":root[", "@media", "  :root[")):
                continue
            m = re.fullmatch(r"\s+(--[a-z-]+): (#[0-9A-F]{6}|rgba\(\d+,\d+,\d+,[0-9.]+\));", line)
            assert m and m.group(1) in TENANT_TOKENS, line
        assert not re.search(r"url\(|@import|<|\\|/\*|expression|javascript", css)


def test_output_rejected_defence(run):
    """If an algorithm ever returned an odd name or value, nothing reaches the CSS."""
    from tokens.brand_tools import Derived

    def evil(p, a):
        v = {"--color-primary": "#000000;}body{x:y", "--color-text": "#000000"}
        return Derived(True, (), {"light": v, "dark": v}, {})

    r = run(COBALT, algorithms={1: evil})
    assert C.OUTPUT_REJECTED in codes(r, C.REFUSAL) and r.css == "" and r.theme_algo is None


# ---------- contrast, guardrails ----------
@pytest.mark.parametrize("primary", SAMPLE_PRIMARIES)
def test_aa_both_themes_independent(run, primary):
    r = run({"primaryColour": primary})
    if not r.ok:
        assert r.css == "" and C.COLOUR_TOO_LIGHT in codes(r, C.REFUSAL)
        return
    for theme in ("light", "dark"):
        assert aa_failures(r.resolved[theme]) == [], (primary, theme)


def test_aa_with_accent_independent(run):
    for p, a in [("#2443D0", "#0F8A7E"), ("#0F766E", "#B8741A"), ("#9333EA", "#F59E0B"), ("#0369A1", "#E0552C")]:
        r = run({"primaryColour": p, "accentColour": a})
        assert r.ok, (p, a, codes(r))
        for theme in ("light", "dark"):
            assert aa_failures(r.resolved[theme]) == [], (p, a, theme)


def test_aa_property_random_colours(run):
    import random
    rnd = random.Random(7)
    accepted = 0
    for _ in range(120):
        c = "#%06X" % rnd.randrange(1 << 24)
        r = run({"primaryColour": c})
        if r.ok:
            accepted += 1
            for theme in ("light", "dark"):
                assert aa_failures(r.resolved[theme]) == [], (c, theme)
        else:
            assert r.css == "" and r.tenant_tokens == {"light": {}, "dark": {}}
    assert accepted >= 20


def test_edge_colour_limit(run):
    """The light-shift limit sits between teal-500 (rejected) and teal-600-ish (accepted)."""
    assert C.COLOUR_TOO_LIGHT in codes(run({"primaryColour": "#14B8A6"}), C.REFUSAL)
    assert run({"primaryColour": "#10A090"}).ok


@pytest.mark.parametrize("colour,code", [
    ("#6B7280", C.COLOUR_GREY), ("#808080", C.COLOUR_GREY), ("#0B1020", C.COLOUR_GREY), ("#FFFFFF", C.COLOUR_GREY),
    ("#C21F3A", C.COLOUR_NEAR_CRIMSON), ("#D32F2F", C.COLOUR_NEAR_CRIMSON), ("#E53935", C.COLOUR_NEAR_CRIMSON),
    ("#FFD400", C.COLOUR_TOO_LIGHT), ("#F59E0B", C.COLOUR_TOO_LIGHT), ("#7DB6FF", C.COLOUR_TOO_LIGHT), ("#14B8A6", C.COLOUR_TOO_LIGHT),
    ("#1A1040", C.COLOUR_TOO_DARK),
])
def test_guardrail_refusals(run, base, product, colour, code):
    r = run({"primaryColour": colour})
    assert codes(r, C.REFUSAL) == [code], codes(r)
    assert not r.ok and r.css == "" and r.theme_algo is None and r.tenant_tokens == {"light": {}, "dark": {}}
    assert r.resolved == merge(base, product)


@pytest.mark.parametrize("accent,code", [
    ("#808080", C.ACCENT_GREY), ("#C21F3A", C.ACCENT_NEAR_CRIMSON), ("#FFF3A0", C.ACCENT_TOO_LIGHT),
])
def test_accent_refusals(run, accent, code):
    r = run({"primaryColour": "#2443D0", "accentColour": accent})
    assert codes(r, C.REFUSAL) == [code] and r.css == ""


def test_accent_too_close_to_primary(run):
    r = run({"primaryColour": "#2443D0", "accentColour": "#2A48D6"})
    assert codes(r, C.REFUSAL) == [C.ACCENT_TOO_CLOSE_PRIMARY]


def test_refusal_drops_all_tenant_colours_but_keeps_name(run):
    r = run({"primaryColour": "#808080", "displayName": {"en": "Acme"}})
    assert r.css == "" and r.brand["displayName"] == {"en": "Acme"}


def test_adjustment_codes_and_params(run):
    r = run({"primaryColour": "#0F766E"})
    adj = {f.code: f for f in r.adjustments}
    assert set(adj) == {C.ADJ_LIGHT_PRIMARY, C.ADJ_DARK_PRIMARY}
    p = adj[C.ADJ_LIGHT_PRIMARY].params
    assert p["from"] == "#0F766E" and p["to"] == r.tenant_tokens["light"]["--color-primary"] and 0 < p["shiftL"] <= 0.2
    assert adj[C.ADJ_DARK_PRIMARY].params["to"] == r.tenant_tokens["dark"]["--color-primary"]
    assert C.WARN_NEAR_STATUS in codes(r)


def test_cobalt_is_not_darkened(run):
    r = run(COBALT)
    assert r.tenant_tokens["light"]["--color-primary"] == "#2443D0" and C.ADJ_LIGHT_PRIMARY not in codes(r)


def test_accent_adjustments(run):
    r = run({"primaryColour": "#2443D0", "accentColour": "#F59E0B"})
    assert r.ok and C.ADJ_LIGHT_ACCENT in codes(r) and C.ADJ_DARK_ACCENT in codes(r)


def test_accent_fallback_to_text(run):
    r = run({"primaryColour": "#C59043"})
    assert r.ok and C.ADJ_ACCENT_FALLBACK in codes(r)
    assert r.tenant_tokens["light"]["--color-accent"] == r.resolved["light"]["--color-text"]
    assert r.tenant_tokens["dark"]["--color-accent"] == r.resolved["dark"]["--color-text"]


def test_default_accent_kept_when_not_given(run, base):
    r = run(COBALT)
    assert "--color-accent" not in r.tenant_tokens["light"] and r.resolved["light"]["--color-accent"] == base["light"]["--color-accent"]


def test_given_accent_emitted(run):
    r = run(GOOD)
    assert r.tenant_tokens["light"]["--color-accent"] == "#B8741A"


def test_findings_are_codes_only(run):
    for br in (GOOD, {"primaryColour": "#808080"}, {**COBALT, "tokens": {"--color-text": "x"}}, {"primaryColour": "#0F766E"}):
        for f in run(br).findings:
            d = f.to_dict()
            assert set(d) == {"code", "severity", "path", "params"} and re.fullmatch(r"TKN(-[A-Z0-9]+)+", d["code"])
            assert d["path"].startswith("/")
            for v in d["params"].values():
                assert v is None or isinstance(v, (int, float)) or (isinstance(v, str) and (len(v) <= 64 and " " not in v)) or isinstance(v, list)


def test_findings_sorted_and_deterministic(run):
    r = run({"primaryColour": "#0F766E", "tokens": {"--color-text": "x", "--color-surface": "y"}, "weird": 1})
    assert list(r.findings) == sorted(r.findings, key=lambda f: f.sort_key())


# ---------- reuse of derive_tenant_theme ----------
def _decls(css):
    """selector -> {var: value}"""
    out, sel = {}, None
    for line in css.splitlines():
        s = line.strip()
        if s.endswith("{") and s.startswith(":root"):
            sel = s[:-1].strip(); out[sel] = {}
        elif sel and (m := re.fullmatch(r"(--[a-z0-9-]+): (.+);", s)):
            out[sel][m.group(1)] = m.group(2)
    return out


@pytest.mark.parametrize("primary,accent", [("#2443D0", None), ("#0F766E", None), ("#9333EA", "#F59E0B"), ("#0F8A7E", "#B8741A"), ("#C59043", None)])
def test_matches_derive_tenant_theme(run, primary, accent):
    from tokens import brand_tools
    _, D = brand_tools.load()
    res = D.derive(primary, accent)
    assert res["status"] == "ok"
    theirs = _decls(D.css("acme", res))
    ours = _decls(run({"primaryColour": primary, **({"accentColour": accent} if accent else {})}).css)
    assert set(ours) == set(theirs)
    for sel, decls in ours.items():
        assert set(decls) <= set(TENANT_TOKENS)
        for k, v in decls.items():
            assert theirs[sel][k] == v, (sel, k)
        # Everything derive sets for primary comes through; only the accent may be absent (default Coral stays).
        missing = set(k for k in theirs[sel] if k in TENANT_TOKENS) - set(decls)
        assert missing <= {"--color-accent"}


def test_rejections_match_derive(run):
    from tokens import brand_tools
    _, D = brand_tools.load()
    for c in ("#FFD400", "#6B7280", "#C21F3A", "#1A1040", "#14B8A6", "#0F766E", "#2443D0"):
        assert (D.derive(c)["status"] == "ok") == run({"primaryColour": c}).ok


# ---------- selectors ----------
def test_css_scoping_exact(run):
    css = run(GOOD, slug="al-waha").css
    sels = [l.strip()[:-1].strip() for l in css.splitlines() if l.strip().endswith("{")]
    assert sels == [':root[data-tenant="al-waha"]', "@media (prefers-color-scheme: dark)",
                    ':root[data-tenant="al-waha"]:not([data-theme="light"])', ':root[data-tenant="al-waha"][data-theme="dark"]']
    d = _decls(css)
    light, dark = d[':root[data-tenant="al-waha"]'], d[':root[data-tenant="al-waha"][data-theme="dark"]']
    assert d[':root[data-tenant="al-waha"]:not([data-theme="light"])'] == dark
    assert light != dark and set(light) == set(dark)
    assert light["--color-primary-label"] == "#FFFFFF" and dark["--color-primary-label"] == "#0E1117"
    assert css.endswith("}\n") and css.count("{") == css.count("}") == 4


def test_css_sorted_within_blocks(run):
    for block in _decls(run(GOOD).css).values():
        assert list(block) == sorted(block)


def test_html_attributes(run):
    assert run(GOOD, "dark", slug="al-waha").html_attributes == {"data-tenant": "al-waha", "data-theme": "dark"}
    assert run(GOOD, "system").html_attributes == {"data-tenant": "acme"}
    assert run(None, "light").html_attributes == {"data-theme": "light"}


# ---------- user preference ----------
@pytest.mark.parametrize("pref", [None, "light", "dark", "system", {"theme": "dark"}, {}])
def test_preference_never_changes_tenant_colours(run, pref):
    ref = run(GOOD)
    r = run(GOOD, pref)
    assert r.ok and r.css == ref.css and r.tenant_tokens == ref.tenant_tokens and r.resolved == ref.resolved


def test_preference_modes(run):
    assert run(None, None).theme_mode == "system" and run(None, {"theme": "dark"}).theme_mode == "dark" and run(None, "light").theme_mode == "light"


@pytest.mark.parametrize("pref", [{"theme": "dark", "primaryColour": "#FF0000"}, {"primary": "#FF0000"}, {"--color-primary": "#FF0000"}, {"tokens": {}}])
def test_preference_colours_refused(run, pref):
    ref = run(GOOD)
    r = run(GOOD, pref)
    assert C.PREF_FIELD in codes(r, C.REFUSAL) and r.css == ref.css and "#FF0000" not in json.dumps(r.resolved)


@pytest.mark.parametrize("pref", ["blue", "DARK", "", 3, ["dark"], {"theme": "sepia"}, {"theme": None}])
def test_preference_invalid_mode(run, pref):
    r = run(GOOD, pref)
    assert C.PREF_MODE in codes(r, C.REFUSAL) and r.theme_mode == "system" and r.css == run(GOOD).css


# ---------- themeAlgo ----------
def test_theme_algo_recorded(run):
    r = run(GOOD)
    assert r.theme_algo == 1 and r.to_store["themeAlgo"] == 1 and r.to_dict()["themeAlgo"] == 1
    assert r.to_store["resolved"] == r.tenant_tokens


def test_algo_version_changes_only_theme_algo(run):
    from tokens import default_algorithms
    algos = {1: default_algorithms()[1], 2: default_algorithms()[1]}
    a, b = run(GOOD, algo=1, algorithms=algos), run(GOOD, algo=2, algorithms=algos)
    da, db = a.to_dict(), b.to_dict()
    assert da["themeAlgo"] == 1 and db["themeAlgo"] == 2
    da.pop("themeAlgo"); db.pop("themeAlgo")
    assert da == db


def test_unsupported_algo_refused(run):
    r = run(GOOD, algo=2)
    assert codes(r, C.REFUSAL) == [C.ALGO_UNSUPPORTED] and r.css == "" and r.theme_algo is None


@pytest.mark.parametrize("v", [0, -1, "1", 1.0, True, None])
def test_bad_algo_version(run, v):
    assert C.ALGO_UNSUPPORTED in codes(run(GOOD, algo=v), C.REFUSAL)


def test_stored_theme_algo_pins_algorithm(run):
    """A tenant saved under algo 1 keeps algo 1 even when the caller's current version is 2."""
    from tokens import default_algorithms
    one = default_algorithms()[1]
    calls = []

    def algo2(p, a):  # a "new" algorithm that would restyle
        calls.append(2)
        d = one(p, a)
        return d

    r = run({**GOOD, "themeAlgo": 1}, algo=2, algorithms={1: one, 2: algo2})
    assert r.theme_algo == 1 and calls == [] and C.NOTICE_ALGO_PINNED in codes(r) and r.css == run(GOOD).css


def test_stored_resolved_used_verbatim(run):
    stored = run(GOOD)
    br = {**GOOD, "themeAlgo": 1, "resolved": stored.to_store["resolved"]}
    # even with a "new" algorithm that would differ, and a changed current version
    r = run(br, algo=2, algorithms={2: lambda p, a: (_ for _ in ()).throw(AssertionError("must not re-derive"))})
    assert r.ok and r.css == stored.css and r.theme_algo == 1 and C.NOTICE_ALGO_PINNED in codes(r)


@pytest.mark.parametrize("mut", [
    lambda r: r["light"].update({"--color-text": "#000000"}),
    lambda r: r["light"].update({"--color-primary": "#000000;}x{"}),
    lambda r: r["dark"].update({"--color-primary": "url(x)"}),
    lambda r: r["dark"].update({"--color-primary": "rgba(999,0,0,1)"}),
    lambda r: r.pop("dark"),
    lambda r: r.update({"extra": {}}),
    lambda r: r["light"].clear(),
])
def test_stored_resolved_invalid_refused(run, mut):
    import copy
    stored = copy.deepcopy(run(GOOD).to_store["resolved"])
    mut(stored)
    r = run({**GOOD, "themeAlgo": 1, "resolved": stored})
    assert C.RESOLVED_INVALID in codes(r, C.REFUSAL) and r.css == ""


def test_stored_resolved_needs_algo(run):
    r = run({**GOOD, "resolved": run(GOOD).to_store["resolved"]})
    assert C.RESOLVED_INVALID in codes(r, C.REFUSAL) and r.css == ""


# ---------- display name and references ----------
@pytest.mark.parametrize("name", [{"en": "Al Nakhla Trading", "ar": "النخلة للتجارة"}, {"ar": "شركة الواحة"}, {"en": "株式会社", "zh": "公司"}, {"fa": "نخل‌ها"}, {"en": "A" * 40}])
def test_non_latin_names_pass_through_and_stay_out_of_css(run, name):
    r = run({**GOOD, "displayName": name})
    assert r.ok and r.brand["displayName"] == name
    assert all(v in json.dumps(r.to_dict(), ensure_ascii=False) for v in name.values())
    assert not any(ch in r.css for v in name.values() for ch in v if ord(ch) > 127)
    assert r.css.isascii() and all(v not in r.css for v in name.values())
    assert r.css == run(GOOD).css


@pytest.mark.parametrize("name", ["Acme", {}, {"en": ""}, {"en": "   "}, {"en": "A" * 41}, {"en": "a\x00b"}, {"en": "a\nb"}, {"en": 5}, {"e n": "A"}, {"en": "A", "ar": ""}, None])
def test_bad_display_name_refused(run, name):
    r = run({**GOOD, "displayName": name})
    assert C.NAME_INVALID in codes(r, C.REFUSAL) and "displayName" not in r.brand


def test_name_with_css_chars_is_data_only(run):
    r = run({**GOOD, "displayName": {"en": 'a"}</style><b>'}})
    assert r.brand["displayName"] == {"en": 'a"}</style><b>'} and "style" not in r.css and "<" not in r.css


def test_logo_and_favicon_references_pass_through_untouched(run):
    logo = {"onLight": {"assetId": "x", "sha256": "ab"}, "deriveDark": True}
    r = run({**GOOD, "logo": logo, "favicon": {"source": "auto"}})
    assert r.brand["logo"] == logo and r.brand["logo"] is not logo and r.brand["favicon"] == {"source": "auto"} and "assetId" not in r.css


def test_object_fields_type_checked(run):
    assert C.FIELD_TYPE in codes(run({**GOOD, "logo": "http://x"}), C.REFUSAL)


def test_branding_not_a_mapping(run):
    r = run("red")
    assert C.FIELD_TYPE in codes(r, C.REFUSAL) and r.css == ""


# ---------- layers and base drift ----------
def test_base_mismatch_fails_closed(base, product):
    bad = {**base, "dark": {**base["dark"], "--color-text": "#FFFFFF"}}
    r = resolve_tokens(bad, product, COBALT, None, algo_version=1, tenant_slug="x")
    assert C.BASE_MISMATCH in codes(r, C.REFUSAL) and r.css == ""


def test_base_missing_colours_fails_closed(product):
    r = resolve_tokens({}, product, COBALT, None, algo_version=1, tenant_slug="x")
    assert C.BASE_MISMATCH in codes(r, C.REFUSAL) and r.css == ""


@pytest.mark.parametrize("layer", ["x", {"bad": {}}, {"light": {"color-primary": "#fff"}}, {"light": {"--a": 5}}, {"light": []}, {"shared": {"--a;}": "x"}}])
def test_invalid_layers_refused(product, layer):
    r = resolve_tokens(layer, product, None, None, algo_version=1)
    assert codes(r, C.REFUSAL) == [C.LAYER_INVALID]


def test_result_not_aliasing_inputs(run, base):
    r = run(COBALT)
    r.resolved["light"]["--color-text"] = "mutated"
    assert base["light"].get("--color-text") != "mutated" and run(COBALT).resolved["light"]["--color-text"] != "mutated"


@pytest.mark.parametrize("v", ["1", True, 1.5])
def test_bad_stored_theme_algo(run, v):
    r = run({**GOOD, "themeAlgo": v})
    assert codes(r, C.REFUSAL) == [C.ALGO_INVALID] and r.css == ""
