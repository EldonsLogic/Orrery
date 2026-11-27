# Session log: gov-077-review-fixes

Date: 2026-11-27
Author: eldon
Tool and model: claude-code
Plan IDs: GOV-077

## Summary
Fixes for the partner's review of #374 at 4ae3621b. This log supersedes the counts in the first Summary and "For the partner" sections of `2026-11-26-eldon-claude-code-gov-077-remaining-questions.md`: at the first commit 31 rows were answered, 4 founder decisions and 17 research items were left open; later in that session all 4 founder decisions, 21 research items and strategy items 1, 2, 4 (in part), 5, 9, 10 and 12 were answered or partly answered, and the Q-8, Q-267, Q-552, Q-615 to Q-626 and Q-628 rows are no longer open research items.

- "Partner to confirm." restored on the 44 partner, shared and cross-lane rows where commit 5576e446 had replaced it with "(Eldon answered for both founders.)" (ADR-0032). The answers stay proposals until the partner reviews them.
- Access dates added to every ZATCA, UQN and IFRS URL. IFRS URLs were re-fetched on 2026-11-27 (Qatar profile URL added to Q-8). ZATCA and UQN dates are 2026-11-26, as recorded for the same manuals, and say so in each row; they are not a check done on 2026-11-27.
- SOQ-4 made consistent: one answer, status "Partly resolved" (LEG-010, LEG-011).
- Q-553: one active answer that keeps the fail-closed refusal of ERP-007's neutral print for UAE companies.
- Q-557: the Tool API refusal is tracked in OPR-021 (ERP-041 covers the importer and the adapter).
- Merged #372 (and through it #371) first; their fixes apply here.

## Files touched
- `docs/open-questions.md`, `docs/strategy/open-questions.md`, `docs/PLAN.md`: as above.

## Decisions
- None.

## Tokens or cost
Unknown.

## Next step
Partner re-reviews #371, #372 and #374 and marks each row confirmed, changed or rejected. Missing follow-up rows in the partner lane (Q-479 accent rule, Q-628 non-XML Box 5, Q-297 certification re-check) are his to add once he confirms.
