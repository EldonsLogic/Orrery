# ADR-0027: Human floor, action-policy table and agent authority

Status: Proposed
Owner: eldon
Approved by: pending (partner review; accountant and compliance review of the clearance sequence)

## Context
Customers will create agents with an autonomy level per agent. The earlier wording of the human floor ("books, tax filing, payments, permission changes, or a human-set limit") had two holes: a limit set absurdly high is autonomy, and per-invoice authority clearance, where a country requires it, is a tax submission with no human in the loop (UNVERIFIED per country; accountant and counsel confirm). Agent authority also needs defining ([ADR-0004](ADR-0004-one-chat-role-based-views.md), [ADR-0005](ADR-0005-human-review-gate-free-first.md), RULES 21 to 23).

## Decision
- **Always a human (or a human-set limit under the platform cap):** posting to the ledger, periodic tax returns, payments, permission or role changes, sensitive external sends, bank-detail changes, and changes to an agent's limits or autonomy. Setting or changing a limit is itself a floor action, and no customer setting can exceed a platform-level cap.
- **Authority invoice clearance** is deterministic code outside the floor. Its sequencing, and what approval the underlying invoice still needs, are confirmed per country by the accountant and compliance review. It must not silently remove a required approval.
- **One authoritative action-policy table** (SEC-019) covers roles, separation of duties, financial effect, external sends, reversibility and approval. A simpler user-facing risk scale may present it but never overrides a mandatory control.
- **Approvals are bound** to the tenant, the exact action, the data revision, the amount where relevant, the approver and an expiry, and are invalidated when material details change.
- **Agents run as their own least-privilege role**, granted by the tenant admin, never broader than the authority the tenant granted, with defined scope, tools, expiry, revocation, owner-change procedure, audit identity, cost cap and kill switch (SEC-020). "Draft-only" means it cannot send, post or change an approval rule.
- Policy is enforced and audited even when the model or the gateway fails, and fails closed.

## Alternatives rejected
- Letting a customer-set limit define autonomy with no platform cap: the cap is the only fixed point.
- Agents inheriting their owner's permissions: an admin's agent becomes an admin.
- Putting invoice clearance behind a manual approval for every invoice: may break real-time clearance rules where they apply (UNVERIFIED).

## Consequences
- Rows SEC-019, SEC-020, ERP-023, QA-019 and OPR-016.
- RULES 21 to 23 and the product brief wording are updated when accepted.

## Supersedes
None. Refines ADR-0004 and ADR-0005.
