# Session log: web-029-design-foundation

Date: 2026-11-26
Author: eldon
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: WEB-029

## Summary
First design pass, part 1 of 2: a shared design foundation for every app screen (type roles, spacing, radius, control sizes, breakpoints, page frame and a glass material for chrome), applied to the shared controls and the app shell. The owner home is part 2, stacked on this branch.

## Files touched
- docs/PLAN.md: new row WEB-029 (doing, eldon).
- docs/brand/tokens/tokens.json, tokens.css: card radius 12 to 14 px, as the Seshna design system states (regenerated with build_tokens_css.py).
- web/app/src/styles/foundation.css (+ test): roles defined once (label, body-strong, KPI numeral 32/40 with Arabic 48, fluid display and h1 only, measure), radius per role, control sizes 32/40/48 and icon sizes, breakpoints 375/768/1024/1440, page max 1280 with fluid padding 16/24/32/48, glass variables (solid by default, translucent only under @supports backdrop-filter, solid again for reduced transparency or more contrast), html base size.
- web/app/src/ui/Button, control, Card, Badge CSS: sizes sm 32, md 40, lg 48 with a padded 44 px hit area on coarse pointers, icon size per size, inputs at the md height, cards 24 px padding from tablet up, badges pill.
- web/app/src/components/shell: glass sticky top bar and side navigation, the Seshna lockup built at build time from docs/brand/logo/lockup-primary.svg with token colours (BrandLockup.tsx), a phone dock with "Ask Seshna" always one tap away (safe-area aware), page frame, solid drawer, account name isolated in mixed-direction text.
- web/package.json: lint copies the tokens first, so check-css-vars sees the accepted v1.1 tokens in CI as it does locally.

## Decisions
- Glass departs from the design system's "flat, no shadows" rule at Eldon's request (chrome and overlays only, never content). The brand docs need an update; Eldon will handle it.
- Breakpoint and rem tokens: media queries cannot read variables, so the breakpoints are reference values in foundation.css; token sizes stay px because the token generator emits px (rem output is a generator change, not done here).
- Icon-rail sidebar at about 1024 is not built: the brand has no general icon set yet. Between 769 and 1023 the sidebar narrows instead.

## Checks
pnpm lint, typecheck, test (357 vitest + 135 node), next build, theme engine tests, check_docs, check_repo_hygiene, check_proposed: all pass. Screenshots at 375/768/1024/1440, EN and AR, light and dark, kept outside the repo.

## Round 2 (review feedback, same session)
- Merged origin/web-028-self-host-fonts (#320) so the preview renders Cairo and Readex Pro; #366 is now stacked on #320. Verified in the browser: both faces load, h1 computes to Cairo.
- Company switcher (initial avatar, name, chevron, listbox in a glass popover, keyboard), round avatar for the account menu, visible language switch (عربي / English) beside it, icon menu button on phones.
- Side navigation: full-height glass column with sticky, self-scrolling content; Lucide icons (lucide-react 1.75.0, ISC, recorded in docs/legal/licence-register.md) as placeholders; current item tinted with a 2px start-edge indicator; Seshna mark and build stage at the bottom (membership fixture gained buildState).
- ProgressMarks: visible status word under each step (Done / In progress / Not started), a connecting line solid Cobalt up to the current step and dashed muted after it; marks unchanged (upper half solid for the current step, never mirrored).
- Foundation: glass alpha 66% light / 58% dark with blur 24; `--page-band` (flat 4% Cobalt tint) and `--main-pad-block`; main is the size container.

## Tokens or cost
Not measured.

## Next step
WEB-029 part 2 (owner home, stacked PR), then one PR per screen on this foundation.

## Addendum: no flash on refresh (Eldon bug report 2026-11-26)
- web/app/src/lib/firstPaint.ts: a blocking inline script in the root layout head sets data-theme (engine bootScript), lang and dir from localStorage before paint; when the saved locale is not Arabic it adds `locale-pending` (CSS hides the body) and the provider removes it once the locale is applied, with a 1.5 s safety timeout in script and provider. No CSP exists in web/app/vercel.json, so nothing was weakened; a future CSP needs the hash of firstPaintScript(). Playwright on the static export (dark OS, saved English and light): at 50 ms body hidden with light theme, at 500 ms English ltr light, no dark or Arabic frame. lint, tsc, vitest and next build pass.

## Addendum: partner review fixes (round 3)
- Glass fill is 88% of the surface in both themes (was 66/58%); check-contrast.mjs now reads muted and control-border tokens from tokens.proposed.css and checks text, muted text and icons on glass over white and black backdrops (worst case >= 5.5:1), plus control borders (3:1) and the active option ring.
- Popovers and the account panel are solid (no glass on glass, no translucent Badge); the specular box-shadow (--glass-highlight) is removed; nav offset and top bar share --shell-bar-height; both languages stay on phones with a 44px target; one breakpoint (width > 48rem); select and active language borders use --color-border-control; bdi on workspace and user names; narrow-phone progress marks show the state line only for the current stage.
