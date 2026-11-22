# Session log: founder-answers

Date: 2026-11-22
Author: eldon
Tool and model: claude-code (Claude Opus; the questions were prepared by Opus and Fable review agents)
Plan IDs: GOV-061, GOV-062, GOV-063, GOV-064

## Summary
Eldon answered founder questions one at a time in chat. The answers are written into `docs/open-questions.md`.

## Files touched
- `docs/open-questions.md`: 16 questions answered.
  - Q-560, Q-70, Q-23, Q-25, Q-29, Q-123, Q-43, Q-42, Q-41, Q-312, Q-128, Q-294, Q-296 and Q-291 are marked RESOLVED with Eldon's answer.
  - Q-292 and Q-293 are marked DECIDED, pending GOV-063.
  - Eldon said he answers for both founders. That is recorded on Q-42, Q-41, Q-312, Q-560 and the second-round rows.
- `docs/decisions/ADR-0027-human-floor-action-policy-and-agent-authority.md`: Status Accepted; Approved-by names this log; the three Q-294 checks are written into the Decision (it was Proposed, so its body could still change).
- `docs/decisions/INDEX.md`: ADR-0027 shown Accepted.
- `docs/PLAN.md`:
  - GOV-061 added and set done.
  - GOV-062 added (todo): supersede ADR-0034's sandbox rule.
  - GOV-063 added (todo): apply Q-292 and Q-293.
  - GOV-064 added (todo): apply Q-41, Q-42, Q-43 to the action-policy table, RULES 21 to 23 wording to ADR-0027, and Q-70 tokens.

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

## Second round (same day)
- **Q-128 and Q-294:** ADR-0027 is Accepted (status line and INDEX updated) with the partner's first three checks. Delivery postings stay with Q-44.
- **Q-296:** the mapping gets every strictness item.
- **Q-291:** staging may use a dev-class host now.
- **Q-292 and Q-293:** decided, pending GOV-063 (new todo row).

## Notes for the partner (his lane, no rows added from Eldon's side)
- Q-23: set `enable_immutable_ledger = 1` for every v1 tenant in provisioning.
- Q-291: `infra/staging.md` still asks for an INF-001 provider ADR; confirm whether a dev-class staging host needs it.
- Q-296: add every strictness item to the role-and-permission mapping (record scopes, deny unmapped fields, artifact hash, negative tests, the two `Percent` to `Float` fixes).

## Tokens or cost
Unknown.

## Next step
- GOV-062: write the ADR-0034 supersede note.
- A loader follow-up in the partner's lane may relax the `secondary` evidence rule now that Q-560 is answered.
