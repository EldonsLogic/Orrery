# Session log: account-policy

Date: 2026-11-07
Author: eldon
Tool and model: claude-code
Plan IDs: GOV-029,PLT-002,WEB-018

## Summary
Set the policy of one personal GitHub account per founder (ADR-0023) and aligned the lane map, code owners, onboarding, rules and agent instructions. Recovered unmerged work (identity and web-stack proposals, both ADRs still Proposed) and re-committed it under the founder's account.

## Files touched
- scripts/lanes.json, .github/CODEOWNERS: one login per founder.
- AGENTS.md, docs/ONBOARDING.md, docs/RULES.md: several Claude sessions may share the one account, one at a time.
- docs/decisions/ADR-0023 and INDEX; docs/PLAN.md (GOV-029).

## Decisions
- ADR-0023: one personal GitHub account per founder.

## Tokens or cost
Unknown.

## Next step
Both founders review ADR-0007 (PLT-002) and ADR-0022 (WEB-018).
