# Session log: plan-status-partner-rows-2

Date: 2026-11-22
Author: partner
Tool and model: claude-code (Claude Opus 5.5, coordinator)
Plan IDs: CMP-034,GOV-055,CMP-028,CMP-029,CMP-031,ERP-029,SEC-022,BPL-032

## Summary
Judges eight partner rows whose PRs merged but which were still `doing`. Five move to `done`; three stay `doing` with the open item recorded. Only status cells change.

## Files touched
- `docs/PLAN.md`: `doing` to `done` for CMP-034, CMP-028, CMP-029, CMP-031 and SEC-022. No other row, column or owner changed.

## Decision table
| Row | Merged PR(s) | Decision | Evidence, or what remains |
|---|---|---|---|
| CMP-034 | #259 | done | The loader gate is on main. Production refuses a pack below `certified` or `regulated`, refuses any evidence except `verified_official`, and refuses `testOnly`. Eldon approved it with a line-by-line read; 23 tests. The Q-560 answer (agreed by both founders) is follow-up work on its own row, CMP-035. |
| GOV-055 | #254 | doing | The CI reviewer check is on main. Remaining: the engine/apply eligibility check or compiled-artifact certification binding, which waits on Q-297. |
| CMP-028 | #256, #267 | done | The row asks for the Egypt pack, and `country.eg` 0.1.0 is on main at `tested` with `unverified` evidence, sources in `evidence.json`. Eldon approved it with a line-by-line read. Not part of this row, but needed before the pack leaves `tested`: accountant and counsel confirmation (Q-11, Q-198, Q-200, Q-201, Q-215), native Arabic review, and certification under CMP-035. |
| CMP-029 | #257, #267 | done | The row asks for UAE and KSA packs on the framework, and `country.ae` and `country.sa` 0.1.0 are on main at `tested`. Eldon approved both with line-by-line reads. Go-live blockers are recorded in `evidence.json`: ZATCA Phase 2, UAE e-invoicing from 2027-01-01, and Q-23/Q-555. Q-559 (pack vs Blueprint e-invoicing mode) is open. Accountant and Arabic sign-off and CMP-035 are needed before leaving `tested`. |
| CMP-031 | #255, #267 | done | The row asks for the Qatar pack, and `country.qa` 0.1.0 is on main at `tested`. Eldon approved it with a line-by-line read. Before leaving `tested`: the Q-202 accountant check that no VAT is in force, a source for the CR pattern, week start, timezone and currency, Arabic review, and CMP-035. |
| ERP-029 | #260, #266 | doing | The offline reconciler, journal and tests are on main. The row is about having reconciliation in place before OPR-004 and OPR-007 enable a live handler, and none of the six gates in section 7 of `docs/architecture/action-outcome-reconciliation.md` is met yet: (1) a real `read_engine_state` tested on the bench with a fenced `not_applied`; (2) a scheduled run with operator paging; (3) stuck outcomes in the OPR-007 inbox; (4) Q-558 (a) to (c) answered, with (d) agreed and built under ERP-032; (5) ADR-0041 tenant-database storage; (6) an external head anchor and a MAC on ERP-023 audit rows. |
| SEC-022 | #235, #252, #258, #261, #262 | done | Adapter roles and workflow states are namespaced, and collisions with built-ins are refused, case-insensitively, after normalisation. `test_04b` asserts namespaced mappings and has no `expectedFailure`; it passed live on the mapped-only fixture (#252 log). ADR-0051 is written, and the security reviews were by different models (Opus, Gemini, and Eldon's Fable reads). Eldon's link-target policy point is decided: keep the 3-type direct-path set (#262). ADR-0051 is still Proposed, and the row asks for an ADR, not its acceptance. A Low follow-up (refusing unknown pointer roots) is in its own PR. |
| BPL-032 | #235, #252, #258, #261, #262 | doing | `role.upsert` now writes the mapped grants, and hidden or read-only field permissions apply. `test_06` and the field-level probe passed live on the mapped-only fixture (#252), and the `test_06` tripwire is removed. Remaining: the trading fixture's purchasing and price-list grants (Supplier, Price List, Purchase Order, Purchase Receipt, Purchase Invoice) are still refused until BPL-034 (contract PR #247, open) merges. Then the entities go into `ENTITY_TO_DOCTYPE`, `test_01b`, `test_02` and `test_03` are ungated, and the full fixture is run live. |

## Decisions
- None new. This records statuses only.

## Tokens or cost
Unknown.

## Next step
- **BPL-032:** ungate after #247 merges.
- **ERP-029:** complete the section 7 gates before OPR-004 or OPR-007.
- **GOV-055:** waits on Q-297.
