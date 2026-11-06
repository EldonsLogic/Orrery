# Fonts

No font files are bundled in this repo. Alexandria and Readex Pro licences are confirmed from the OFL.txt files that ship with the fonts (checked 2026-11-06); Lucide is still UNVERIFIED.

| Font | Use | Source | Licence (per PDF) |
|---|---|---|---|
| Alexandria | Wordmark and headings (500-600) | Google Fonts: https://fonts.google.com/specimen/Alexandria | SIL OFL 1.1, confirmed. Copyright 2022 The Alexandria Project Authors, https://github.com/Gue3bara/Alexandria |
| Readex Pro | Interface and body (400, 500) | Google Fonts: https://fonts.google.com/specimen/Readex+Pro | SIL OFL 1.1, confirmed. Copyright 2018 The Readex Pro Project Authors, https://github.com/ThomasJockin/readexpro. Reserved Font Name: 'RevReading Lexend' |
| Lucide (icons) | Outline icons, 24 px, 1.75 px stroke | https://lucide.dev | ISC, UNVERIFIED |

## Loading in the app
- Self-host the WOFF2 files; do not call Google Fonts at runtime (privacy, latency, availability). `preview.html` uses a Google Fonts link for review only.
- Subset to Latin and Arabic (plus punctuation and digits), and check coverage of the 2025 SAR and AED currency symbols (open item).
- Load only the weights used: Alexandria 500 and 600; Readex Pro 400 and 500. Use `font-display: swap` and the fallbacks in `tokens.css`.
- Record the licence text of each font file next to it once downloaded.

## Licence notes (OFL 1.1)
- Reserved Font Name restriction: a modified Readex Pro font file may not use the reserved name 'RevReading Lexend'. Subsetting or converting to WOFF2 counts as modification under the OFL, so rename subsets accordingly and keep the OFL.txt with each file.
- The outlined wordmark in `logo/*.svg` is artwork drawn from glyph outlines, not a font file; the OFL does not restrict it. Its SVG comment says: outlined from Alexandria SemiBold (SIL OFL 1.1).

## Rebuilding the outlined wordmark
Keep the font outside the repo and point the build at it: `ORRERY_FONT_ALEXANDRIA=/path/to/Alexandria-VF.ttf python3 tools/build_logo.py && ORRERY_FONT_ALEXANDRIA=/path/to/Alexandria-VF.ttf python3 tools/build_logo_proposed.py` (needs Python fontTools). Without the variable the scripts write the live-text PLACEHOLDER lockups, so do not commit those over the outlined files.
