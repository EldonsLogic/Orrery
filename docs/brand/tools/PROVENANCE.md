# Provenance: `build_logo.py` (Seshna logo generator)

**Source.** The Seshna logo kit "Nuqta S", exploration draft v3 (November 2026), file `tools/build_kit.py`, supplied by the founders outside the repo. The kit is not published anywhere; there is no upstream commit. Imported under BRD-014, ADR-0066.

**Font used to generate.** Cairo variable font, `ofl/cairo/Cairo[slnt,wght].ttf` from google/fonts at commit `a2c83daed9bc723922de8d0a9512990bd3d91df4` (SHA-256 `667c9871 82391c91 f4e57a2f 455b1794 fb5e3ee6 ca4ef338 3e86bb69 0fa9c964`, fetched 2026-11-23). Copyright 2009 The Cairo Project Authors (https://github.com/Gue3bara/Cairo), SIL OFL 1.1. The font file is not in the repo; the outlined wordmark is artwork, not a font file.

**Check.** With that font, `build_logo.py` writes the 11 masters byte-identical to the kit's `masters/` folder (mark and small-size cut, light and dark; wordmark, light and dark; horizontal lockups primary, dark and on Cobalt; stacked lockups primary and dark). Verified 2026-11-23.

## Kept
- Mark geometry (`turn`, `mark_geometry`, `mark_path`), the 18-unit master cut and 30-unit small-size cut, the 256 grid, heights 224 and 240.
- Wordmark shaping (HarfBuzz kerning), instancing at wght 700 with slnt 0, tracking -0.5% em, outline via fontTools pens, the SVG comment.
- Lockup proportions (horizontal mark 1.6 x cap height, stacked 2.2 x, gap 0.6 x, panel padding one cap height) and the palette values.

## Changed
- Command line: the font path comes from the environment variable `SESHNA_FONT_CAIRO`; output always goes to `docs/brand/logo/`; family, weight and tracking are constants. The name comes from `brand.json`.
- Without the font the script still writes the marks and app icons (stdlib only) and leaves the wordmark and lockups untouched.
- Output file names follow the repo (`mark-primary.svg`, `lockup-primary.svg`, ...) so `scripts/build_brand_assets.py` and `web/scripts/copy-tokens.mjs` keep working.
- Added: one-colour black and white marks, and the app icons (rounded tile, full-bleed square for apple-touch-icon, maskable) as flat paths on a 64-unit tile. The kit's own app icon and favicon used a `transform` and a different tile radius; these are redrawn without transforms (tile radius 14/64, small-size cut, mark 62% of the tile; maskable 50%).
- Removed: an unused `panel` helper with dead code, the redundant first `mark_path` call per mark.

## Removed from the kit (not imported)
- `presentation/` (board and mockup slides) and `check/` (preview renders), and all mockups.
- The kit's PNG renders and `web/` set: PNG, ICO, apple-touch and maskable icons are regenerated here by `build_icons.py`.
- `make_guidelines.py` and the guidelines PDF (PDFs are not allowed in the repo). The guideline text is rewritten into `docs/brand/02-logo.md` and related files.
