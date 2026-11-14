# Session log: gov-040-founder-answers

Date: 2026-11-14
Author: partner
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: GOV-040

## Summary
Recorded the founders' answers to Q-17, Q-18 and Q-19 from the PR #48 comment: ADR-0031 accepted, new ADR-0032 accepted. Applied Eldon's review of #48 and merged main.

## Files touched
- `docs/decisions/ADR-0031-rigid-zone-code-authorship.md`: Proposed → Accepted (reading A).
  - The four conditions are now exactly the founders': official vectors, line-by-line human review, accountant review of tax maths before Phase 2, and a logged model and prompt.
  - Different-model review and one calculation authority are listed as rules that also apply.
  - The #43 paragraph is marked as history, ADR-0030 is marked Proposed, and the schema's `rigid` "never AI-written" description is added to the follow-ups.
- `docs/decisions/ADR-0032-approval-is-a-recorded-review.md`: new, Accepted (Q-17).
  - Covers required review and code-owner review on `main`, approval as a GitHub review only, and rows in the other's lane as proposals.
- `docs/decisions/INDEX.md`: ADR-0031 Accepted, ADR-0032 added.
- `docs/open-questions.md`:
  - Q-17 and Q-18 are struck as resolved, with their ADRs.
  - Q-19 is marked ANSWERED and stays open until Eldon's contracts-lane ADR and schema change.
  - With the decision recorded, Q-18 no longer opens with a proposed answer. It now leads with the decision and then gives both readings as they were.
- `docs/PLAN.md`: new row GOV-040 (partner, G0), so this work has its own row instead of reusing Eldon's GOV-008 and the BPL rows.
- `docs/log/2026-11-13-...-post-merge-review-and-q16.md` renamed to `...-q17-q19.md`, because it adds Q-17 to Q-19, not Q-16. The log is new in this unmerged PR.
- Merged `origin/main` (no rebase, no force-push).
  - Resolved `docs/open-questions.md`: kept main's Q-15, Q-16 and Q-21 to Q-27 plus this PR's Q-17 to Q-19.
  - Regenerated `docs/STATUS.md`.

## Checks
- `gh api .../branches/main/protection` returned 404, so the current protection state is UNVERIFIED (no protection, or no admin rights).
- A repository admin turns on the ADR-0032 settings.

## Decisions
- ADR-0031 and ADR-0032 record the founders' answers. This session decided nothing new.

## Tokens or cost
Unknown.

## Next step
- Eldon reviews #48.
- A repo admin enables required reviews on `main`.
- Eldon writes the Q-19 contracts ADR.
- #43 meets ADR-0031's conditions: a named reviewer and a logged prompt.
