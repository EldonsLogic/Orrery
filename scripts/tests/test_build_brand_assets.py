import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build_brand_assets as b  # noqa: E402

FILES = b.build()
MODES = b.roles(json.loads(b.TOKENS.read_text(encoding="utf-8")))[1]
HEX_ROLE = b.roles(json.loads(b.TOKENS.read_text(encoding="utf-8")))[0]
NS = 'xmlns="http://www.w3.org/2000/svg"'
P = MODES["light"]["primary"]
# a valid source; each negative case changes one thing so the rejection is due to the payload
BASE = f'<svg {NS} width="10" height="10" viewBox="0 0 10 10"><title>t</title><path d="M0 0L10 10Z" fill="{P}"/></svg>'


def light(svg):
    return b.derive(b.load("t.svg", svg), "light", {}, HEX_ROLE, MODES)


class BrandAssets(unittest.TestCase):
    def test_build_is_deterministic(self):
        self.assertEqual(b.build(), FILES)

    def test_committed_outputs_match(self):
        self.assertEqual(b.main(["--check"]), 0)

    def test_dark_variant_uses_dark_tokens_only(self):
        self.assertIn(MODES["dark"]["primary"], FILES["mark-dark.svg"])
        self.assertNotIn(MODES["light"]["primary"], FILES["mark-dark.svg"])
        self.assertIn(MODES["dark"]["text"], FILES["lockup-dark.svg"])

    def test_app_icon_dark_swaps_tile_and_glyph(self):
        dark = FILES["app-icon-dark.svg"]
        self.assertIn(f'rx="14" fill="{MODES["dark"]["background"]}"', dark)
        self.assertIn(f'fill="{MODES["dark"]["primary"]}"', dark)

    def test_sizes_keep_viewbox_and_aspect(self):
        self.assertIn('width="32" height="32"', FILES["mark-32.svg"])
        self.assertIn("viewBox=", FILES["mark-32.svg"])
        self.assertIn('width="160"', FILES["lockup-w160.svg"])

    def test_validator_rejects_active_content(self):
        ns = 'xmlns="http://www.w3.org/2000/svg"'
        for bad in (f"<svg {ns}><script>x</script></svg>",
                    f'<svg {ns}><image href="https://e.example/x.png"/></svg>',
                    '<!DOCTYPE svg [<!ENTITY a "b">]><svg ' + ns + "/>",
                    f'<svg {ns} onload="x()"/>'):
            with self.assertRaises(SystemExit):
                b.validate("bad.svg", bad)

    def test_all_outputs_pass_validator(self):
        for n, s in FILES.items():
            b.validate(n, s)


    # --- review of PR #239, High 1: validator bypasses (SEC-018 section 6) ---
    def test_base_fixture_is_accepted(self):
        b.load("ok.svg", BASE)
        light(BASE)

    def assert_rejected(self, *cases):
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(SystemExit):
                b.load("bad.svg", bad)

    def test_rejects_unanchored_svg_namespace(self):
        self.assert_rejected(BASE.replace("2000/svg", "2000/svg.evil.example/x"),
                             BASE.replace(NS, 'xmlns="https://www.w3.org/2000/svg"'))

    def test_rejects_foreign_namespace_and_root(self):
        self.assert_rejected(
            '<x:svg xmlns:x="urn:evil" width="10" height="10" viewBox="0 0 10 10"><x:path d="M0 0Z"/></x:svg>',
            BASE.replace("<svg ", "<g ").replace("</svg>", "</g>"),
            BASE.replace("<path ", '<x:path xmlns:x="urn:evil" '),
            BASE.replace("<path ", '<path xmlns:l="http://www.w3.org/1999/xlink" l:href="#a" '),
            BASE.replace("<title>t</title>", f"<svg {NS} viewBox=\"0 0 1 1\"/>"))

    def test_rejects_entity_encoded_and_scheme_payloads(self):
        self.assert_rejected(
            BASE.replace(f'fill="{P}"', 'fill="&#x75;rl(https://e.example/x)"'),
            BASE.replace(f'fill="{P}"', 'fill="u&#x72;l(#a)"'),
            BASE.replace('d="M0 0L10 10Z"', 'd="&#100;ata:text/html,x"'),
            BASE.replace('d="M0 0L10 10Z"', 'd="VBScript:msgbox(1)"'),
            BASE.replace('d="M0 0L10 10Z"', 'd="jav&#x61;script:x"'),
            BASE.replace('d="M0 0L10 10Z"', 'd="@import x"'),
            BASE.replace('<path ', '<path transform="EXPRESSION(alert(1))" '),
            BASE.replace('<path ', '<path transform="java\tscript:x" '))

    def test_rejects_active_and_style_elements(self):
        for el in ('<style>@import url(https://e.example/a.css);</style>',
                   '<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">x</div></foreignObject>',
                   '<image href="data:image/png;base64,AAAA"/>', '<use href="#a"/>',
                   '<set attributeName="href" to="javascript:x"/>', '<a href="https://e.example">x</a>'):
            self.assert_rejected(BASE.replace("<title>t</title>", "<title>t</title>" + el))
        self.assert_rejected(BASE.replace("<path ", '<path style="fill:url(https://e.example)" '))

    def test_rejects_control_bidi_dtd_and_encoding(self):
        self.assert_rejected(
            BASE.replace("<title>t</title>", "<title>t\u202e</title>"),
            BASE.replace("<title>t</title>", "<title>t&#x202E;</title>"),
            BASE.replace("<title>t</title>", "<title>t&#x2066;</title>"),
            BASE.replace("<title>t</title>", "<title>t\x01</title>"),
            BASE.replace("<title>t</title>", "<title>t\x85</title>"),
            '<?xml version="1.0" encoding="ISO-8859-1"?>' + BASE,
            '<?xml-stylesheet href="https://e.example/a.css"?>' + BASE,
            '<!DOCTYPE svg [<!ENTITY a "b">]>' + BASE,
            BASE.replace("<path ", "<path>text</path><path "),
            "<svg " + NS)

    def test_output_is_reserialised_from_tree(self):
        odd = (f"<?xml version='1.0' encoding='utf-8'?>\n<!-- c --><svg   {NS} width='10'\n height='10' "
               f"viewBox='0 0 10 10'><title>t</title>  <path d='M0 0L10 10Z' fill='{P.lower()}'  /></svg>")
        out = b.serialise(light(odd))
        self.assertEqual(out, b.serialise(light(BASE)))
        self.assertNotIn("<!--", out)
        self.assertNotIn("'", out)
        for n, s in FILES.items():
            self.assertEqual(b.serialise(b.load(n, s)), s, n)
            self.assertNotIn("<!--", s, n)

    def test_validate_rejects_non_canonical_or_non_token_output(self):
        good = b.serialise(light(BASE))
        b.validate("ok.svg", good)
        for bad in (good.replace("\n<title>", "\n  <title>"), good.replace(P, "#ABCDEF")):
            with self.subTest(bad=bad), self.assertRaises(SystemExit):
                b.validate("bad.svg", bad)

    # --- Medium 2: derive() must reject every non-token colour ---
    def test_derive_rejects_non_token_colours(self):
        for bad in (BASE.replace(f'fill="{P}"', 'fill="#fff"'), BASE.replace(f'fill="{P}"', 'fill="red"'),
                    BASE.replace(f'fill="{P}"', "fill='#ABCDEF'"), BASE.replace(f'fill="{P}"', 'fill="none"'),
                    BASE.replace(f'fill="{P}"', f'stroke="{P}"'), BASE.replace(f' fill="{P}"', "")):
            with self.subTest(bad=bad), self.assertRaises(SystemExit):
                light(bad)

    def test_derive_accepts_single_quoted_and_inherited_token_fill(self):
        dark = b.derive(b.load("t.svg", BASE.replace(f'fill="{P}"', f"fill='{P.lower()}'")), "dark", {}, HEX_ROLE, MODES)
        self.assertIn(f'fill="{MODES["dark"]["primary"]}"', b.serialise(dark))
        inherited = BASE.replace(f'<path d="M0 0L10 10Z" fill="{P}"/>', f'<g fill="{P}"><path d="M0 0L10 10Z"/></g>')
        light(inherited)

    # --- Medium 3: resize() and viewBox parsing ---
    def test_resize_survives_declaration_comment_and_missing_size(self):
        src = '<?xml version="1.0" encoding="UTF-8"?>\n<!-- c -->\n' + BASE.replace(' width="10" height="10"', "")
        out = b.serialise(b.resize(light(src), 32, "32"))
        self.assertIn('width="32"', out)
        self.assertIn('height="32"', out)
        self.assertIn('viewBox="0 0 10 10"', out)

    def test_bad_viewbox_fails_closed(self):
        for vb in ("", ' viewBox="0 0 0 10"', ' viewBox="0 0 10"', ' viewBox="a b c d"', ' viewBox="0 0 -1 10"',
                   ' viewBox="0 0 inf 10"'):
            bad = BASE.replace(' viewBox="0 0 10 10"', vb)
            with self.subTest(vb=vb), self.assertRaises(SystemExit):
                b.load("bad.svg", bad)

    # --- Medium 4: stale outputs and non-SVG files ---
    def test_check_fails_on_drift_and_extra_files(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(b, "OUT", Path(d)):
            self.assertEqual(b.main([]), 0)
            self.assertEqual(b.main(["--check"]), 0)
            first = Path(d) / sorted(FILES)[0]
            first.write_text(first.read_text(encoding="utf-8") + " ", encoding="utf-8")
            self.assertEqual(b.main(["--check"]), 1)
            b.main([])
            for extra in ("stale.svg", "notes.txt"):
                (Path(d) / extra).write_text("x", encoding="utf-8")
                self.assertEqual(b.main(["--check"]), 1)
                (Path(d) / extra).unlink()

    def test_write_removes_stale_files(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(b, "OUT", Path(d)):
            (Path(d) / "old-mark.svg").write_text("x", encoding="utf-8")
            (Path(d) / "old.png").write_text("x", encoding="utf-8")
            b.main([])
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), sorted(FILES))
            self.assertEqual(b.main(["--check"]), 0)


    # --- Fable re-review of ea68596 (L1, L2, L3, L5, L6) ---
    def test_check_compares_bytes_crlf_cr_and_bad_utf8(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(b, "OUT", Path(d)):
            b.main([])
            f = Path(d) / "mark.svg"
            good = f.read_bytes()
            for drift in (good.replace(b"\n", b"\r\n"), good.replace(b"\n", b"\r"), good + b"\xff"):
                f.write_bytes(drift)
                self.assertEqual(b.main(["--check"]), 1)
            b.main([])
            self.assertEqual(f.read_bytes(), FILES["mark.svg"].encode("utf-8"))

    def test_symlinked_output_folder_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            real = Path(d) / "elsewhere"
            real.mkdir()
            (real / "keep.txt").write_text("keep", encoding="utf-8")
            link = Path(d) / "assets"
            os.symlink(real, link)
            with mock.patch.object(b, "OUT", link):
                for argv in ([], ["--check"]):
                    with self.subTest(argv=argv), self.assertRaises(SystemExit):
                        b.main(argv)
            self.assertEqual(sorted(p.name for p in real.iterdir()), ["keep.txt"])

    def test_symlinked_entries_are_refused(self):
        for name in ("mark.svg", "stale.svg"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                out, outside = Path(d) / "assets", Path(d) / "outside.svg"
                out.mkdir()
                outside.write_text("outside", encoding="utf-8")
                with mock.patch.object(b, "OUT", out):
                    b.main([])
                    (out / name).unlink(missing_ok=True) if name == "mark.svg" else None
                    os.symlink(outside, out / name)
                    for argv in ([], ["--check"]):
                        with self.assertRaises(SystemExit):
                            b.main(argv)
                self.assertEqual(outside.read_text(encoding="utf-8"), "outside")
                self.assertTrue((out / name).is_symlink())

    def test_subdirectory_in_output_folder_aborts(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(b, "OUT", Path(d)):
            (Path(d) / "sub").mkdir()
            (Path(d) / "sub" / "x.svg").write_text("x", encoding="utf-8")
            with self.assertRaises(SystemExit):
                b.main([])
            self.assertTrue((Path(d) / "sub" / "x.svg").exists())

    def test_rejects_source_with_nothing_drawable(self):
        self.assert_rejected(BASE.replace(f'<path d="M0 0L10 10Z" fill="{P}"/>', "<g/>"))

    def test_markup_characters_are_escaped_and_round_trip(self):
        src = BASE.replace("<title>t</title>", "<title>a&lt;b&quot;c&amp;</title>").replace(
            ' viewBox="0 0 10 10"', ' viewBox="0 0 10 10" role="x&lt;y&quot;z"')
        out = b.serialise(light(src))
        self.assertIn('role="x&lt;y&quot;z"', out)
        self.assertIn("<title>a&lt;b&quot;c&amp;</title>", out)
        self.assertEqual(b.serialise(b.load("t.svg", out)), out)

    def test_deep_nesting_and_oversize_fail_closed(self):
        deep = BASE.replace("<path ", "<g>" * 2000 + "<path ").replace("</svg>", "</g>" * 2000 + "</svg>")
        big = BASE.replace('d="M0 0L10 10Z"', 'd="M0 0' + " L1 1" * (b.MAX_CHARS // 5) + '"')
        many = BASE.replace("<title>t</title>", "<title>t</title>" + "<g/>" * (b.MAX_ELEMENTS + 1))
        for bad in (deep, big, many):
            with self.subTest(n=len(bad)):
                with self.assertRaises(SystemExit):
                    b.load("bad.svg", bad)

    def test_rejects_arabic_letter_mark_and_zero_width_characters(self):
        cases = [BASE.replace("<title>t</title>", f"<title>t{c}</title>") for c in
                 ("\u061c", "\u200b", "\u200c", "\u200d", "\u200e", "\u200f", "\u2060", "\ufeff")]
        cases.append(BASE.replace('d="M0 0L10 10Z"', 'd="java&#x200B;script:x"'))
        self.assert_rejected(*cases)


if __name__ == "__main__":
    unittest.main()
