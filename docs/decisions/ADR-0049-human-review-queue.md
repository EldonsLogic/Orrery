# ADR-0049: Human review queue and the team_reviewed gate evidence

Status: Proposed
Owner: eldon
Approved by: pending (Tier 3: approval authority; needs the other founder's line-by-line review and a different-model security review)

## Context
[build-states.md](../../contracts/build-states.md) makes `owner_approved` to `team_reviewed` a human gate that only a named internal reviewer can pass. PLT-013 builds the queue behind it; BPL-020 (state machine) and DSC-009 (owner approval flow) read its output. [ADR-0027](ADR-0027-human-floor-action-policy-and-agent-authority.md) and [ADR-0048](ADR-0048-agent-authority-propose-not-act.md) say agents propose and humans decide; [ADR-0047](ADR-0047-mfa-design.md) defines the MFA step-up. Code: `services/control-plane/reviewqueue/`.

## Decision
1. **Evidence, not promotion.** The queue's `gate_evidence` and `team_reviewed_evidence` are evidence for BPL-020. Nothing in the queue changes a build state; BPL-020 applies its own policy and re-reads the stored content itself.
2. **Reviewers** are staff-realm identities verified by the identity service (live token, active identity, current session version, MFA, a fresh step-up to claim and to decide) holding the role `team_reviewer` from an injected resolver. Anything unexpected denies. The role set is a proposal (Q-225 b, Q-440).
3. **Separation of duties.** The author, the requester, any attester or signer (`involved`) and any staff member linked to one of them cannot claim or decide. A claim is a lock that expires; only its holder decides.
4. **State is folded, never stored.** Each item is an append-only log of events, each sealed with a whole-record HMAC (per-purpose derived key, key id inside the seal) and chained to the previous seal. Every read re-validates and folds; any mismatch is RQ-011. No key means no queue (RQ-012); there is no unsealed or plain-hash fallback.
5. **Decisions bind the content digest.** A decision is refused if the host's current content no longer matches; an approval reads as stale when content changes. A held (quarantined) item cannot be approved and only a resubmission with new content lifts the hold.
6. **Checklists are data** per kind (`checklists.json`). Approval needs every check `pass`; every other decision needs a note. Audit lines carry the note's hash and length, never its text. Labels are i18n keys in Arabic and English.
7. **Time** is the caller's, whole seconds, bounded to a fixed window and within five minutes of the identity clock, and never older than the log's last event.

## Alternatives rejected
- Storing status on the item: a stored verdict can be edited; folding from sealed events cannot be trusted less than the seal.
- A plain sha256 as the integrity check when no key is set: anyone can recompute it.
- Letting the caller pass the content digest: the host passes content it loaded itself.

## Consequences
BPL-020 and DSC-009 consume the evidence. The console screens for the queue come with PLT-014 or a follow-up row. Open: Q-440 to Q-446.

## Supersedes
None.
