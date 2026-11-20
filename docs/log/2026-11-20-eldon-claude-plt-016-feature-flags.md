# Session log: plt-016-feature-flags

Date: 2026-11-20
Author: eldon
Tool and model: claude
Plan IDs: PLT-016

## Summary
Feature-flag library for the control plane: boolean flags, fail closed, per-tenant, per-user and deterministic percentage rollouts, uncached kill switch that overrides all, hash-chained append-only audit, staff-human-only changes with MFA step-up for restricted flags. Tier 2 (flags cannot change authority). In-memory store only.

## Files touched
- services/control-plane/featureflags/: library
- services/control-plane/tests/featureflags/: 90+ tests (hostile contexts, NaN clock, unknown flags, cross-tenant, agent actors, kill precedence)
- services/control-plane/README.md, docs/PLAN.md (PLT-016 done), docs/open-questions.md (Q-450 to Q-453)

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown.

## Next step
Persistent store, gateway wiring and admin UI (PLT-013/014 console), cross-model review (Tier 2), Q-450 to Q-453.
