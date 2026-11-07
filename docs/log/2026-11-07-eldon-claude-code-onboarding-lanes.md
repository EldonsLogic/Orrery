# Session log: onboarding-lanes

Date: 2026-11-07
Author: eldon
Tool and model: claude-code
Plan IDs: GOV-022,GOV-010,GOV-012,GOV-013

## Summary
Built the founders' onboarding into the repo so nothing has to be sent separately: one-time setup per founder, the lane split by paths, first tasks by owner, pending decisions with who records them, the working loop and what to do when blocked. Plan owners now follow the lanes.

## Files touched
- docs/ONBOARDING.md (new): setup, lanes, first tasks, decisions waiting, loop, blockers.
- AGENTS.md, docs/RULES.md (rule 47), docs/00-START-HERE.md, README.md: point to onboarding and the lanes.
- docs/PLAN.md: owners assigned where unassigned (Eldon: spine, product, brand; partner: engine, runtime, compliance); new row GOV-022 done.
- scripts/check_docs.py, scripts/check_repo_hygiene.py: ONBOARDING.md required and allowed.

## Decisions
- Initial lanes are a working agreement proposed in Eldon's session; either founder may re-assign owners in the plan through a PR. Gateway and control-plane lanes are decided at the start of G2.

## Tokens or cost
Unknown.

## Next step
Partner: do the setup, review ADR-0001..0018 (GOV-013), fill the model registry (GOV-012), then start CE-SEC-003 and LEG-004. Eldon: BPL-003, PLT-002, WEB-018.
