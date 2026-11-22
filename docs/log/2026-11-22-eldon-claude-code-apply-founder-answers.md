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
  - records the rest of the Q-560 policy as proposed CMP rows for the partner to accept in review;
  - the status-to-manifest rule applies in production only (the manifest schema refuses `draft` for tax components);
  - "synthetic data only" is the caller's duty, not a loader check.
- **docs/decisions/ADR-0060-role-assignments-in-regional-store.md:**
  - supersedes ADR-0007 item 9;
  - role assignments live in a regional store outside the tenant site;
  - Proposed: decided by Eldon, becomes Accepted after a security review by a different model or founder (RULES 42).
- **docs/decisions/INDEX.md:** two rows added (ADR-0059 Accepted, ADR-0060 Proposed).
- **docs/architecture/country-packs.md, docs/architecture/phased-delivery-and-lanes.md, docs/strategy/market-pack-track-plan.md, docs/fundraising/investor-shortlist.md:** a fixed market order is replaced with readiness order (ADR-0024, ADR-0026). The GOV-039 capacity wording is corrected.
- **docs/specs/phase-exit-criteria.json:** aligned with GATES.md (G1-1, G1-2, G2-1, G3-4). E3-3 is left as on main: Q-293 did not cover it.
- **docs/open-questions.md:**
  - Q-293 marked applied; Q-292 DECIDED, pending the ADR-0060 security review;
  - Q-560 points at ADR-0059 and says the answer was given for both founders.
- **docs/PLAN.md:** GOV-062 and GOV-063 marked done; GOV-065 added (todo): the Tool API ADR for section 4 step 2 wording.
- **docs/fundraising/investor-shortlist.md:** the basis line notes the fit scores were not re-judged.

## Decisions
ADR-0059 Accepted (Q-560) and ADR-0060 Proposed pending security review (Q-292). Both decided by Eldon, answering for both founders, recorded in docs/log/2026-11-22-eldon-claude-code-founder-answers.md; the partner's review of this PR is the second founder's record (ADR-0032 item 2).

## Notes for the partner (not edited, partner lane)
- **country-pack-framework.md:66-72:** cite ADR-0059. The loader.py:26 comment "until Q-560 is answered" is now stale.
- **CMP-015:** "KSA, then UAE" implies a market order.
- **ADR-0039, ADR-0040 and role-and-permission-mapping.md:** once ADR-0060 is Accepted after its security review, they can cite it instead of "blocked by Q-292".
- **Q-560 policy follow-ups (proposals, ADR-0032 item 3):** adviser sources after accountant sign-off, the certification rule, the production-only status-to-manifest check, and documenting the caller's synthetic-data duty for `sandbox` and `test`.
- **ADR-0060 security review:** who may write to the store, `syncVersion` integrity, per-tenant keying, deny on outage.

## Tokens or cost
Unknown.

## Next step
The partner adds the CMP row for the Q-560 loader policy and updates the partner-lane citations above.
