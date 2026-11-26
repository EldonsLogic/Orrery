# Font licence and Arabic typography check (BRD-011)

Status: draft for founder review. Checked 2026-11-21 (access date for every source below).
Owner: eldon. Register rows: [docs/legal/licence-register.md](../legal/licence-register.md) section 1b-ii.

## Method

- Licence text: each family's OFL.txt (raw GitHub) and the Google Fonts METADATA.pb for the same family. Google Fonts specimen pages returned only their titles to the fetch tool (client-rendered), so they are cited as the public listing, not as the licence source.
- Embedding and self-hosting: SIL OFL FAQ at https://openfontlicense.org/ofl-faq/ (entries 1.12, 2.1, 2.4, 2.6).
- Files were not downloaded and no font file is in the repo (see `docs/brand/fonts/README.md`).

## Fonts found in the repo

| Font | Where used | Licence (confirmed) | Source checked | Weights and axis | Embed PDF | Self-host webfont | Arabic script | Digits | Gaps |
|---|---|---|---|---|---|---|---|---|---|
| Readex Pro | `docs/brand/tokens/tokens.css` (`--font-body`), `web/app/src/styles/tokens.generated.css`, `web/marketing/src/styles/tokens.generated.css`, `apps/engine/.../print_formats/bilingual_tax_invoice.py` | SIL OFL 1.1 | OFL.txt (raw GitHub, ThomasJockin/readexpro); METADATA.pb (google/fonts) | wght 160 to 700; brand uses 400 and 500 | Yes (FAQ 1.12) | Yes (FAQ 2.1, 2.4) | Subsets include arabic, latin, latin-ext | Latin 0-9 in latin subset; Arabic-Indic and tnum UNVERIFIED | Reserved Font Name 'RevReading Lexend'; subset must be renamed |
| Alexandria | tokens (`--font-heading`), web CSS, print format, `docs/brand/tools/wordmark_outline.py` (wordmark outlined, no font file in repo) | SIL OFL 1.1 | OFL.txt (raw GitHub, google/fonts mirror of Gue3bara/Alexandria); METADATA.pb | wght 100 to 900; brand uses 500 and 600 | Yes | Yes | Subsets include arabic | Arabic-Indic and tnum UNVERIFIED | None |
| Noto Sans Arabic | print format `font-family` stack only | SIL OFL 1.1 | OFL.txt (google/fonts); METADATA.pb | Regular 400 listed; axes not checked | Yes | Yes | Yes (Noto Arabic block) | Arabic-Indic glyphs UNVERIFIED (glyph check needed) | Fallback only; not in brand tokens |
| DejaVu Sans | print format stack only | Bitstream Vera licence (redistribution and modification allowed with rename) | LICENSE (dejavu-fonts master) | n/a | Yes, with notice | Yes, with notice | Limited Arabic (not checked) | UNVERIFIED | Fallback only |
| Arial | print format stack only | Microsoft proprietary (not verified here) | not fetched | n/a | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | See findings |

## Findings

1. Alexandria and Readex Pro are SIL OFL 1.1 on the OFL.txt and Google Fonts metadata. This confirms `docs/brand/fonts/README.md` (checked 2026-11-06) and extends it to 2026-11-21.
2. Embedding in PDFs is permitted for both (OFL FAQ 1.12). The tax invoice print format may embed them, including subsets.
3. Self-hosting WOFF2 is permitted (OFL FAQ 2.1). Converting to WOFF2 and subsetting are modifications (FAQ 2.2, 2.6). Readex Pro has the RFN 'RevReading Lexend', so a modified Readex Pro must not use that name. Alexandria has no RFN.
4. Copyright year mismatch: Readex Pro OFL.txt says 2018, Google METADATA says 2019. Both point to the same project. Not a licence issue; record the OFL.txt text with each file.
5. Print format names Arial in its font stack. Arial is a Microsoft font and is not covered by OFL. It is not bundled, so there is no redistribution. But if a PDF render falls back to Arial on a host that has it, the output embeds a system font. Recommend removing Arial from the stack, or bundling Noto Sans Arabic or DejaVu Sans as the fallback. Founder decision needed.
6. Preview pages (`docs/brand/preview.html`) load Google Fonts from fonts.googleapis.com for review only. Fonts README already rules this out for the app. Keep it out of the web bundle.
7. Print formats name 'Readex Pro' first, but no WOFF2 or TTF is bundled into the PDF pipeline, so the renderer falls back to whatever the host has. Bundling the files is a prerequisite for consistent Arabic invoices.

## Gaps (UNVERIFIED)

- Arabic-Indic digits (U+0660 to U+0669) in Readex Pro and Alexandria: not confirmed from the font files. Needs a glyph-map check on the downloaded TTFs.
- Tabular figures (`tnum`) in Readex Pro and Alexandria: not confirmed. Needed for amounts and tables (brand section 04).
- Saudi riyal symbol (U+20C3, 2025): coverage not checked in any family. Brand item in `docs/brand/10-open-items.md` stays open.
- Arabic coverage of DejaVu Sans and Arial: not checked. Only relevant if they stay in the fallback stack.
- Google Fonts specimen pages could not be read through the fetch tool; their licence fields were read from METADATA.pb instead.

## Next steps

- Download the families from the Google Fonts repo, keep each OFL.txt next to its file, and run a glyph check for U+0660 to U+0669, U+20C3 and the `tnum` feature. Record the results here.
- Founder decision: Arial in the print format stack (remove, or bundle a fallback).
- Then mark BRD-011 done and close Q-119 in `docs/open-questions.md`.

## Addendum 2026-11-23 (BRD-014): Cairo
Cairo replaces Alexandria for headings and the wordmark (ADR-0066). Licence checked from `ofl/cairo/OFL.txt` in google/fonts at commit a2c83daed9bc723922de8d0a9512990bd3d91df4 (accessed 2026-11-23): SIL OFL 1.1, Copyright 2009 The Cairo Project Authors (https://github.com/Gue3bara/Cairo), no Reserved Font Name. Identical to the OFL.txt shipped with the Seshna logo kit. Used only to outline the wordmark; no Cairo font file is in the repo. The Alexandria rows above are historical. Not yet confirmed for Cairo: Arabic-Indic digits, `tnum`, 2025 currency symbols.

## Addendum 2026-11-25 (BRD-011, WEB-028): pinned-file verification and coverage
Both files were downloaded from google/fonts at commit `a2c83daed9bc723922de8d0a9512990bd3d91df4` (accessed 2026-11-25) and checked with fontTools 4.x (`uv run --no-project --with fonttools --with brotli`).

| Item | Cairo | Readex Pro |
|---|---|---|
| Source file | https://github.com/google/fonts/blob/a2c83daed9bc723922de8d0a9512990bd3d91df4/ofl/cairo/Cairo%5Bslnt,wght%5D.ttf | https://github.com/google/fonts/blob/a2c83daed9bc723922de8d0a9512990bd3d91df4/ofl/readexpro/ReadexPro%5BHEXP,wght%5D.ttf |
| TTF SHA-256 | `667c987182391c91f4e57a2f455b1794fb5e3ee6ca4ef3383e86bb690fa9c964` (matches the BRD-014 record) | `268bba7e1e8f3b14d798b3fb0e40ebaa3fc39308c9ac0020e2faf6df181cc30e` |
| OFL.txt SHA-256 | `a4554e1799d42e1405924b61eb0e0722ae1623b1f1f07f995348f96c496362a9`: OFL 1.1, Copyright 2009 The Cairo Project Authors, no RFN | `b41267a3903a45955f77b44596e080480c577fb7221df59672d0bc8cd8cd4b6f`: OFL 1.1, Copyright 2018 The Readex Pro Project Authors, RFN "RevReading Lexend" |
| Axes | wght 200 to 1000, slnt -11 to 11 | wght 160 to 700, HEXP 0 to 100 |
| Arabic letters U+0621 to U+064A and harakat U+064B to U+0652 | all present in the full font; the web subset lacks U+063B to U+063F (37 of 42 letters) | same as Cairo: full font has all; the web subset lacks U+063B to U+063F |
| Latin A-Z, a-z, 0-9 | present | present |
| Arabic-Indic digits U+0660 to U+0669 (and U+06F0 to U+06F9) | 10/10 (10/10) | 10/10 (0/10) |
| Web subset, checked with fontTools 2026-11-26 on the shipped `*-subset.woff2` files | U+0600 to U+06FF: 102 of 256 code points; U+063B to U+063F absent; U+0660 to U+0669 and U+06F0 to U+06F9 present | U+0600 to U+06FF: 73 of 256 code points; U+063B to U+063F absent; U+06F0 to U+06F9 absent; U+0660 to U+0669 present |
| Arabic comma, semicolon, question mark, percent, decimal and thousands separators (U+060C, U+061B, U+061F, U+066A to U+066C) | present | present |
| Tabular figures (`tnum` feature) | none (GSUB has no tnum or pnum) | none (no tnum or pnum) |
| Digit widths without any feature | Western digits all 560 units: effectively tabular by default. Arabic-Indic digits vary 250 to 678: proportional | Western digits vary 500 to 620: proportional. Arabic-Indic digits vary 281 to 630: proportional |
| Saudi riyal sign (U+20C1) | absent | absent |

Findings:
1. Licences confirmed for both from the pinned commit. Cairo has no RFN; Readex Pro's RFN is not used (the subset keeps the name "Readex Pro" and the name table does not contain the reserved name).
2. `font-variant-numeric: tabular-nums` does nothing in either font. Cairo's Western digits are tabular anyway; Readex Pro's are not. Amount columns set in Readex Pro will not align on digit width. Needs a founder decision: set amount and table figures in Cairo (Western digits), or accept proportional figures, or add a tabular-figure instance. Recorded as a gap, not worked around.
3. No Saudi riyal sign in either font, so the product must use the code "SAR" or the Arabic abbreviation (`04-typography.md` already allows this). Earlier docs wrote the code point as U+20C3; the founder brief says U+20C1. Neither is in either font. Which code point Unicode assigned is UNVERIFIED (unicode.org not fetched).
4. Arabic shaping quality (joining, mark positioning in rendered text) and Arabic-Indic digit appearance were not visually reviewed: UNVERIFIED. Glyph presence and OpenType tables only.
5. Web subsets (WEB-028): `web/app/public/fonts/` holds `Cairo-subset.woff2` (38,420 B) and `ReadexPro-subset.woff2` (34,740 B) with each OFL.txt and a PROVENANCE.md. Weights: Cairo 500 to 600, Readex Pro 400 to 500, `slnt` and `HEXP` pinned to 0. Coverage kept: Basic Latin, Latin-1, general punctuation, the Arabic letters and digits listed in the subset row above (not the whole Arabic block: Cairo 102 and Readex Pro 73 of 256 code points in U+0600 to U+06FF), and the Arabic-Indic digits U+0660 to U+0669; Readex Pro also lacks U+06F0 to U+06F9 (Extended Arabic-Indic digits).
6. Not covered here: Persian and Urdu letters beyond what the Arabic block holds in these files, Latin Extended beyond Latin-1, the print format fallback decision (Arial), Noto Sans Arabic and DejaVu Sans coverage.
7. Founder decision (Eldon, 2026-11-25, WEB-028 BRD-011): numbers in tables and amount columns, numeric inputs and calendar days use Cairo through the `--font-heading` token, with `tabular-nums`, because Cairo's Western digits 0-9 all share advance width 559. Body text stays Readex Pro and headings stay Cairo. Known limit: Arabic-Indic digits are proportional in both fonts; a tabular instance is a later fix.
