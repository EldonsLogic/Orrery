# Session log: opr-009-change-by-chat

Date: 2026-11-19
Author: eldon
Tool and model: claude
Plan IDs: OPR-009

## Summary
Built `services/operate/change/` (OPR-009): a router `change` request becomes a validated, diffed, risk-classified Blueprint change proposal with a digest-bound preview; applied only after a confirmation bound to that digest (expiry, stale base, replay, tamper and superseded proposals refused), through the injected Blueprint path port. 45 new tests (English, Arabic, hostile drafts, ledger/stock/roles refusals); operate suite 400 passed.

## Files touched
- services/operate/change/ (edits, service, preview, store, models, errors), services/operate/tests/change/, services/operate/README.md
- docs/PLAN.md (OPR-009 done), docs/open-questions.md (Q-280 to Q-282)

## Decisions
- Chat applies up to R2 only; R3/R4 and ledger/tax/permission areas go to Studio review (Q-280). Tier 3 change (agent authority).

## Tokens or cost
Unknown or approximate, if known.

## Next step
Wire the real drafter and `BlueprintPort` to the change engine propose/apply path, and the host confirm card (Q-281, OPR-005, OPR-010).
