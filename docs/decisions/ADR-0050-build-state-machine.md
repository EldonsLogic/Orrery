# ADR-0050: Build state machine, draft to live, with the human gates

Status: Proposed
Owner: eldon
Approved by: pending (Tier 3: approval authority; needs the other founder's line-by-line review and a different-model security review)

## Context
[build-states.md](../../contracts/build-states.md) defines the lifecycle and says the control plane rejects any transition whose preconditions are not recorded. BPL-020 builds the machine in `services/blueprint/build_state/` on top of PLT-013 (team review evidence, [ADR-0049](ADR-0049-human-review-queue.md)), BPL-019 (simulation sign-off evidence), [ADR-0047](ADR-0047-mfa-design.md) (step-up) and [ADR-0048](ADR-0048-agent-authority-propose-not-act.md) (agents propose, humans decide).

## Decision
1. **Exactly the contract's transitions**: (none) to draft; draft to draft (revise); draft to owner_approved; owner_approved to team_reviewed; team_reviewed to built_in_sandbox; built_in_sandbox to simulated; simulated to live (after a recorded cutover start); and rollback to any earlier state before live. Nothing else; `live` is terminal here. The order follows the contract and the Blueprint `meta.buildState` enum (owner approval before team review), not the shorthand in the plan row (Q-500).
2. **Every promotion is one explicit call by one human.** There are no timers, callbacks or auto transitions. Gates (owner approval, team review, simulated, cutover start, go-live, rollback) need a Principal built by an injected identity adapter from verified claims with kind `human` and a consumed step-up; the machine checks the flag too. Agents and services may create and revise drafts and run the sandbox build (role `build_runner`), never a gate. The claim assumptions are written in `ports.py`.
3. **Evidence is re-derived at transition time**, never accepted: the Blueprint content comes from the host store and is digested here; team review is re-verified through the review port (`verify_evidence` with the sequence and head pinned at the review gate, `hold`, `stale`, `eligible`, tenant, subject, digest all checked on exact types); the simulation report is re-loaded and its sign-off re-derived from the sealed sign-off ledger with the required roles and the report digest (BPL-019 `gate_evidence`, not trusting `eligible` alone). A changed content digest after any approval is BS-008 and needs re-approval. A hold blocks every later promotion.
4. **Separation of duties**: a team-gate actor is not an author, not in `involved`, not the queue's approver of record and not an owner-gate actor; an owner-gate actor is not a staff author and not a team reviewer (Q-503).
5. **State is folded from a sealed append-only log** (whole-record HMAC with key id, chained, per-tenant head and manifest anchors, no key no machine, no sha256 fallback), the same transition rules at write and read time. A forged, reordered, truncated, deleted or replayed (other tenant or Blueprint) record is BS-011.
6. **Applies are write-ahead and idempotent** through an injected engine port: `apply_started` (idempotency key bound to tenant, Blueprint, kind, digest, attempt) is sealed before the call; only `confirmed` moves the state; an exception or any other answer is `unknown` and the build stays applying/unknown (no new apply, no rollback) until `resolve_apply` gets a definite answer.
7. **Q-274** is answered by `SignOffLedger`: sign-off records are stored sealed per simulation with the unique key (simulation, report digest, role) enforced on append.
8. Time is the host clock only; callers pass none. Errors are typed (BS-001 to BS-017) with bilingual labels; no engine name anywhere.

## Alternatives rejected
- Storing the state on the Blueprint or a row: a stored verdict can be edited; the folded sealed log cannot be trusted less than its seal.
- Accepting an evidence dict from the caller: a constructed dict has no authority; the API takes ids and pins only.
- Letting a service or agent confirm go-live: the owner's step-up is the human floor ([ADR-0027](ADR-0027-human-floor-action-policy-and-agent-authority.md)).
- Automatic sandbox and simulated transitions (the contract's wording): they become explicit calls; the contract's "automatic" means no human decision is needed for the sandbox build, which still needs fresh evidence (Q-500).

## Consequences
DSC-009 (owner approval flow) and the console call these methods. Open: Q-500 to Q-506.

## Supersedes
None.
