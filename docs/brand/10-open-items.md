# 10 Open items

What the Seshna brand system (ADR-0066) still leaves undone, unverified or in draft. The Quadrant-era items (hand-tuned Quadrant favicons, Alexandria wordmark outline, Quadrant stacked lockup, orbital direction, quadrant device) are closed: the Quadrant mark and Alexandria are retired. Their history is in git and in `docs/log/`.

## Before public launch
- **Trademark search** on the name Seshna and the Nuqta S mark in Saudi Arabia, the UAE, Egypt and Qatar. Not done. No TM or (R) until registered.
- **Name story wording (DRAFT).** "Inspired by the Egyptian root for writing (sš)" and "the rhombic dot as the calligrapher's unit of proportion" must be checked with a specialist before public storytelling (`01-foundation.md`).
- **Arabic lines in the kit** (tagline and specimens) need native-speaker review. Every Arabic line, not only the first.
- **Marketing claims** in the foundation table ("Days", "a simulated month") must not be published until the product can prove them.

## Logo system gaps
- **Status and Progress marks:** built in web from the master and small-cut paths (`09-applications.md`, BRD-014). The outline stroke (16 u master, 22 u small cut, inside the silhouette), sizes (20 px status, 24 px progress) and spacing are INFERRED, not from the kit; designer check. Progress order follows the reading direction (Discover at the start, on the right in Arabic) while each mark stays unmirrored.
- **Runtime tenant-variable paths need the same `--seshna-` guard.** Only `tools/derive_tenant_theme.py` refuses to emit `--seshna-*` today. Any runtime path that writes tenant CSS variables (the Blueprint `branding` apply, a server-side theme resolver, a client that sets properties on `:root`) must reject or drop `--seshna-*` the same way, with a test. Owner: whoever builds that path.
- **Loading mark (approved by Eldon, 2026-11-26; closed):** fill cycle outline, upper half, both halves on a 2.4 s loop; static drafted state under reduced motion (`09-applications.md`). In use in web pending approval.
- **One-colour lockup** (black or white with the wordmark) for single-colour invoices: not generated; only the one-colour marks exist.
- **Size set below 24 px:** `scripts/build_brand_assets.py` (outside `docs/brand`) derives `logo/assets/mark-16.svg` and `mark-24.svg` from the master; the 16 px file should use the small-size cut (`mark-small.svg`). The minimum lockup width in that script is 80 px; the new rule is 96 px. Needs a scripts change with its own plan row.
- **App icon geometry** (tile radius 14/64, mark at 62%, maskable at 50%) is INFERRED for this repo: the kit's own app icon used a 22.5% radius and a transform. Designer check.
- **Graphic device.** The quadrant device is retired and the kit defines no replacement brand graphic (`07-graphic-elements.md`, `11-v1.1-additions.md` section 5).
- **Seshna storytelling device for social and slides:** not specified.

## Code outside `docs/brand` and `web/` that still uses the old system
- `apps/engine/change_engine/change_engine/print_formats/bilingual_tax_invoice.py` lists Alexandria in its font stack (and its test lists it as an allowed font).
Each needs its owner's plan row.

## Closed
- **State marks under a tenant theme:** closed 2026-11-24. Both founders decided the marks always stay Seshna Cobalt (`--seshna-mark`, never tenant-overridable; `09-applications.md`, `12-tenant-theming.md`).

## Decisions pending
- **Numerals.** Western (0-9) vs Arabic-Indic: confirm with pilot customers.
- **Mirroring of progress graphics in RTL** (the logo never mirrors).

## To verify
- Claim that Saudi Arabia and the UAE introduced new currency symbols in 2025, and whether Cairo and Readex Pro include them (UNVERIFIED).
- Arabic-Indic digits and tabular figures (`tnum`) in Cairo and Readex Pro: not confirmed from the font files.
- Maskable icon safe-circle rule (80%) and store icon rules (UNVERIFIED).
- ZATCA invoice template with a compliance advisor.

## Inconsistencies noticed (carried from v1)
- "Carbon" has two hex values: #12151B (text, wordmark) and #0E1117 (dark background, dark app-icon tile). `11-v1.1-additions.md` section 2 proposes names for both.
- Destructive button in dark mode: white on #FF6B81 is about 2.7:1. PROPOSED fix in `11-v1.1-additions.md` section 4.

## v1.1 and tenant theming
Everything in `11-v1.1-additions.md` and `12-tenant-theming.md` stays PROPOSED until the founders accept each section. The token files `tokens/tokens.proposed.*` were ACCEPTED as the active layer on 2026-11-22 (Q-70). The Quadrant-era v1.1 status table is retired with the Quadrant mark (ADR-0066); its open founder and designer items for spacing, states, charts and tenant limits remain in sections 1 to 12 of `11-v1.1-additions.md`.
