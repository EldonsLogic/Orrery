# Session log: gov-077-remaining-questions

Date: 2026-11-26
Author: eldon
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: GOV-077

## Summary
Eldon asked for every remaining open question to be answered (2026-11-26). This session goes through the partner, shared and unassigned rows in `docs/open-questions.md` (Q-3 and Q-214 are skipped because they are handled separately) and the open items in `docs/strategy/open-questions.md`. Engineering rows get the safest option, consistent with AGENTS.md, the accepted ADRs and Eldon's answers in #370 to #372 and on #335, #336, #344 and #355. Founder decisions and research items are not edited; they go to Eldon as a separate list outside the repo. Stacked on #372.

Counts:
- `docs/open-questions.md`, 52 open rows: 31 answered with the safest option, 4 founder decisions (Q-9, Q-129, Q-295, Q-479) and 17 research items (Q-8, Q-11, Q-267, Q-552, Q-615 to Q-626, Q-628). None was already settled.
- `docs/strategy/open-questions.md`, 11 open items: 5 marked resolved (items 3, 6 and 11, plus items 4 and 8 in part), 4 founder decisions (items 1, 2, 10, and the entity part of item 4) and 3 research items (items 5, 9, 12).

## For the partner
Eldon's delegated answers to your rows (prefix `ANSWERED 2026-11-26 (Eldon, delegated to Claude Opus 5.5; safest option)`, ending "Partner to confirm."; owners unchanged). Please confirm or object on the PR:
- Partner-owned: Q-6, Q-15, Q-24, Q-26, Q-27, Q-176, Q-303, Q-310, Q-474, Q-475, Q-476, Q-477, Q-478, Q-515, Q-517, Q-550, Q-551, Q-553, Q-554, Q-555, Q-556, Q-557, Q-559.
- Shared (`both`): Q-135, Q-300, Q-309, Q-311, Q-516, Q-519, Q-558.
- Unassigned: Q-2 (answered, no confirmation line).
- Q-478 and Q-551 keep the fail-closed refusal until the market accountant approves a treatment. Q-555 restricts back-dated stock entries under Q-23.
- Your partner-owned accountant and ZATCA rows (Q-8, Q-267, Q-552, Q-615 to Q-626, Q-628) are left open as research items.

## Files touched
- `docs/open-questions.md`: 31 rows answered.
- `docs/strategy/open-questions.md`: items 3, 4, 6, 8 and 11 marked resolved or partly resolved, with evidence.
- `docs/PLAN.md`: GOV-077 (doing) and four partner `todo` rows from the answers: ERP-040 (pin manifest, Q-26), ERP-041 (stock and import input guards, Q-555 to Q-557), PLT-035 (gateway stream pass-through and caller context, Q-176 and Q-300 b), CMP-046 (UAE tax invoice mode, Q-553). Existing rows reused: ERP-038 (Q-475), ERP-039 (Q-311), ERP-032 (Q-558 d), INF-016 (Q-474).

## Decisions
- No ADR. The answers say "needs ADR" where one is needed (Q-309 event store, Q-27 v16 move, Q-516 recording, Q-519 downloads). Proposed ADRs they lean on (ADR-0039, ADR-0042, ADR-0043, ADR-0051, ADR-0052) stay Proposed.

## Tokens or cost
Unknown.

## Next step
Partner confirms or objects to his rows on the PR. Eldon takes the founder list. The research items go to the market accountant, counsel and official ZATCA, FTA and ETA sources.
