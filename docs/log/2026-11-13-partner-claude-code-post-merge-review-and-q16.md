# Session log: post-merge-review-and-q16

Date: 2026-11-13
Author: partner
Tool and model: claude-code / opus-5.5
Plan IDs: GOV-008,GOV-036,BPL-028,BPL-029

## Summary
Post-merge cross-model review (Opus against the Sonnet author) of Eldon's merged PRs #44, #45 and #46, which the partner had approved verbally; review posted as PR comments, with a correction that the approval was given; open question Q-16 on recording approvals as GitHub reviews.

## Files touched
- docs/open-questions.md: added Q-16 (verbal approvals with no GitHub review on record, `main` protection requires checks but no approving review, whether a PR approval approves its ADRs, rows placed in the other founder's lane).

## Decisions
- None taken. The partner's position on the proposed ADRs, as posted on the PRs: changes requested on ADR-0027 (the human-floor limit would let an agent post to the ledger or file a tax return, against RULES 21; no security review) and ADR-0030 (the mapping drops role scope, and unmapped engine fields are visible by default); ADR-0028 approved; ADR-0029 approved pending counsel; ADR-0026 approved in principle after fixes (lane table contradicts section 2, Qatar shown as the first market although it is a hypothesis). The partner accepts ERP-021 and ERP-022. PLT-025, CMP-032 and ERP-023 are to be confirmed in a follow-up.
- BPL-028 independent check on paper: trial balance correct (1,150.00 each side). Fixes requested: opening-stock account, discount accounting setting, a credit note instead of cancel, a real mid-submit interruption case, the Owner approval step.
- Defect reported on #44: `scripts/phase_exit_check.py` accepts the other founder OR a different model; RULES 48 requires both. Reproduced locally.

## Tokens or cost
Unknown.

## Next step
Eldon answers the review comments on #44 to #46 and Q-16. Partner: get #39 (ERP-001) and #34 (CE-SEC-003) reviewed and merged, then ERP-021.
