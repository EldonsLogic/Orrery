# ADR-0032: Approval is a recorded GitHub review

Status: Accepted
Owner: partner
Approved by: both founders. Eldon's answer to Q-17 was posted on PR #48 on 2026-11-14 at his instruction. The partner accepted it when asking for it to be recorded (log `2026-11-14-partner-claude-code-gov-040-founder-answers.md`).

## Context
PRs #44, #45 and #46 were approved verbally in a working session and merged by their author with a relayed-approval comment, so no review is on record (Q-17). Those PRs carried ADR-0026 to ADR-0030, which stayed Proposed. They also put plan rows in the other founder's lane without explicit agreement on those rows. The repo already says nobody merges their own PR without the other founder's review (AGENTS.md), but nothing enforces it or says what counts as approval.

## Decision
1. **Branch protection.** `main` requires one approving review and a code-owner review before merge, in addition to the status checks.
   - `.github/CODEOWNERS` lists both founders for every path.
   - GitHub does not count an author's approval of their own PR, so in practice the other founder approves.
2. **Approval means a GitHub review.** A verbal or chat approval does not approve a PR.
   - It also does not accept an ADR inside one. An ADR becomes Accepted only when its "Approved by" line names the approving review or the log that records the founders' answer.
3. **Rows in the other founder's lane.** A plan row placed in the other founder's lane is a proposal until that founder accepts it in a review.

## Alternatives rejected
- **Keep checks-only protection and rely on the written rule.** #44 to #46 show the rule alone is not followed under time pressure.
- **Accept verbal approvals logged afterwards.** They leave no record that ties a specific diff to the approver.

## Consequences
- A repository admin turns on the protection settings in GitHub. This session could not read the current protection (the API returned 404, which fits either no protection or no admin rights), so the current state is UNVERIFIED.
- Merges wait for the other founder's review. This is slower, but every merge has a record.
- ADR-0026 to ADR-0030 stay Proposed until a review or a recorded founder answer accepts each one.
- The rows put in the other founder's lane by #44 to #46 (PLT-025, CMP-032, ERP-023) are proposals until that founder accepts them in review.

## Supersedes
None.
