# Session log: erp-023-engine-action-policy

Date: 2026-11-19
Author: partner
Tool and model: codex-gpt-6-2-sol
Plan IDs: ERP-023

## Summary

Added engine-side business-action admission. The adapter resolves trusted session and approval state, checks the versioned policy and exact payload, and commits a decision and replay claims before dispatching a registered effect under the human's engine identity.

## Files touched

- `apps/engine/change_engine/change_engine/guarded_apply/` contains the action-policy evaluator and durable decision journal.
- `apps/engine/change_engine/change_engine/adapter/engine.py` exposes the guarded action hook.
- `apps/engine/change_engine/change_engine/tests/test_erp_023_action_policy.py` and `.github/workflows/tests.yml` cover the hook in CI.
- `docs/PLAN.md` records ERP-023 as doing.

## Decisions

- [ADR-0027](../decisions/ADR-0027-human-floor-action-policy-and-agent-authority.md) remains Proposed and [Q-44](../open-questions.md) remains open. The engine treats delivery's operational posting as a floor action and refuses every agent submission, even with an approval or zero-approval configuration. A human's submission can satisfy the floor under a validated limit. Q-41's self-approval fallback stays disabled, and the interim separation rule also excludes an agent draft's owning human.
- [SEC-019](../security/action-policy-table.md) defines no executable policy for AP-SALES-02 or AP-PAY-01. The evaluator reserves both IDs as disabled. AP-BPL-01 is disabled on this business-action path because it requires the distinct Blueprint review workflow. Configured thresholds require a trusted amount and matching cap currency. With no tenant threshold, stock and invoice posting require an independent approver.
- The binding uses [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html) key ordering and UTF-8 (accessed 2026-11-19), decimal strings for monetary fields, and an explicit SHA-256 prefix. The version, tenant, caller, revisions, payload and idempotency key enter the digest.
- The engine journal commits replay claims and audit together on a shared, server-owned SQLite path. A failed or uncertain effect keeps its claim for reconciliation. A guarded action requires an authenticated state resolver and a registered handler that checks target revisions in its effect transaction. OPR-004 and OPR-007 supply the gateway and approval-inbox integration, and SEC-008 owns the event-stream audit chain.

## Verification

- TDD red runs failed for the missing policy and adapter entry point, and later located gaps in digest input validation, approval expiry at admission, and audit row replacement.
- Required engine group passed 110 tests and 22 subtests, including 60 ERP-023 tests. The in-memory and simulated backend conformance harnesses passed 208 tests each.
- Broader offline engine run passed 240 tests and 54 subtests, with 16 skips. The full-directory attempt could not collect the live MariaDB Suite B because PyMySQL is absent. The live suite was excluded from the offline run.

## Tokens or cost

Unknown.

## Next step

Review ERP-023 under the rigid-zone review rules and connect the OPR-004 and OPR-007 authority sources before enabling a live handler.
