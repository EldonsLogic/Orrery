# web

Status: draft
Owner: eldon

Purpose: user-facing web code.

| Folder | Purpose | Design source |
|---|---|---|
| [marketing](marketing/README.md) | Public website | [docs/product/website.md](../docs/product/website.md) |
| [app](app/README.md) | The product app: one chat and role-based views | [docs/product/app-screens.md](../docs/product/app-screens.md) |

Design tokens: [docs/brand/tokens](../docs/brand/tokens/tokens.json). Theming and tenant branding: [theming](../docs/architecture/theming.md).

## Run locally (Node 20, pnpm via corepack)
```
corepack enable
pnpm -C web install --frozen-lockfile
pnpm -C web/app dev          # app, then open /preview
pnpm -C web/marketing dev    # marketing, /ar and /en
pnpm -C web lint && pnpm -C web test && pnpm -C web typecheck && pnpm -C web build
```
Stack and rules: [ADR-0022](../docs/decisions/ADR-0022-web-stack.md). Both apps are static exports with no server code and no API routes. Messages live in `<app>/messages/{ar,en}.json` (Arabic default).

## Structure
- `app/`, `marketing/`: Next.js (App Router, TypeScript strict). `app/theme/` is the plain-Node theme engine (BRD-005), outside the pnpm workspace; its tests run with `node --test web/app/theme/`.
- `scripts/`: `copy-tokens.mjs` (token copy) and `check-tokens-only.mjs` (rejects colour and font literals and physical-direction CSS; run by `pnpm lint`).

## Where tokens come from
`docs/brand/tokens/tokens.css` (generated, never edited by hand) is copied to `<app>/src/styles/tokens.generated.css` by `scripts/copy-tokens.mjs` before dev, typecheck and build. `tokens.proposed.css` (the accepted v1.1 layer, Q-70) is copied to `tokens.proposed.generated.css` and imported after it. The copies are git-ignored.

**Only the design-system preview page (`app` route `/preview`) exists.** Product screens come at gate G1 and later.
