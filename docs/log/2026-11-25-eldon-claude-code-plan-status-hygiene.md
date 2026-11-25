# Session log: plan-status-hygiene

Date: 2026-11-25
Author: eldon
Tool and model: claude-code (Haiku 5.5, delegated subagent)
Plan IDs: GOV-072

## Summary
Closed Eldon rows whose work is merged (BPL-034, BRD-014, GOV-069); left four open with reasons. Added GOV-072 for this change.

## Files touched
- docs/PLAN.md: BPL-034, BRD-014 and GOV-069 set to done; GOV-072 row added after GOV-065 (done).
- docs/log/2026-11-25-eldon-claude-code-plan-status-hygiene.md: this log.

## Row evidence
- BPL-034 done: PR #247 (title "BPL-034: purchasing and price-list engine mapping", merged 2026-11-22). PR #281 was checked and is not the evidence: it is the partner's BPL-032 role-grant change.
- BRD-014 done: PR #298 and PR #305, both merged.
- GOV-069 done: PR #296, merged 2026-11-25.
- GOV-070 already `done` on main, no change.
- BPL-035 stays doing: PR #248 is merged, but its completeness and computed-authority tests are still purchasing-only (`services/blueprint/tests/test_engine_mapping.py`, the `test_purchasing_*` tests). `contracts/engine-mapping.md` says completeness is "tested for the purchasing example". The row's closing condition is not met. Bench checks for discount handling are also open.
- BPL-036 stays doing: PR #253 merged, but ADR-0057 still reads "Approved by: pending (partner review)" and four DECIDED rows wait on follow-up rows.
- GOV-060 stays doing: PR #263 merged, but ADR-0058 also reads "Approved by: pending (partner review)".
- SEC-009 stays doing: PR #270 is chat-side only. The gateway side (edge limits, T16, T12, PLT-009 wiring) is the partner's lane.

## Decisions
- None. Row GOV-072 omits the date from its text because AGENTS.md forbids calendar dates in plans.

## Tokens or cost
Unknown.

## Next step
Eldon or the partner decides whether ADR-0057 and ADR-0058 are approved, which would let BPL-036 and GOV-060 close. BPL-035 needs the completeness and computed-authority tests widened to every example, plus the discount bench check.
