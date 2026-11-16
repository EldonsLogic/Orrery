# Session log: review-tiers

Date: 2026-11-16
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: GOV-043

## Summary
Drafted ADR-0035 (Proposed): risk-tiered review, block only on defects, two rounds, larger PRs, logs for code PRs only, stay at the current gate, generated STATUS. Eldon agreed in chat; it changes approval gates, so the partner must agree through a recorded review.

## Files touched
- docs/decisions/ADR-0035-risk-tiered-review.md and INDEX.md: new, Proposed
- docs/PLAN.md: GOV-043 (doing); docs/STATUS.md regenerated

## Decisions
- ADR-0035 (Proposed). Mechanism for Tier 1 on a protected main is UNVERIFIED and left to the founders.

## Tokens or cost
Not measured.

## Next step
Partner reviews ADR-0035 and picks the Tier 1 mechanism. After acceptance: update AGENTS.md, RULES and the PR template; CI-generated STATUS.
