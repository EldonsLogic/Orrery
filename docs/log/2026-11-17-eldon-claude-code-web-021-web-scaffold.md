# Session log: web-021-web-scaffold

Date: 2026-11-17
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: WEB-021

## Summary
Wrote the web/ scaffold per ADR-0022 (pnpm workspace, Next.js app and marketing, Arabic-default i18n, token import, token-only checker, one preview page using the theme engine, web-checks CI job). Verified in CI only (the local npm registry was too slow to install): the first CI run created the lockfile, which I committed, then I fixed three first-run errors (CSS module typing, vitest JSX runtime, next-intl provider on the marketing site). The job now passes install from the frozen lockfile, lint, token check, typecheck, unit tests and build of both apps.

## Files touched
- web/: workspace, two Next.js apps, scripts, README
- .github/workflows/ci.yml: web-checks job (non-frozen install the first time, uploads the lockfile); .gitignore
- docs/PLAN.md: WEB-021 done; docs/open-questions.md: Q-119 to Q-121

## Decisions
- None. Deps pinned exactly: next 16.4.6, next-intl 4.15.1, react and react-dom 19.3.1 (MIT); typescript 5.9.3 (Apache-2.0); eslint 9.39.5, typescript-eslint 8.73.0, vitest 4.1.12 and type packages (MIT).

## Tokens or cost
Unknown or approximate, if known.

## Next step
Licence register entries for next and next-intl (LEG-004); WEB-019 once the Vercel project exists (INF-013); self-hosted fonts (BRD-011).
