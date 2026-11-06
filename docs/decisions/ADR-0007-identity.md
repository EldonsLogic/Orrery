# ADR-0007: Identity model

Status: Proposed
Owner: eldon
Approved by: Pending (Eldon to review; partner review pending)

## Context
Users may belong to several companies (owner, accountant, auditor). Per-tenant sign-in is simple but forces repeat logins and makes support and the accountant channel awkward. Open question Q-1.

## Decision
PROPOSED: one central identity (user account) with per-tenant roles and scopes. Authentication and MFA are central; authorisation lives in the Blueprint roles of each tenant. Staff support access is separate, just-in-time and audited. Not decided until both founders accept it; the choice affects Tool API checks and tenant provisioning.

## Alternatives rejected
- Identity per tenant: simpler isolation, worse UX for accountants and multi-company owners.
- Third-party identity provider from day one: possible later; decide with hosting (INF-001).

## Consequences
- If accepted: build PLT-005 as a central service; tenants trust its tokens.
- Cross-tenant leakage risk moves into the identity layer; test it (SEC-004).
- Blocks G0 until decided (PLT-002).

## Supersedes
none
