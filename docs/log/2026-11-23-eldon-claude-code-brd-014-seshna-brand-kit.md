# Session log: brd-014-seshna-brand-kit

Date: 2026-11-23
Author: eldon
Tool and model: claude-code (Opus-class subagent)
Plan IDs: BRD-014

## Summary
Integrated the Seshna brand kit (ADR-0066): docs/brand guidelines rewritten, Nuqta S logo set regenerated from an adapted kit generator with pinned Cairo, heading token switched to Cairo, web icons, manifest and product-name strings updated. Two stacked PRs: docs/brand (`brd-014-seshna-brand-kit`), then web (`brd-014-seshna-web`, this log).

## Files touched
- docs/brand/tools/build_logo.py: replaced by the kit's build_kit.py, adapted (PROVENANCE.md). With Cairo at google/fonts a2c83dae it writes the 11 kit masters byte-identical.
- docs/brand/tools/build_icons.py: small-size cut below 24 px and in favicon.ico; adds maskable-512.png; apple-touch from a full-bleed square.
- docs/brand/logo/, logo/png/, logo/assets/: regenerated (build_logo.py, build_icons.py, scripts/build_brand_assets.py unchanged). Removed Quadrant-only files (mark-two-tone, logo/proposed/, build_logo_proposed.py, wordmark_outline.py).
- docs/brand/tokens/tokens.json and tokens.css (regenerated): heading and wordmark family Cairo.
- docs/brand/*.md, brand.json, fonts/README.md, preview.html, preview-tenant-themes.html (regenerated): Seshna name, Cairo headings; tool messages say "Seshna Crimson/Coral".
- web/scripts/copy-tokens.mjs: copies favicon (ico, svg), apple-touch-icon, 192/512 and maskable icons into app and marketing `public/icons/` (gitignored).
- web/app: manifest icons (SVG, PNG 192/512, maskable), layout icons; pwa test; messages `pwa.name`/`shortName` = "Seshna" in en and ar.
- web/marketing: icons metadata; title "Seshna" in en and ar, wrapped in `<bdi>`.

## Checks
pnpm test (278), lint, typecheck, build: pass. check_docs, check_repo_hygiene, scan_secrets: pass. Brand tools: check_contrast, check_proposed, test_derive_tenant_theme, test_tenant_contrast, scripts/tests/test_build_brand_assets (29): pass.

## Decisions
- ADR-0066 (GOV-069, written in parallel). No new decision here; app-icon geometry (tile 14/64, mark 62%, maskable 50%) is INFERRED and listed in docs/brand/10-open-items.md.

## Tokens or cost
Unknown.

## Next step
- BRD-014 to done once both PRs merge (PLAN.md owned by GOV-069 session).
- Outside these paths, needs owners' rows: Alexandria in services/studio/static/index.html and the engine print-format font stack; scripts/build_brand_assets.py should use the small-size cut at 16 px and a 96 px minimum lockup.
- Web fonts are not loaded anywhere in web/ yet; self-hosting Cairo and Readex Pro WOFF2 needs its own row.
