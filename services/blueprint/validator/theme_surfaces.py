"""Theme surfaces used for the branding contrast check (rule 10).

Copied from docs/brand/tokens/tokens.json (token names color.light.surface, color.light.background,
color.dark.surface, color.dark.background). The validator never reads docs at runtime; a test
(tests/test_theme_surfaces.py) fails when these copies drift from tokens.json.
"""

SURFACES: dict[str, dict[str, str]] = {
    "light": {
        "surface": "#FFFFFF",     # color.light.surface (Panel)
        "background": "#F3F4F6",  # color.light.background (Chalk)
    },
    "dark": {
        "surface": "#171B23",     # color.dark.surface (Panel)
        "background": "#0E1117",  # color.dark.background (Carbon)
    },
}
