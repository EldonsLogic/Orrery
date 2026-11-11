# ADR-0028: Recoverable, journaled change apply (not universal rollback)

Status: Proposed
Owner: eldon
Approved by: pending (partner review)

## Context
Database structure changes and application metadata cannot share one atomic transaction, and posted financial documents and external sends cannot be undone by a rollback. The draft engine-adapter and compiled-artifact contracts currently promise atomic apply and an inverse for every change set. The partner and the independent review asked for honest wording. Contracts changes need an ADR ([../RULES.md](../RULES.md) rule 19).

## Decision
- Apply is **journaled and recoverable**: durable checkpoints, a tenant-level lock, the approved change bound to a revision and a change hash, a defined recovery step for every stage. Atomicity is promised only where it is demonstrated.
- Every change is classified: (1) transactional change that truly rolls back; (2) partially applied configuration needing compensation or forward repair; (3) posted financial document needing correcting entries; (4) external submission or send that cannot be undone.
- Invoices, payments and other irreversible operations carry a durable operation identity. If the engine succeeds but the gateway or event writer fails, the outcome is visible and reconciled before any retry, so a duplicate effect cannot be created silently.
- Acceptance tests force interruption at each durable boundary and document the operator action where automatic recovery is unsafe.
- The adapter and compiled-artifact contracts are reworded to this model before they become accepted.

## Alternatives rejected
- Promise universal rollback: untrue for schema changes, financial postings and sends.
- No journal, rely on the engine: hides partial failure and duplicate effects.

## Consequences
- BPL-025 and BPL-026 are reworded; ERP-021 tests recovery on a real bench; QA rows cover duplicate effects.
- A user-requested undo of configuration is a new revision; financial effects use native correction mechanisms.

## Supersedes
None.
