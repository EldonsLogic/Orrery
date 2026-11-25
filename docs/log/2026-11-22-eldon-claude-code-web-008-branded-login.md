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

## Review fixes (partner review of 75d14db1)
- High: login form is `method="post"` with a fixed `action="/login/"`; email, password and submit stay disabled until the client has mounted, so a failed hydration cannot send credentials in a GET query string. CSRF protection is left for when identity is wired (PLT-005); noted in a code comment.
- Medium: the real login takes the tenant from the host only (ADR-0007) through `tenantFromHost` and a local synthetic host map; the gateway will validate it later (PLT). The query-driven fixture choice moved to `/login/preview/`, off unless `NEXT_PUBLIC_LOGIN_PREVIEW=1`, noindex, dev only.
- Medium: branding checks use the rendered colours in light and dark: button label on fill, hover and pressed; primary link and focus ring on the card surface (read from docs/brand/tokens). Hover, pressed and label tokens are now required. Button uses `--color-primary-label`, `-hover`, `-pressed`; `check-contrast.mjs` reads the same tokens. `next.config.mjs` sets the bundler root to the repo root for the read-only tokens.json import.
- Low: tenant name and headline carry `lang` and `dir` of the locale actually shown.
