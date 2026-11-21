import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build_brand_assets as b  # noqa: E402

FILES = b.build()
MODES = b.roles(json.loads(b.TOKENS.read_text(encoding="utf-8")))[1]


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


if __name__ == "__main__":
    unittest.main()
