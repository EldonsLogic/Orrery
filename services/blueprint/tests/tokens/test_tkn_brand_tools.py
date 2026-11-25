import sys
from pathlib import Path

import pytest

from tokens import brand_tools as B
from tokens import codes as C
from tokens import layers


def test_load_is_cached_and_leaves_no_trace():
    before_path = list(sys.path)
    T, D = B.load()
    assert B.load() == (T, D)
    assert sys.path == before_path
    assert "themelib" not in sys.modules or sys.modules["themelib"] is not T
    assert Path(T.__file__) == B.TOOLS_DIR / "themelib.py" and Path(D.__file__) == B.TOOLS_DIR / "derive_tenant_theme.py"
    assert D.T is T


def test_no_bytecode_written_next_to_docs():
    B.load()
    assert not (B.TOOLS_DIR / "__pycache__").exists()


def test_derive_colours_ok():
    d = B.derive_colours("#2443D0", None)
    assert d.ok and d.vars["light"]["--color-primary"] == "#2443D0" and d.colours["dark"]["primary"] == d.vars["dark"]["--color-primary"]


@pytest.mark.parametrize("reason,code", [
    ("Primary #FFFFFF is near-white (OKLCH chroma 0.000 < 0.04). Buttons", C.COLOUR_GREY),
    ("Primary #C21F3A is within 0.000 of Seshna Crimson #C21F3A (limit 0.1).", C.COLOUR_NEAR_CRIMSON),
    ("Primary #FFD400 is too light: Primary text is 1.5:1", C.COLOUR_TOO_LIGHT),
    ("Primary #1A1040 is too dark: only 1.04:1", C.COLOUR_TOO_DARK),
    ("No darker shade of #123456 reaches AA in the light theme.", C.COLOUR_NO_AA),
    ("No lightness of #123456 gives AA for links", C.COLOUR_NO_AA),
    ("Dark primary #112233 has chroma 0.010: it would read as grey in the dark theme.", C.COLOUR_DARK_GREY),
    ("Dark primary #112233 falls within 0.1 of dark Crimson #FF6B81.", C.COLOUR_NEAR_CRIMSON),
    ("Dark primary #E8EAEF is indistinguishable from the dark theme text colour.", C.COLOUR_DARK_NEAR_TEXT),
    ("Accent #808080 is near-grey (chroma 0.0).", C.ACCENT_GREY),
    ("Accent #C21F3A is within 0.0 of Crimson: a highlight", C.ACCENT_NEAR_CRIMSON),
    ("Accent #FFD400 is too light for a graphic", C.ACCENT_TOO_LIGHT),
    ("No dark-theme shade of accent #FFD400 reaches 3:1.", C.ACCENT_NO_AA),
    ("Accent #2A48D6 is too close to the primary #2443D0", C.ACCENT_TOO_CLOSE_PRIMARY),
    ("Internal check failed: a derived pair", C.CONTRAST_INTERNAL),
    ("something nobody wrote yet", C.COLOUR_REJECTED),
])
def test_refusal_classification(reason, code):
    assert B._refusal_code(reason) == code


def test_every_recorded_rejection_classified_not_fallback():
    """Run derive over many colours: no rejection may fall into the unrecognised bucket."""
    import random
    rnd = random.Random(11)
    seen = set()
    for _ in range(400):
        d = B.derive_colours("#%06X" % rnd.randrange(1 << 24), "#%06X" % rnd.randrange(1 << 24) if rnd.random() < 0.5 else None)
        for f in d.findings:
            seen.add(f.code)
            assert f.code not in (C.COLOUR_REJECTED, C.ADJ_OTHER, C.WARN_OTHER), f
    assert C.COLOUR_GREY in seen and C.COLOUR_TOO_LIGHT in seen


def test_known_names_include_derived():
    names = B.locked_and_derivable_names()
    assert "--color-primary-hover" in names and "--color-danger" in names and names == sorted(set(names))


def test_layer_css_parser_ignores_nested_root_blocks():
    css = ':root { --a-b: 1; --c-d: 2; }\n@media (x) { :root { --a-b: 9; } }\n:root[data-theme="dark"] { --c-d: 3; }\n/* :root { --z: 1; } */'
    assert layers.layer_from_css(css) == {"shared": {"--a-b": "1"}, "light": {"--c-d": "2"}, "dark": {"--c-d": "3"}}


def test_v1_base_matches_generated_css(base):
    v1 = B.v1_base()
    for theme in ("light", "dark"):
        for var, key in (("--color-background", "background"), ("--color-surface", "surface"), ("--color-text", "text"), ("--color-danger", "danger")):
            assert base[theme][var].upper() == v1[theme][key].upper()
