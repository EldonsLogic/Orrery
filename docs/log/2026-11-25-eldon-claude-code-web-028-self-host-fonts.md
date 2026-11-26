# Session log: web-028-self-host-fonts

Date: 2026-11-25
Author: eldon
Tool and model: claude-code
Plan IDs: BRD-011,WEB-028

## Summary
Verified the Cairo and Readex Pro licences and glyph coverage from the pinned google/fonts commit (BRD-011), subset both to WOFF2 and self-hosted them in the web app and the Studio, removing the Google Fonts link and CSP entries (WEB-028). Gaps found: no `tnum` in either font (Readex Pro Western digits are proportional) and no Saudi riyal sign; both recorded, not worked around.

## Files touched
- web/app/public/fonts/: two subset WOFF2 files, two OFL.txt, PROVENANCE.md
- web/app/src/styles/fonts.css, web/app/src/app/layout.tsx: @font-face with font-display swap, imported first
- web/scripts/check-tokens-only.mjs (+ test): font-family literal allowed only in styles/fonts.css
- services/studio (server.py, _paths.py, static/index.html, tests): serves the same fonts at /fonts/, CSP now font-src and style-src 'self' only
- docs/brand/font-licence-check.md, docs/brand/fonts/README.md, docs/brand/10-open-items.md, docs/legal/licence-register.md, docs/open-questions.md (Q-119), docs/PLAN.md

## Decisions
- Studio serves the web app's font files locally (chose local serving, not system-stack fallback). No ADR needed; follows ADR-0058 and ADR-0066.

## Tokens or cost
Unknown.

## Next step
Founder decision on tabular figures for amounts (Cairo digits, accept proportional, or a tabular instance) and on the riyal sign (use the code). Arabic shaping visual review is UNVERIFIED. Print format still names Alexandria and Arial (ERP-007 owner).

## Addendum: tabular figures decision (2026-11-25)
Implemented Eldon's decision: `.numeric` in Table and TextField and `.day` in DatePicker set `font-family: var(--font-heading)` (Cairo) with `tabular-nums`. No new token. Recorded in `docs/brand/font-licence-check.md` item 7. Known limit: Arabic-Indic digits stay proportional until a tabular instance exists.

## Addendum: partner review fixes on PR #320 (2026-11-26)
- Merged origin/main into the branch (no rebase).
- CI: `.github/workflows/tests.yml` now lists `web/app/public/fonts/**` and `web/app/src/styles/fonts.css` in both `paths` triggers (after `!web/**`) and in the Studio suite filter.
- Studio test `test_every_font_url_in_served_stylesheet_resolves_as_woff2` parses `url(...)` in the served fonts.css and asserts 200 and `font/woff2` for each.
- `DatePicker.module.css`: typed date input uses `var(--font-heading)` with `tabular-nums`.
- Glyph coverage verified with fontTools on the shipped subset files: both subsets lack U+063B to U+063F; Readex Pro subset also lacks U+06F0 to U+06F9. Cairo subset covers 102/256 and Readex Pro 73/256 of U+0600 to U+06FF. Corrected `docs/brand/font-licence-check.md` and refreshed `docs/legal/licence-register.md` (bundled status, Studio references).
- Checks: Studio pytest 72 passed; web test 337 passed; web lint ok; check_docs, check_repo_hygiene, check_plan_independence ok.
