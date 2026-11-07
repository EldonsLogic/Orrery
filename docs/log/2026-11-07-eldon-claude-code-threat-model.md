# Session log: threat-model

Date: 2026-11-07
Author: eldon
Tool and model: claude-code (cloud session); drafted by an Opus-tier sub-agent, verified by the orchestrator
Plan IDs: SEC-001

## Summary
Threat model v1 for the five parts and the four contracts (plus connector interface and build states): scope and an honest not-modelled list, a trust-boundary diagram, assets, actors, STRIDE tables per part (T1-T16 kept, T17-T60 new), abuse cases, top 10 risks, and a per-contract file saying what each consumer may and may not trust.

## Files touched
- docs/security/threat-model.md: rewritten as v1.
- docs/security/threat-model-contracts.md (new): per-contract trust rules and proposed contract changes.
- docs/PLAN.md: SEC-001 done (v1; revisit at each gate).

## Decisions
- None. Proposed contract changes (approval bound to argument hash, idempotency keyed by user, gateway-set caller) are listed for a future ADR; no contract edited.

## Tokens or cost
Unknown.

## Next step
Top risks need owners: T36 adapter acting as the real user (OPR-004, ERP-012, partner lane), T50 token tenant and audience checks (PLT-005, SEC-004; matches ADR-0007), T42 approvals decided outside the model. Gaps marked NEW in section 8 need plan rows agreed by both founders.
