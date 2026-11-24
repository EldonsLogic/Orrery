# Session log: web-012-first-run-onboarding

Date: 2026-11-20
Author: eldon
Tool and model: claude
Plan IDs: WEB-012

## Summary
Built the first-run onboarding screens (five steps: welcome, interview, documents, review, ready) at /onboarding/ in web/app, ar and en, tokens only, UI-only with no data or auth. Reran lint, 241 vitest, typecheck and build: all pass.

## Files touched
- web/app/src/lib/onboarding.ts: pure step model
- web/app/src/components/onboarding/: OnboardingFlow, CSS module, tests
- web/app/src/app/(app)/onboarding/page.tsx: route
- web/app/messages/{en,ar}.json: onboarding strings
- docs/PLAN.md: WEB-012 done

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Not measured.

## Next step
Link the guide from the help menu and first login once the identity service (PLT-005 follow-up) can say who is new (WEB-011).
