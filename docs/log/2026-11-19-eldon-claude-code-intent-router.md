# Session log: intent-router

Date: 2026-11-19
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: OPR-002

## Summary
Intent router: bilingual rules plus injected classifier port, safety combiner that resolves doubt to ask, mode never grants authority.

## Files touched
- services/operate/router/, tests/router, docs/architecture/intent-router.md

## Decisions
- None.

## Tokens or cost
Sonnet subagent, about 150k tokens.

## Next step
Open PR after OPR-001 (#190); Q-259, Q-260; real classifier later.
