# Session log: web-009-document-templates

Date: 2026-11-26
Author: eldon
Tool and model: claude-code
Plan IDs: WEB-009

## Summary
First slice of WEB-009: Settings > Document templates in web/app (tax invoice, quote, purchase order). Per template: logo placement, accent token, footer text; locked regions shown read-only; preview from fixture text; behind a port with an in-memory fake, no engine calls. Arabic and English strings, RTL tested.

## Files touched
- web/app/src/settings/documents/{port,controller,access}.ts: port, fake adapter, state, admin-only access
- web/app/src/components/settings/documents/: screen, CSS module, tests
- web/app/src/app/(app)/settings/documents/page.tsx, SideNav link, messages en and ar
- docs/PLAN.md: WEB-009 doing

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown.

## Next step
WEB-009 follow-ups: (1) partner lane, ERP-016: the engine branding input has no per-template logo placement or footer text, so a contract and the real adapter are needed before wiring live (UNVERIFIED whether the footer region may carry tenant text); (2) real logo from the WEB-007 asset once SEC-006 reports it clean; (3) live preview from the engine renderer instead of fixture text; (4) Arabic strings need native review (ADR-0033).

## Review fixes (#359, partner review at 352d6e25)
Claude Sonnet 5.5 for Eldon: footer kept as a locked last region on all three kinds with the tenant text as a bilingual slot inside it; the accent is no longer a text colour (primary text, contrast pairs added to check-contrast); the settings now mirror contract `branding.documentHeader` (tenant-wide `logoPosition`, `accentOnDocuments`, `footerText` {ar, en}), so follow-up (1) above is superseded; SessionProvider tests added for workspace switch and non-admin denial.
