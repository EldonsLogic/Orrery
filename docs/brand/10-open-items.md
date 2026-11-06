# 10 Open items

Items the PDF leaves undone, inconsistent or unverified.

## Missing from the PDF
1. The PDF (p.4) refers to an "Open items" section; it does not exist. This file replaces it.
2. The PDF (p.9) refers to a "03-fonts folder of this kit"; no font files were supplied. See `fonts/README.md`.
3. Hand-tuned 16 px and 32 px favicons (and small mark versions below 24 px) do not exist yet. Not drawn here.
4. DONE (2026-11-06): wordmark outlined from Alexandria SemiBold (wght 600) in `lockup-primary.svg`, `lockup-dark.svg` and `logo/proposed/lockup-stacked.svg`. Measured cap height 700/1000 em (OS/2 sCapHeight), ink width about 4.56 X; the old INFERRED 0.70 and 4.5 X are replaced by measured values. Font: https://github.com/Gue3bara/Alexandria, SIL OFL 1.1. Still open: designer review of spacing, the r's and the y tail; kerning is only the font's own r+y pair.
5. Stacked lockup is not in v1.
6. Fourth direction idea (orbital geometry) not started.
7. Not specified in the PDF (so not invented): "low opacity" value for the quadrant device, app-icon corner radius and nudge distance, spacing scale beyond the 8 px grid, hover/pressed/disabled states, breakpoints, shadows, chart palette beyond the stated rule.

## Inconsistencies noticed
- "Carbon" has two hex values: #12151B (light text, mono mark) and #0E1117 (dark background, dark button label). The 7.64:1 claim needs #0E1117. The dark app-icon tile uses #0E1117 (INFERRED).
- The PDF says tagline lines marked with a flag need native review but flags only the first line, while p.10 requires review of every Arabic headline and tagline.

## Decisions pending
- **Arabic spelling of the name. PROPOSED, NOT APPLIED.** The PDF forbids transliterating the name into Arabic letters anywhere. Reviewers recommend allowing an Arabic spelling in running text and search copy only, while the logo stays Latin. Needs a founder decision and a native-speaker choice of spelling.
- **Numerals.** Western (0-9) vs Arabic-Indic: confirm with pilot customers.
- **Name clearance.** Orrery is a working codename, not trademark-cleared.

## To verify
- Native-speaker review of every Arabic line (flag: all of them, not only the first tagline).
- Claim that Saudi Arabia and the UAE introduced new currency symbols in 2025, and whether Alexandria and Readex Pro include them (UNVERIFIED).
- Font licences: Alexandria and Readex Pro confirmed SIL OFL 1.1 from their OFL.txt files (see `fonts/README.md`). Lucide (ISC): still UNVERIFIED.
- Marketing claims in the foundation table ("Days", "a simulated month") must not be published until the product can prove them.
- ZATCA invoice template with a compliance advisor.
- Transcription of Arabic text from page images; check against the source PDF.

## Possible contrast gap (not in the PDF table)
- Destructive button is "Crimson fill, white label" (p.13). In dark mode Crimson is #FF6B81, and white on #FF6B81 is about 2.7:1, below AA. The PDF contrast table does not cover this pair. Needs a design decision; preview.html follows the PDF literally (white label).

## v1.1 status of each item (added after Task D; everything below is PROPOSED, nothing accepted)
Proposals live in `11-v1.1-additions.md`, `12-tenant-theming.md`, `logo/proposed/`, `tokens/tokens.proposed.*`. v1 files and tokens are unchanged. "Open" means a human must still decide or review.
| Item above | Status | Where | Still open |
|---|---|---|---|
| Missing 3: 16 and 32 px marks | PROPOSED draft: pixel-snapped `mark-16.svg`, `mark-32.svg`, slot verified at least 1.5 px (16) and 1.94 px (32) wide by rendering | `logo/proposed/`, `tools/build_logo_proposed.py --verify` | Designer review and approval; sizes between 16 and 24 px |
| Missing 4: wordmark not outlined | DONE: outlined from Alexandria SemiBold by `tools/wordmark_outline.py` (env `ORRERY_FONT_ALEXANDRIA`), cap height 700/1000 em measured; stacked lockup also outlined | `logo/lockup-*.svg`, `logo/proposed/lockup-stacked.svg` | Designer review of the generated outline |
| Missing 5: stacked lockup | PROPOSED draft (mark 2.8 X, gap 0.6 X, start-aligned) | `logo/proposed/lockup-stacked.svg` | Designer review |
| Missing 6: orbital direction | Not started | | Founder decision |
| Missing 7: quadrant device opacity | PROPOSED 10% (max 16% with no text over it) and placement rules | 11, section 5 | Founder accept |
| Missing 7: app-icon radius and nudge | PROPOSED: radius 14/64, nudge 1.5/64 with computed reasoning and safe-zone check | 11, section 6 | Designer accept |
| Missing 7: spacing scale, breakpoints, shadows | PROPOSED | 11, section 1 | Founder accept |
| Missing 7: hover, pressed, disabled, selected, focus, visited | PROPOSED, all text pairs AA (200 pairs checked) | 11, section 3 | Founder accept |
| Missing 7: chart palette | PROPOSED 6 series, 3:1 on all surfaces, colour-blind checked | 11, section 12 | Founder accept; designer taste check |
| Inconsistency: two Carbon hexes | PROPOSED names only: Carbon ink #12151B, Carbon deep #0E1117 (hex unchanged) | 11, section 2; `--carbon-ink`, `--carbon-deep` | Founder accept naming |
| Inconsistency: tagline flag only on first line | Unchanged. Every Arabic line added in 11 is flagged | | Native-speaker review of all Arabic |
| Contrast gap: destructive button, dark | PROPOSED: Carbon deep label on #FF6B81, 6.90:1 | 11, section 4 | Founder accept; `preview.html` still follows v1 literally |
| New gap found: status pills on their own 14% tint | PROPOSED: pill label tokens (v1 colour reaches 3.51 to 4.41:1 in light on tint) | 11, section 3 | Founder accept |
| New gap found: comparison series "Carbon at 40%" is 2.58:1 in light | PROPOSED alpha 49% (light), 40% kept (dark) | 11, section 12 | Founder accept |
| Tenant branding (CONTEXT section 9) | PROPOSED: layers, locked and open tokens, derivation with AA guarantee, logo and document rules | 12; `tools/derive_tenant_theme.py` | ADR-0014 acceptance; limits (0.20 L, red brands, light-brand mode); compliance advisor for invoice precedence |
| Decisions pending (Arabic name spelling, numerals, name clearance) | Unchanged, still founder decisions | | Open |
| To verify (fonts, licences, currency symbols, marketing claims, ZATCA template, Arabic transcription) | Unchanged | | Open. New UNVERIFIED items: Lucide icon names, Machado colour-blind matrices, maskable and store icon rules, week start day |
