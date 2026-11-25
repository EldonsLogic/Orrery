# Fonts

No font files are bundled in this repo. Cairo replaces Alexandria for headings (ADR-0066, 2026-11-23); Readex Pro stays for body.

| Font | Use | Source | Licence |
|---|---|---|---|
| Cairo | Headings (500-600) and the outlined wordmark (700) | Google Fonts: https://fonts.google.com/specimen/Cairo; file used for the wordmark: google/fonts `ofl/cairo/Cairo[slnt,wght].ttf` at commit a2c83daed9bc723922de8d0a9512990bd3d91df4 (fetched 2026-11-23) | SIL OFL 1.1, confirmed from that commit's OFL.txt. Copyright 2009 The Cairo Project Authors, https://github.com/Gue3bara/Cairo. No Reserved Font Name in the OFL.txt |
| Readex Pro | Interface and body (400, 500) | Google Fonts: https://fonts.google.com/specimen/Readex+Pro | SIL OFL 1.1, confirmed. Copyright 2018 The Readex Pro Project Authors, https://github.com/ThomasJockin/readexpro. Reserved Font Name: 'RevReading Lexend' |
| Lucide (icons) | Outline icons, 24 px, 1.75 px stroke | https://lucide.dev | ISC (see the licence register) |

Alexandria is retired from the brand (it was the v1 heading font). Code outside `docs/brand` and `web/` that still names it is listed in `10-open-items.md`.

## Loading in the app
- Self-host the WOFF2 files; do not call Google Fonts at runtime (privacy, latency, availability). `preview.html` uses a Google Fonts link for review only.
- Subset to Latin and Arabic (plus punctuation and digits), and check coverage of the 2025 SAR and AED currency symbols (open item).
- Load only the weights used: Cairo 500 and 600; Readex Pro 400 and 500. Use `font-display: swap` and the fallbacks in `tokens.css`.
- Record the licence text and a PROVENANCE note next to each font file once added. (The web app does not load any web font yet: it uses the token font stacks with system fallbacks.)

## Licence notes (OFL 1.1)
- Subsetting or converting to WOFF2 counts as modification under the OFL: keep the OFL.txt with each file, and do not use a Reserved Font Name (Readex Pro: 'RevReading Lexend') for a modified file.
- The outlined wordmark in `logo/*.svg` is artwork drawn from glyph outlines, not a font file; the OFL does not restrict it. Its SVG comment says: outlined from Cairo (wght 700), SIL OFL 1.1.

## Rebuilding the outlined wordmark
Keep the font outside the repo and point the build at it: `SESHNA_FONT_CAIRO=/path/to/Cairo-VF.ttf uv run --no-project --with fonttools --with uharfbuzz python3 tools/build_logo.py`. Without the variable the script rebuilds only the marks and app icons and leaves the wordmark and lockups untouched.
