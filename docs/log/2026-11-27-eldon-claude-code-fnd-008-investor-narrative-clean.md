# Session log: fnd-008-investor-narrative-clean

Date: 2026-11-27
Author: eldon
Tool and model: claude-code (Claude Sonnet 5.5)
Plan IDs: FND-008

## Summary
Replaces PR 347, whose history contains investor-audience pitch text that must not be in the public repo. This branch starts from main and carries the same intended changes without that text. Adds plan row FND-008, the FND-004 dependency on it, the website content draft (a side output of FND-008, without the pitch section), and an open question on the shared-path review rule.

## Files touched
- docs/PLAN.md: new row FND-008 (eldon, G1, todo); FND-004 now depends on FND-008.
- docs/gtm/seshna-website-content-v1.md: website draft, pitch section removed, marketing claims labelled UNVERIFIED, owner line says side output of FND-008.
- docs/open-questions.md: Q-689 (review rule for shared paths).
- this log.

## Decisions
- The investor narrative lives outside the repo (AGENTS.md). PR 347 is closed, its branch is kept.

## Tokens or cost
Unknown.

## Next step
Partner reviews; then build the narrative outside the repo.
