# Provenance: self-hosted brand fonts (WEB-028, BRD-011)

Kept here, not in `web/app/public/fonts/`, so it is not served in the static export. The font files and their OFL texts stay in `web/app/public/fonts/`.

Two subset variable WOFF2 files, derived from Google Fonts upstream files, both SIL OFL 1.1. Accessed 2026-11-25. The Studio serves these same files (`services/studio`).

| Output file | Upstream file (google/fonts, commit `a2c83daed9bc723922de8d0a9512990bd3d91df4`) | Upstream SHA-256 | Output SHA-256 | Size |
|---|---|---|---|---|
| `Cairo-subset.woff2` | <https://github.com/google/fonts/blob/a2c83daed9bc723922de8d0a9512990bd3d91df4/ofl/cairo/Cairo%5Bslnt,wght%5D.ttf> (font version 3.130) | `667c987182391c91f4e57a2f455b1794fb5e3ee6ca4ef3383e86bb690fa9c964` | `c4b79cdc72306d0db80310573471b9549176577b8921c7ec650e9c72d22cc42e` | 38,420 B |
| `ReadexPro-subset.woff2` | <https://github.com/google/fonts/blob/a2c83daed9bc723922de8d0a9512990bd3d91df4/ofl/readexpro/ReadexPro%5BHEXP,wght%5D.ttf> (font version 1.205) | `268bba7e1e8f3b14d798b3fb0e40ebaa3fc39308c9ac0020e2faf6df181cc30e` | `4c268924a2ad5cf62423ea54dd8f4c87a1c77160ce073ef6a9b95b66d016c87d` | 34,740 B |

Licence texts (in `web/app/public/fonts/`): `Cairo-OFL.txt` (upstream SHA-256 `a4554e1799d42e1405924b61eb0e0722ae1623b1f1f07f995348f96c496362a9`, Copyright 2009 The Cairo Project Authors, no Reserved Font Name) and `ReadexPro-OFL.txt` (upstream SHA-256 `b41267a3903a45955f77b44596e080480c577fb7221df59672d0bc8cd8cd4b6f`, Copyright 2018 The Readex Pro Project Authors, Reserved Font Name "RevReading Lexend"). Both are copies of `ofl/<family>/OFL.txt` at the commit above with trailing whitespace stripped by the repo's pre-commit hook (text otherwise identical); committed SHA-256 `aa2b13bf0770c59a7fb7a3b793a7df5162c9cb5ad540ec81b0c0c1385946845d` (Cairo, converted from CRLF to LF line endings) and `2a07fb9a9c171c89bd6f52c8d06d182f76bb4c9b7870a738459fea51a5f1e459` (Readex Pro). The font name stays "Cairo" and "Readex Pro"; the reserved name does not appear in the subset's name table (checked).

## What was changed (OFL modification)

- Variable axes narrowed: Cairo `wght` 500 to 600 and `slnt` pinned to 0 (no slant, brand rule); Readex Pro `wght` 400 to 500 and `HEXP` pinned to 0.
- Glyphs subset to Basic Latin, Latin-1 Supplement, `U+0152`, `U+0153`, `U+02C6`, `U+02DC`, General Punctuation `U+2000-206F`, `U+20AC`, `U+2122`, `U+2212`, `U+2215`, `U+25CC`, the Arabic block `U+0600-06FF` and `U+FDF2`, `U+FDFC`; all layout features kept for those glyphs; hinting dropped; WOFF2 compression.
- No outlines were edited.

## Rebuild

Run with `uv run --no-project --with fonttools --with brotli python3 -I <script>`, in a script kept outside the repo (the subset build script is not in the repo; recorded as an open item) that uses `fontTools.varLib.instancer` (limit axes, then save and reload the font) then `fontTools.subset` (flavor woff2, `layout_features=['*']`, `name_IDs=['*']`, `notdef_outline`, no hinting) with the code points above. Fonts are not added to the repo as TTF; fetch them from the pinned commit.

## Known glyph gaps

The pinned upstream TTFs and the subsets both lack U+063B to U+063F; Readex Pro also lacks U+06F0 to U+06F9; Arabic-Indic digits are proportional in both fonts, and neither has a riyal sign. Details: `docs/brand/font-licence-check.md`. Arabic shaping in the subsets is not yet verified in a browser.
