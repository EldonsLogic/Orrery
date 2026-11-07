# Session log: policy-persistence

Date: 2026-11-07
Author: partner
Tool and model: antigravity / gemini-3.8-flash
Plan IDs: CE-SEC-003

## Summary
Persisted change engine runtime policies per site with monotonic revision increments, durable audit trail logging, and admin permission gating behind whitelisted RPC endpoints.

## Files touched
- `apps/engine/change_engine/change_engine/api/endpoints.py`: added admin role enforcement (`_require_admin_caller`), site resolution, and RPC endpoints for policy registration, unregistration, audit retrieval, revision inspection, and document lifecycle evaluation.
- `apps/engine/change_engine/change_engine/guarded_apply/policy_store.py`: created `PolicyStore` supporting durable per-site database tables (`tabChange Engine Policy` and `tabChange Engine Policy Audit`) and standalone fallback storage.
- `apps/engine/change_engine/change_engine/guarded_apply/policy_enforcer.py`: added revision and audit metadata to `RuntimePolicy`, separated per-site policy storage from default Tier 0 protected invariants, and added site-aware policy evaluation.
- `apps/engine/change_engine/change_engine/tests/test_ce_sec_003_policy_persistence.py`: added 8 comprehensive test cases verifying admin permission enforcement, revision monotonicity, audit trail diffs, site isolation, document hook enforcement, and unregistration.
- `docs/PLAN.md`: marked `CE-SEC-003` as `done`.
- `docs/STATUS.md`: regenerated status.

## Decisions
- Per-site isolation: runtime policies are scoped per site (or tenant database), ensuring policies configured for one tenant never leak into another tenant.
- Durable audit trail: every policy save (create, update, toggle) or unregister logs an immutable audit row recording actor, timestamp, action, and full before/after JSON payloads.

## Tokens or cost
Approximate session token usage via Gemini 3.8 Flash.

## Next step
Pick up `ERP-001` (pin Frappe, ERPNext, HRMS versions and stand up dev bench in `infra/dev/docker`).
