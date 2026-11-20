# Session log: plt-014-factory-screens

Date: 2026-11-20
Author: eldon
Tool and model: claude
Plan IDs: PLT-014

## Summary
Built the staff-only component factory review screens (list by status, draft spec, test plan, risk class with reasons, generalisation, evidence per opaque tenant ref, history, attest/approve/reject through an injected port with a placeholder step-up). Text from models and tenants is shown as plain text only. Viewed the built static export at 375 and 1280 px: no horizontal overflow, list and detail swap on narrow screens, hostile fixture text displayed as text. Tier 2, screens only; the backend enforces.

## Files touched
- web/app/src/factory/: types, text safety, action model, fixtures, port, tests
- web/app/src/components/factory/: FactoryScreen, RequestDetail, ReviewActions, CSS module, tests
- web/app/src/app/(staff)/console/components/page.tsx: route
- web/app/src/console/access.ts, port.ts, components/console/ConsoleShell.tsx: factory permissions, audited view name, nav link
- web/app/messages/{ar,en}.json, web/app/README.md, docs/open-questions.md (Q-470 to Q-473), docs/PLAN.md (PLT-014 done)

## Decisions
- None new. Follows ADR-0047 (step-up placeholder, Q-471) and ADR-0048 (agents propose, humans decide).

## Tokens or cost
Unknown.

## Next step
Wire a real `FactoryReviewPort` through the gateway once a row exists (Q-472); add the action-bound step-up proof (Q-471, SEC-005); settle the staff-role mapping (Q-470). Native review of the Arabic strings (ADR-0033).
