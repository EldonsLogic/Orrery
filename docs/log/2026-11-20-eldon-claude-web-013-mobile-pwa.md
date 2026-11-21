# Session log: web-013-mobile-pwa

Date: 2026-11-20
Author: eldon
Tool and model: claude
Plan IDs: WEB-013

## Summary
WEB-013: mobile-responsive fixes (no horizontal scroll at 375 and 768 px, 44px touch targets, safe-area insets, dvh, logical CSS only) and installable web app metadata (manifest, theme-color from tokens, viewport-fit=cover). No service worker (Q-380). Viewed at 375 and 768 px in the built-in browser against a static serve of the build: chat and blueprint screenshots in Arabic RTL, plus a script check over home, onboarding, blueprint, console, login, records, preview (scrollWidth equals viewport, no control under 44px).

## Files touched
- web/app/src/styles/mobile.css: touch-target and safe-area variables, body reset
- web/app/src/app/layout.tsx, web/app/src/app/manifest.ts, web/app/src/pwa/manifest.ts: metadata, viewport, manifest from messages and tokens
- web/app/src/lib/viewport.ts: viewport classes; AppShell closes the drawer on leaving the narrow layout
- web/app/src/**/*.module.css: 44px targets, safe areas, 100dvh, panel width cap
- web/scripts/copy-tokens.mjs, web/.gitignore: brand app icon copied at build (ignored)
- web/app/messages/*.json: pwa strings; tests in lib/viewport.test.ts and pwa/pwa.test.ts
- docs/open-questions.md: Q-380 to Q-382; docs/PLAN.md: WEB-013 done

## Decisions
- No service worker until caching rules exist (Q-380); manifest icon is the existing SVG only (Q-381).

## Tokens or cost
Unknown.

## Next step
QA-014 accessibility audit; answer Q-380 to Q-382.
