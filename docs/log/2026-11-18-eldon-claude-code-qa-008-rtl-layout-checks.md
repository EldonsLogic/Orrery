# Session log: qa-008-rtl-layout-checks

Date: 2026-11-18
Author: eldon
Tool and model: claude-code
Plan IDs: QA-008

## Summary
RTL layout checks without image baselines (the repo forbids committed images): a CSS scanner for physical left/right in lint, and vitest tests rendering ui components and auth forms in rtl and ltr, incl. tenant theme not changing direction. Real screenshot diffs stay open (Q-143). Sonnet subagent built it; I reran lint and 13 node plus 60 vitest tests.

## Files touched
- web/scripts/check-rtl-css.mjs (+test), web/package.json, web/app/src/ui/rtl.test.tsx, web/app/README.md
- docs/open-questions.md (Q-143), docs/PLAN.md (QA-008 stays doing: screenshots and branded documents open)

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Decide where baselines live (Q-143); branded documents after ERP-016.
