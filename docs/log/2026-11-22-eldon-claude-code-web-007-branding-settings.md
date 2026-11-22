# Session log: web-007-branding-settings

Date: 2026-11-22
Author: eldon
Tool and model: claude-code
Plan IDs: WEB-007

## Summary
Branding settings screen (`/settings/branding/`): primary colour picker and hex field, live light and dark preview, AA pass/fail table per pair from a TypeScript port of the BRD-006 derivation (parity-tested against `docs/brand/tools/derive_tenant_theme.py`), owner and general manager only, save and logo upload through a typed port with a fake. Logo upload is raster-only and never rendered: the SEC-006 sanitiser and scan are not built, so SVG is refused and the logo stays pending until SEC-006 reports it clean.

## Files touched
- web/app/src/settings/branding/: colour.ts (port of derive, primary path only; accent and status warnings not ported), colour.data.json (base colours, checked against tokens.json), port.ts (typed port, fake, logo limits), access.ts (permission through Blueprint scope), tests
- web/app/src/components/settings/branding/: BrandingScreen.tsx, css module, SSR tests
- web/app/src/app/(app)/settings/branding/page.tsx; SideNav.tsx (nav link for permitted callers); messages ar and en (`branding`, `shell.nav.branding`)
- docs/PLAN.md: WEB-007 done

## Decisions
- Colour data lives in a JSON file so the tokens-only gate (TS and CSS scan) stays unchanged; no gate weakened.
- Server must re-run the derivation and re-check permission; the client result is feedback only.

## Tokens or cost
Unknown.

## Next step
Real gateway adapter for the port and SEC-006 logo pipeline (then show the logo); WEB-008 login branding can reuse `derive`; port accent support if the screen needs it.

## Review follow-up (Fable, #278)
- Fixed: hex field text keypad with pattern (M1); Save off until load succeeds, error and no overwrite on failure (M2); locale-aware ratios and caption in messages, dropped unused keys (L3); file name through `plainText` (L4); one status line instead of a live preview region (L5); preview link is a span (L6); own "Result" header and Card label (L7).
- Open follow-ups: make the tokens-only gate scan `.json` with a named allowlist (L1, gate untouched here); a sample per reject code and compare reject reasons in the parity test, and check white and Carbon against tokens.json (L2); use a border token if one is added (L8).
