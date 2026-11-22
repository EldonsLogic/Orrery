# Session log: web-008-branded-login

Date: 2026-11-22
Author: eldon
Tool and model: claude-code
Plan IDs: WEB-008

## Summary
The /login/ page now shows tenant branding (logo, display name, derived primary in light and dark) with a platform fallback, through a typed TenantBrandingPort with a fake; authentication is still the WEB-017 placeholder.

## Files touched
- web/app/src/components/login/: branding.ts (untrusted-input checks, scoped CSS), fake.ts and fixture.json, BrandedLogin and its CSS, login.test.tsx
- web/app/src/components/auth/AuthShell.tsx, LoginForm.tsx, app/login/page.tsx: brand slot and tenant scope
- web/app/messages/{en,ar}.json: auth.login.platformName (Arabic unreviewed, ADR-0033)
- web/app/README.md, docs/PLAN.md (WEB-008 done)

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown.

## Next step
Real tenant token endpoint and identity wiring replace the fake and placeholder (PLT-005); login background asset and favicon; WEB-007 can reuse branding.ts sanitisers.
