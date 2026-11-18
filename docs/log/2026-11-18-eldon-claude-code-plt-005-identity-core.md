# Session log: plt-005-identity-core

Date: 2026-11-18
Author: eldon
Tool and model: claude-code
Plan IDs: PLT-005

## Summary
Built the PLT-005 identity core (services/control-plane/identity): tenant-bound short-lived tokens with pinned algorithm, separate staff realm, per-membership session versions, refresh rotation with reuse detection, MFA policy, single-use invites, staff support grants that cannot be self-approved, append-only audit, roles only from an injected resolver. Test-only HMAC signer; no network, no real IdP, no real users (Q-14). Opus subagent built it; I reran 73 tests.

## Files touched
- services/control-plane/identity/, tests/identity/, README
- docs/open-questions.md (Q-147 to Q-151), docs/PLAN.md (PLT-005 stays doing)

## Decisions
- None; Q-147 asks whether owners must use MFA (SEC-005 says yes, ADR-0007 does not).

## Tokens or cost
Unknown or approximate, if known.

## Next step
IdP spike and Q-14 before storing real users; agent run tokens (ALP-001 to 004); security review by a different model (Tier 3).
