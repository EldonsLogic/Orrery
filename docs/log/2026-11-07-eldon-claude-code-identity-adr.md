# Session log: identity-adr

Date: 2026-11-07
Author: eldon
Tool and model: claude-code (cloud session)
Plan IDs: PLT-002

## Summary
Wrote the identity proposal for founder approval: central identity with per-tenant membership, roles resolved per request from each tenant's Blueprint, one token per tenant, no customer login on the engine (shadow engine users), OIDC with the identity provider chosen in a spike, mandatory MFA for admin and finance roles, separate staff realm. ADR-0007 stays Proposed.

## Files touched
- docs/decisions/ADR-0007-identity.md: full proposal, trade-offs and consequences (still Proposed).
- docs/PLAN.md: PLT-002 doing (done when both founders accept the ADR).

## Decisions
- None taken. ADR-0007 recommends option A; Eldon and the partner approve by setting `Approved by` and `Status: Accepted`.

## Tokens or cost
Unknown.

## Next step
Eldon and partner: accept or amend ADR-0007, then mark PLT-002 done and close Q-1. Then PLT-005 (identity service with the IdP spike), SEC-004.
