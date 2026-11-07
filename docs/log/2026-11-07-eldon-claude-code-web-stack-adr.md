# Session log: web-stack-adr

Date: 2026-11-07
Author: eldon
Tool and model: claude-code (account Eldonham, cloud session)
Plan IDs: WEB-018

## Summary
Wrote the web stack proposal for founder approval (ADR-0022, Proposed): one TypeScript and React stack on Next.js for marketing and app; static marketing; app screens rendered in the browser against our in-country gateway so no tenant data is processed on Vercel; plain CSS with token custom properties and a lint rule against literal colours and fonts; logical properties for RTL; headless accessible primitives; ICU i18n with Arabic default; self-hosted fonts; Playwright RTL goldens.

## Files touched
- docs/decisions/ADR-0022-web-stack.md (new, Proposed); docs/decisions/INDEX.md.
- docs/PLAN.md: WEB-018 doing (done when both founders accept).

## Decisions
- None taken. Library licences are UNVERIFIED until LEG-004 records them.

## Tokens or cost
Unknown.

## Next step
Eldon and partner: accept or amend ADR-0022. On acceptance add a scaffold row for `web/`, then INF-013 (founders create the Vercel project) and WEB-019.
