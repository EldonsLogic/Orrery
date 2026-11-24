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
