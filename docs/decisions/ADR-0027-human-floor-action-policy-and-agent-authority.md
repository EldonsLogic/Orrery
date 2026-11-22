# ADR-0027: Human floor, action-policy table and agent authority

Status: Accepted
Owner: eldon
Approved by: Eldon, answering for both founders, 2026-11-22 (Q-128 and Q-294), recorded in docs/log/2026-11-22-eldon-claude-code-founder-answers.md, with the partner's review of PR #264 as the second founder's record (ADR-0032 item 2); accepted with the partner's three Q-294 checks, now written into the Decision below. The per-country clearance sequence still needs accountant and compliance review before it is used. Whether delivery-generated GL postings fall under the floor stays with Q-44.

## Context
Customers will create agents with an autonomy level per agent. The earlier wording of the human floor ("books, tax filing, payments, permission changes, or a human-set limit") had two holes: a limit set absurdly high is autonomy, and per-invoice authority clearance, where a country requires it, is a tax submission with no human in the loop (UNVERIFIED per country; accountant and counsel confirm). Agent authority also needs defining ([ADR-0004](ADR-0004-one-chat-role-based-views.md), [ADR-0005](ADR-0005-human-review-gate-free-first.md), RULES 21 to 23).

## Decision
- **Always a human (or a human-set limit under the platform cap):** posting to the ledger, periodic tax returns, payments, permission or role changes, sensitive external sends, bank-detail changes, and changes to an agent's limits or autonomy. Setting or changing a limit is itself a floor action, and no customer setting can exceed a platform-level cap.
- **A limit never replaces the human on the mandatory rows (Q-294 check 1):** for ledger postings, payments and permission or role changes, a human-set limit or cap only narrows what may happen; it never replaces the mandatory human initiation or approval that the action-policy table (SEC-019) requires. Whether delivery-generated GL postings fall under this stays with Q-44.
- **Authority invoice clearance** is deterministic code outside the floor. Its sequencing, and what approval the underlying invoice still needs, are confirmed per country by the accountant and compliance review. It must not silently remove a required approval: automated clearance runs only under an approved country-specific sequence that preserves the invoice's approval (Q-294 check 3).
- **One authoritative action-policy table** (SEC-019) covers roles, separation of duties, financial effect, external sends, reversibility and approval. A simpler user-facing risk scale may present it but never overrides a mandatory control.
- **Approvals are bound** to the tenant, the exact action, the data revision, the amount where relevant, the approver and an expiry, and are invalidated when material details change.
- **Agents run as their own least-privilege role**, granted by the tenant admin, never broader than the authority the tenant granted, with defined scope, tools, expiry, revocation, owner-change procedure, audit identity, cost cap and kill switch (SEC-020). "Draft-only" means it cannot send, post or change an approval rule.
- **Agent authority intersects the initiating human (Q-294 check 2):** when an agent acts on behalf of a human, what it may do is the intersection of its own grant and that human's current permissions and scope at the time of the call (SEC-020, ADR-0004, ADR-0007). It never exceeds either.
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
