# Session log: sec-019-action-policy-table

Date: 2026-11-15
Author: eldon
Tool and model: claude-code / opus
Plan IDs: SEC-019

## Summary
Drafted the action-policy table spec for ADR-0027: table schema, risk classes, approval binding to a payload hash, separation of duties, lifecycle with cancellation, failure and expiry, break-glass, fail-closed enforcement, agents as draft-only actors, approval events, and a starter table for the six golden-path actions.

## Files touched
- `docs/security/action-policy-table.md`: new, Status proposed, Approved by pending.
- `docs/open-questions.md`: appended Q-41 to Q-44. Q-28 to Q-40 are already used on open branches, so the numbering starts after them.
- `docs/PLAN.md`: SEC-019 set to `doing`. It stays `doing` until the partner reviews the PR.
- `docs/STATUS.md`: regenerated.

## Decisions
- None. Every rule in the spec is a proposal. ADR-0027 was not changed and is still Proposed.

## Brief given to the model
The task was SEC-019: specify the action-policy table for ADR-0027. It covers the schema, separation of duties, payload-hash binding, expiry, cancellation, failure, timeout, break-glass, fail-closed enforcement, agent versus human floor, and approval as an audit event. It also includes a starter table for the golden-path actions, with roles Owner, Sales, Warehouse and Finance and an agent column that is always draft-only. The brief allowed no dates, no code and no engine names.

## Tokens or cost
Unknown.

## Next step
- The partner reviews the spec with a different model.
- The founders answer Q-41 to Q-44.
- The accountant reviews the finance rows before Phase 2.
- Then SEC-020 (agent role spec) and ERP-023 (enforcement) build on it.
- The canonical form and hash proposal in section 5 is UNVERIFIED and needs checking in ERP-023.
