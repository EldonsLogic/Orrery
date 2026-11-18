# web/app

Status: draft
Owner: unassigned

Purpose: the product app. One chat plus role-based views, approval inbox, Settings > Branding, login page, tenant-branded documents. Screens: [docs/product/app-screens.md](../../docs/product/app-screens.md). Tokens: [docs/brand/tokens](../../docs/brand/tokens/tokens.json). Theming: [theming](../../docs/architecture/theming.md). Every string through i18n; RTL from day one.

**Empty until gate G1.**

## Theme engine (BRD-005)
`theme/theme-engine.js` is the user theme preference (light, dark, system) with per-user persistence; see [theming](../../docs/architecture/theming.md). Run its tests with `node --test web/app/theme/` (Node 20, no packages).

## UI components (BRD-010)
`src/ui/` is the component library: Button, TextField, Select, Checkbox, Card, Badge, Alert, Spinner, Table, VisuallyHidden, Stack (import from `src/ui`). CSS Modules built only from brand tokens, logical properties only, no text inside components (every visible or aria string is a prop, so copy goes through i18n). It will move to its own package later. See every variant on the preview page, Components section.

## Auth and error pages (WEB-017, UI only)
`/login/`, `/reset-password/`, `/reset-password/confirm/`, `not-found.tsx`, `error.tsx` and `global-error.tsx`, built from `src/ui` and tokens, copy under the `auth` and `errors` message namespaces. The forms do no real authentication: they call typed placeholder handlers in `src/lib/authPlaceholder.ts` (fixed results, no network, no credential stored or logged) until PLT-005 (identity service). Failure wording never says whether an account exists. The reset-confirm page does not read a token yet; that arrives with PLT-005.
The Arabic strings for these pages are unreviewed (ADR-0033) and need a native-speaker review before use with customers.
Still open under WEB-017 / ERP-016: own emails (reset and notifications) and print formats; no engine template may reach a customer (ADR-0016).

## RTL checks (QA-008)
Deterministic layout checks, no screenshot baselines:
- `web/scripts/check-rtl-css.mjs` (part of `pnpm lint`, also `pnpm check:rtl`) fails on physical-direction CSS in `app/src` and `marketing/src`: `margin|padding|border-left|right`, `left|right`, `float`, `text-align: left|right`, physical radii, `translateX`, `scaleX`. Use logical properties. If a physical value is truly right (symmetric or always-LTR content), add `/* rtl-ok: reason */` on the same line or the line above; the reason is required.
- `src/ui/rtl.test.tsx` renders the components and the auth forms in `dir="rtl"` and `dir="ltr"` and asserts the root `dir`, no inline `left`/`right`, LTR numeric inputs, logical end alignment for numeric table columns, and that theme modes (per tenant) never change `dir`. The components have no icon mirroring hook yet, so none is tested; add one with the first directional icon.
- Real browser screenshot diffs are NOT done: baselines are images and cannot be committed (AGENTS.md). Open question Q-143 asks where to store them. Tenant-branded documents (print formats) are not covered until ERP-016 produces them.
