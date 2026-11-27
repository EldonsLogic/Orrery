"""Static UI rules: no markup sinks, tokens only for colours and fonts, one bilingual string dictionary, local assets."""
import json
import re
import shutil
import subprocess

import pytest

from studio_testlib import STATIC

JS_FILES = sorted(STATIC.glob("*.js"))
SINKS = re.compile(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\s*\(|new\s+Function\s*\(|setTimeout\s*\(\s*['\"]")
COLOUR = re.compile(r"#[0-9A-Fa-f]{3,8}\b|\brgba?\(|\bhsla?\(")


def test_static_js_has_no_markup_or_code_sinks():
    assert JS_FILES
    for f in JS_FILES:
        text = f.read_text(encoding="utf-8")
        assert not SINKS.search(text), f.name


def test_html_has_no_inline_script_style_or_handlers():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)", html)
    assert "<style" not in html and " style=" not in html
    assert not re.search(r"\son[a-z]+=", html)
    assert "cdn" not in html.lower() and "unpkg" not in html.lower()


def test_css_colours_and_fonts_only_in_the_token_block():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    block_end = css.index("}") + 1
    rest = css[block_end:]
    assert not COLOUR.search(rest), COLOUR.search(rest)
    for m in re.finditer(r"font-family\s*:\s*([^;}]+)", rest):
        assert m.group(1).strip().startswith("var(--") or m.group(1).strip() == "inherit", m.group(0)
    assert "--studio-qr-light" in css[:block_end]


def test_js_sets_no_literal_colours():
    for f in JS_FILES:
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"['\"]#[0-9A-Fa-f]{3,8}['\"]", text), f.name


@pytest.mark.skipif(shutil.which("node") is None, reason="node is needed to read i18n.js")
def test_dictionary_has_english_and_arabic_and_covers_every_key_the_ui_uses():
    script = "global.window={};require(process.argv[1]);process.stdout.write(JSON.stringify(window.STUDIO_I18N));"
    out = subprocess.run(["node", "-e", script, str(STATIC / "i18n.js")], capture_output=True, text=True, check=True)
    d = json.loads(out.stdout)
    assert set(d) == {"en", "ar"}
    assert set(d["ar"]) == set(d["en"]), (sorted(set(d["en"]) - set(d["ar"])), sorted(set(d["ar"]) - set(d["en"])))
    used = set()
    used |= set(re.findall(r'data-i18n="([^"]+)"', (STATIC / "index.html").read_text(encoding="utf-8")))
    used |= set(re.findall(r"\b[tT]\('([a-zA-Z0-9.]+)'", (STATIC / "app.js").read_text(encoding="utf-8")))
    missing = sorted(k for k in used if not k.endswith(".") and k not in d["en"])  # 'prefix.' + value is dynamic
    assert not missing, missing
    assert d["en"]["engine.fake"] == "In-memory engine (fake)"


def test_served_assets_are_local(client):
    status, body, headers = client.get("/")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    html = body.decode("utf-8")
    for src in re.findall(r'(?:src|href)="(/[^"]*)"', html):
        s, _, h = client.get(src)
        assert s == 200, src
    status, css, _ = client.get("/tokens/tokens.css")
    assert status == 200 and b"--color-primary" in css


@pytest.mark.skipif(shutil.which("node") is None, reason="node is needed to read i18n.js")
def test_arabic_keeps_placeholders_and_never_names_the_engine():
    script = "global.window={};require(process.argv[1]);process.stdout.write(JSON.stringify(window.STUDIO_I18N));"
    out = subprocess.run(["node", "-e", script, str(STATIC / "i18n.js")], capture_output=True, text=True, check=True)
    d = json.loads(out.stdout)
    token = re.compile(r"\{[a-zA-Z]+\}")
    for k, en in d["en"].items():
        ar = d["ar"][k]
        assert ar.strip(), k
        assert sorted(token.findall(ar)) == sorted(token.findall(en)), k
        assert not re.search(r"frappe|erpnext", ar, re.I), k
