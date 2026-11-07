# Session log: identity-review-fixes

Date: 2026-11-07
Author: eldon
Tool and model: claude-code (cloud session); review by a Sonnet-tier sub-agent, fixes by the orchestrator (Opus)
Plan IDs: PLT-002

## Summary
A cross-model review of ADR-0007 found real gaps. Added to the proposal: where role assignments live and immediate shadow-user re-sync, token lifetime, refresh, revocation by session version, HttpOnly cookie storage and subdomain-equals-token-tenant check, per-tenant impersonation credentials for the engine, invite and recovery rules, per-tenant MFA enforcement and step-up, staff tokens with their own issuer and customer-approved grants, IdP spike criteria for engine invisibility and RTL, outage behaviour, lifecycle hooks and a recorded security review as an acceptance condition. New open question Q-14 on where the identity store lives across three countries.

## Files touched
- docs/decisions/ADR-0007-identity.md (still Proposed); docs/open-questions.md (Q-14).

## Decisions
- None taken; ADR-0007 remains Proposed.

## Tokens or cost
Unknown.

## Next step
Founders: decide ADR-0007 and Q-14 (counsel input via LEG-003).
