# Session log: apply-founder-answers

Date: 2026-11-22
Author: eldon
Tool and model: claude-code. Opus wrote the ADRs and Sonnet made the readiness-order edits. Fable reviews.
Plan IDs: GOV-062, GOV-063

## Summary
Applies Eldon's founder answers recorded in #264: ADR-0059 for Q-560 and the sandbox rule, ADR-0060 for Q-292, and readiness order for Q-293. Stacked on #264.

## Files touched
- **docs/decisions/ADR-0059-draft-country-packs-in-sandbox.md:**
  - draft country packs may run in sandbox and test, with synthetic data only;
  - partly supersedes ADR-0034;
  - records the rest of the Q-560 policy for a later CMP row in the partner's lane.
- **docs/decisions/ADR-0060-role-assignments-in-regional-store.md:**
  - supersedes ADR-0007 item 9;
  - role assignments live in a regional store outside the tenant site;
  - security review is required before implementation.
- **docs/decisions/INDEX.md:** two rows added.
- **docs/architecture/country-packs.md, docs/architecture/phased-delivery-and-lanes.md, docs/strategy/market-pack-track-plan.md, docs/fundraising/investor-shortlist.md:** a fixed market order is replaced with readiness order (ADR-0024, ADR-0026). The GOV-039 capacity wording is corrected.
- **docs/specs/phase-exit-criteria.json:** aligned with GATES.md (G1-1, G1-2, G2-1, G3-4, E3-3).
- **docs/open-questions.md:**
  - Q-292 and Q-293 marked applied;
  - Q-560 points at ADR-0059.
- **docs/PLAN.md:** GOV-062 and GOV-063 marked done.

## Decisions
ADR-0059 and ADR-0060, both Accepted. Approved by Eldon, answering for both founders.

## Notes for the partner (not edited, partner lane)
- **country-pack-framework.md:66-72:** cite ADR-0059. The loader.py:26 comment "until Q-560 is answered" is now stale.
- **CMP-015:** "KSA, then UAE" implies a market order.
- **ADR-0039, ADR-0040 and role-and-permission-mapping.md:** they can now cite ADR-0060 instead of "blocked by Q-292".
- **Q-560 policy follow-ups:** adviser sources after accountant sign-off, the certification rule and the status-to-manifest check need a CMP row in the partner's lane.

## Tokens or cost
Unknown.

## Next step
The partner adds the CMP row for the Q-560 loader policy and updates the partner-lane citations above.
