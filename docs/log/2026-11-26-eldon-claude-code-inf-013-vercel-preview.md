# Session log: inf-013-vercel-preview

Date: 2026-11-26
Author: eldon
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: INF-013

## Summary
Turns on Vercel deploys for `web/app`, with explicit install, build and output settings, so each PR gets a preview link.

## Files touched
- web/app/vercel.json:
  - `framework`: nextjs.
  - Install runs at the pnpm workspace root (`web/`) with the frozen lockfile.
  - `buildCommand`: `pnpm build` (copy-tokens, then next build).
  - `outputDirectory`: `out` (static export).
  - `git.deploymentEnabled`: true.
- `web/marketing/vercel.json` is unchanged and stays disabled.

## Decisions
- Earlier Vercel attempts failed on every push, and the setup was paused. The likely cause was default settings that did not fit the pnpm workspace and `docs/brand` token copy. This PR states those settings explicitly.
- Checked from a fresh clone of main:
  - `pnpm install --frozen-lockfile` in `web/` passes.
  - `pnpm build` in `web/app` passes and writes the static export to `out/`.
  - The output has 0 engine-name hits (frappe, erpnext).
- Founder steps in Vercel:
  - Project `seshna-app`, root directory `web/app`.
  - "Include files outside the root directory" stays on.
  - Deployment Protection turned on for previews (ADR-0018: previews are not public; synthetic data only).

## Tokens or cost
Unknown.

## Next step
Once Eldon confirms the project exists and the first preview is green:
- mark INF-013 done;
- WEB-019: design-system pages;
- QA-017: preview smoke check with no engine markers.
