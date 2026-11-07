# ADR-0022: Web stack for the marketing site and the app

Status: Proposed
Owner: eldon
Approved by: pending (Eldon to approve; partner review pending). Proposal written for WEB-018, log 2026-11-07-eldon-claude-code-web-stack-adr.

## Context
WEB-018 asks for the web stack before any screen is built. ADR-0018 (Proposed) already picks Vercel for per-PR previews, and says the first thing hosted is the design-system preview pages, then clickable chat screens. Fixed constraints:
- Arabic first, right-to-left from day one, Arabic and English equal; every string through i18n (AGENTS.md principle 4).
- Tokens only, light and dark themes, tenant overrides of a whitelist of tokens (ADR-0014, [theming](../architecture/theming.md)).
- The engine is invisible (ADR-0016): the browser talks only to our app and gateway.
- Production customer data stays in-country (ADR-0006). Vercel regions are unchecked and no Gulf or Egypt region is assumed (UNVERIFIED).
- Two founders working mostly through AI agents: the stack must be one that agents write well, with one language across front end and tooling where possible.
- Hijri and Gregorian date entry, Eastern Arabic digits, bidi-safe mixed text (WEB-016, [calendars-and-locale](../architecture/calendars-and-locale.md)).

## Decision
PROPOSED, recommended: **one TypeScript and React stack for both the marketing site and the app, on Next.js**, in one small workspace under `web/`.
1. **Framework: Next.js (App Router) with React and TypeScript in strict mode**, for both `web/marketing` and `web/app`. One stack means shared tokens, i18n, components and tests, and the best fit with Vercel previews.
2. **Rendering by surface.** Marketing: static generation, fully cacheable, no customer data. App: the browser renders tenant screens and calls our in-country gateway directly; the Next.js server holds no tenant data and does not proxy business data. This keeps Vercel usable for previews (synthetic data only) and lets production serve the app as static files or a standalone Node container from an in-country host. Where production runs is decided with hosting (INF-001).
3. **Styling: plain CSS with CSS custom properties from `docs/brand/tokens` (CSS Modules per component).** No utility framework with its own colour palette, so a hard-coded colour cannot slip in; a lint rule rejects hex, rgb and font-family literals outside the token files. Logical properties only (`margin-inline-start`, not `margin-left`), so RTL needs no mirrored stylesheet.
4. **Components: an accessible headless primitive library (Radix UI primitives, MIT, UNVERIFIED until LEG-004) with our own styling.** Direction set once at the root (`dir="rtl"` or `ltr` from the locale).
5. **i18n: ICU message format with `next-intl` (licence UNVERIFIED until LEG-004).** Arabic is the default locale; locale in the URL path for marketing (`/ar`, `/en`), from the user setting in the app. Numbers, currency and dates through `Intl` with explicit numbering system; Hijri display through a vetted Umm al-Qura library chosen in CMP-022 (Q-12), never hand-written.
6. **Fonts: self-hosted** (no third-party font CDN at runtime), as licensed in BRD-011.
7. **Quality tools: pnpm workspace, ESLint, Prettier, Vitest for units, Playwright for end-to-end and RTL screenshot goldens (evals/README "RTL checks"), axe checks for accessibility.** Exact versions are pinned in the lockfile when the workspace is scaffolded; no version is chosen in this ADR.
8. **Order of work:** design-system preview pages first (tokens, type, colour, RTL and dark samples), then clickable chat screens with fixture data, then real screens once identity (ADR-0007) and the gateway exist.

## Alternatives rejected
- **Astro for marketing plus Next.js for the app.** Astro ships less JavaScript for content pages, but two frameworks double the tooling and component work; revisit only if marketing page speed fails a budget.
- **SvelteKit or Nuxt (Vue).** Good frameworks, smaller hiring and agent-training pool than React, and the accessible-primitive and i18n ecosystems we need are thinner in Arabic RTL use (UNVERIFIED, judgement).
- **The engine's own desk UI or its Vue UI kit.** Breaks engine invisibility (ADR-0016) and ties the product to the engine we want replaceable (ADR-0002).
- **A utility CSS framework (for example Tailwind).** Fast to write, but its default palette and arbitrary values make "tokens only" hard to enforce; possible later if configured to expose tokens only.
- **Server-rendering tenant pages on Vercel.** Simplest code, but tenant data would be processed outside the country.
- **React Native or a native mobile app first.** Not needed before G3; WEB-013 covers a responsive, installable web app.

## Trade-offs
- Next.js is heavier than a static site generator and moves fast; upgrades need care. Mitigation: App Router only, few framework-specific features in the app, pinned versions, Dependabot.
- Client-rendered tenant screens mean a larger first load and more care with auth tokens in the browser (short-lived, per tenant, per ADR-0007).
- Plain CSS with tokens is more typing than a utility framework; the lint rule is the price of keeping branding safe.

## Consequences
- If accepted: a new plan row (to be added on acceptance) scaffolds `web/` (workspace, token import, i18n, lint rules, one preview page); the founders connect the Vercel project (INF-013); WEB-019 then hosts the design-system preview pages. Until the Vercel project exists, previews are local only (`pnpm dev`); the agent stops and asks for the project, as ADR-0018 requires.
- New libraries are added to the licence register (LEG-004) before first use.
- CI gains a web job (lint, type check, unit tests, build) when `web/` has code.

## Supersedes
none
