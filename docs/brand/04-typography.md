# 04 Typography (PDF p.9; ADR-0066)

Two families cover both scripts, both under the SIL Open Font License 1.1 and on Google Fonts (licences in `fonts/README.md`).
- **Cairo.** Headings everywhere (product, site and documents) and the outlined wordmark. Replaces Alexandria (founder decision 2026-11-23). Headings at 500 to 600; the wordmark is Cairo Bold 700, outlined, never typed live. Its angled stroke ends repeat the cut of the Nuqta S mark.
- **Readex Pro.** Interface and body text. Built for legibility in Latin and Arabic. Body at 400, labels and buttons at 500.

| Style | Family | Size / line height, Latin | Size / line height, Arabic |
|---|---|---|---|
| Display | Cairo 600 | 40 / 48 px | 40 / 60 px |
| Heading 1 | Cairo 600 | 32 / 40 px | 32 / 48 px |
| Heading 2 | Cairo 500 | 24 / 32 px | 24 / 36 px |
| Heading 3 | Cairo 500 | 20 / 28 px | 20 / 32 px |
| Body | Readex Pro 400 | 16 / 24 px | 16 / 28 px |
| Small | Readex Pro 400 | 14 / 20 px | 14 / 24 px |
| Caption | Readex Pro 400 | 12 / 16 px | 12 / 20 px |

Sizes, weights and line heights are the v1 scale unchanged; only the heading family changed. Tokens: `--font-heading` and `--font-body` in `tokens/tokens.css` (generated from `tokens/tokens.json`).

- **Arabic** uses the same sizes with more line height. Never fake an italic or slant; emphasis comes from weight.
- **Numerals.** Tabular figures for amounts, tables and invoices. Default to Western digits (0-9) in both languages for amounts, dates and document numbers; to be confirmed with pilot customers.
- **Currency.** "SAR 12,480.00" in English and "12,480.00 ر.س" in Arabic. New 2025 currency symbols only where the fonts support them, otherwise the codes. (Claim UNVERIFIED; Cairo coverage not checked.)
- **No all-caps labels.** Sentence case everywhere: headings, buttons, labels.
- The product name inside Arabic text stays Latin and is isolated left-to-right (`02-logo.md`).

Specimen (logo kit, DRAFT): "Understand. Build. Run." with its Arabic line (native review pending); "Purchase approvals", "Simulation, week 3".
