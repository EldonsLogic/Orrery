# Session log: cmp-038-publish-workflow

Date: 2026-11-26
Author: eldon
Tool and model: claude-code (Sonnet-class)
Plan IDs: CMP-038

## Summary
CMP-038 slice 2, stacked on PR #350: backend of the staff pack publishing workflow in `services/control-plane/packpublish/`, with fakes only. Draft with exact content digest, deterministic classed field-level diff, two distinct sign-offs (roster accountant plus founder, per-signer signature required in production, Q-652), publish with record and next index entry (audit first, refuse on audit failure Q-656, idempotent on request id), and a one-founder rollback pin with step-up and reason (Q-655). Outputs validate against the #350 schemas.

## Files touched
- services/control-plane/packpublish/: errors, canon, ports, fakes, workflow (new)
- services/control-plane/tests/packpublish/: 16 tests (new)
- services/control-plane/README.md: section for the package

## Decisions
- None new. Assumptions: unlisted paths and non-pack.json files classify as statutory (stricter); the top-level `version` key is left out of the diff; publish ids derive from the request id; floats are refused in pack content (no RFC 8785 number form).

## Tokens or cost
Not measured.

## Next step
CMP-038 slice 3: change records (withdrawal, floor raise, follow-up closure), upgrade scheduling, real ports (trusted_signers.json, WebAuthn, SEC-008 AuditStore, store), staff screen. Single-use step-up is the identity layer's (Q-155).
