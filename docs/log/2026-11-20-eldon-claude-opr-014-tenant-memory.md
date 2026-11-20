# Session log: opr-014-tenant-memory

Date: 2026-11-20
Author: eldon
Tool and model: claude
Plan IDs: OPR-014

## Summary
OPR-014 per-tenant, per-user memory port and in-memory reference store (Tier 3: tenancy and agent authority) with 54 tests; plan row done.

## Files touched
- services/operate/memory/: models, redact, store, service, errors, tests
- docs/architecture/tenant-memory.md: design
- docs/open-questions.md: Q-390 to Q-393
- docs/PLAN.md: OPR-014 done
- services/operate/README.md not touched (outside allowed paths); add a section later

## Decisions
- None (no ADR; open questions Q-390 to Q-393).

## Tokens or cost
Unknown.

## Next step
Host wiring of recall into chat and the owner endpoint (Q-391); events-contract types (Q-390).

## Review fixes (Opus review of PR #212)
Appended in the same session. Clock high-water mark removed and erasure no longer reads the clock; expired rows hard-deleted and not counted; model-facing `AgentMemoryTool` (host sets taint, author, source ids); `confirm` owner-only; rule-like text unverified; unverified cap 20 and 7-day TTL; secrets refused, more ID forms masked, odd digits no longer crash; erasure reports success with `audit_failed`; per-tenant audit salt supported. Q-394 and Q-395 added. 84 tests; mutations (no purge, no owner check, clock in erase) each fail a test.
