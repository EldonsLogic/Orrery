# Session log: founder-answers

Date: 2026-11-22
Author: eldon
Tool and model: claude-code (Claude Opus; the questions were prepared by Opus and Fable review agents)
Plan IDs: GOV-061, GOV-062

## Summary
Eldon answered founder questions one at a time in chat. The answers are written into `docs/open-questions.md`.

## Files touched
- `docs/open-questions.md`:
  - Q-560, Q-70, Q-23, Q-25, Q-29, Q-123, Q-43, Q-42, Q-41 and Q-312 are marked RESOLVED with Eldon's answer.
  - Eldon said he answers for both founders. That is recorded on Q-42, Q-41 and Q-312.
- `docs/PLAN.md`:
  - GOV-061 added (doing).
  - GOV-062 added (todo): supersede ADR-0034's sandbox rule.

## Decisions
- **Country-pack evidence (Q-560):**
  - adviser sources are allowed after an accountant signs off;
  - "certified" needs a named accountant plus one founder;
  - draft packs are allowed in sandbox;
  - a pack's status must match its manifest and name a reviewer.
- **Q-70, Q-23, Q-25, Q-29, Q-123, Q-43:** the recommended defaults were accepted.
- **Q-42:** approving your own agent's draft is not a second person.
- **Q-41:** a sole owner may self-approve R1-R3 actions, with a flag, step-up and a review report. R4 actions are never self-approved.
- **Q-312:** early work for a later gate needs a plan row plus a log line.
- **Also given in chat and posted on the PRs:**
  - keep the `tested` label on packs (#255, #256, #257);
  - stuck and conflicting outcomes are closed by an authorised person with an audited reason (Q-558 d, #260);
  - all six live-handler gates are required (#260);
  - the direct-path link rule stays limited to ledger and audit tables (#262);
  - Egypt e-receipts stay out of scope for now (#256).

## Tokens or cost
Unknown.

## Next step
- GOV-062: write the ADR-0034 supersede note.
- A loader follow-up in the partner's lane may relax the `secondary` evidence rule now that Q-560 is answered.
