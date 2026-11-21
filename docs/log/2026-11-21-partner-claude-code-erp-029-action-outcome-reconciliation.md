# Session log: erp-029-action-outcome-reconciliation

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Claude Opus 5.5, `claude-opus-5-5`)
Plan IDs: ERP-029

## Summary
This session added offline reconciliation of ERP-023 admitted business actions. Every admission ends as applied, failed or unknown. A recorded unknown outcome, or a missing one, is resolved only by an exact engine read-back by the admitted idempotency key. A stuck unknown escalates to the human floor with its claims kept. Every transition is appended to a keyed, tamper-evident journal. This is Tier 3 (engine authority and audit) and needs a human line-by-line review under ADR-0031.

## Files touched
- `apps/engine/change_engine/change_engine/guarded_apply/action_outcome_reconciler.py` (new): `ActionOutcomeReconciler`, `EngineReadback`, `ReconciledOutcome` and `ReconciliationRefused`.
- `apps/engine/change_engine/change_engine/guarded_apply/action_policy_store.py`: the narrow hook justified below.
- `apps/engine/change_engine/change_engine/tests/test_erp_029_action_outcome_reconciliation.py` (new): 32 tests.
- `.github/workflows/tests.yml`: the ERP-023 step also runs the new test path; the step is renamed.
- `docs/architecture/action-outcome-reconciliation.md` (new): the design note.
- `docs/open-questions.md`: new row Q-558.

## Store hook justification
ERP-023 stores the idempotency claim as `[submitter, key]` with no link to the request ID. The audit record has no key, and the payload hash cannot be inverted. Without a binding written at admission, the reconciler would have to take the key from its caller. That is untrusted input that could point the read-back at another request's effect.

The hook adds three things:
- the append-only table `action_policy_admission_keys`, with one key per request and update, delete and replace triggers;
- one `INSERT` in `record()`, after the claims are reserved, for non-deny decisions only, in the same transaction;
- the read method `admission_key()`, which returns the binding only while both the request claim and the idempotency claim exist.

The enforcer's decisions are unchanged. `action_policy_enforcer.py` is not edited, and the 73 ERP-023 tests pass unedited. If the insert fails, the admission aborts. That matches the existing fail-closed rule for journal failures.

## Decisions
- No ADR (per brief). The founder decisions are in Q-558: the stuck threshold, the escalation recipient, journal key custody, and whether an audited human attestation may close an undecidable outcome.
- Recorded `applied` and `failed` outcomes are taken as final without an engine re-read. A `not_applied` read-back counts as `failed` only if the engine fences the key. That fence is UNVERIFIED and is a gate item for OPR-004 and OPR-007.
- The journal is one HMAC chain across tenants, with contiguous sequences. Deleting the newest entries is not detectable without an external anchor. This is documented as a limit. Its impact is bounded because final states are derived again from the outcome or the read-back, never from the journal alone.

## Verification
- Tests first. The new module failed (1 failed, 31 errors, module missing) before the implementation. It passed 32 of 32 after.
- ERP-023 and ERP-029: 105 passed.
- ERP-021: 7 tests OK.
- ERP-026 offline: 30 passed, 36 skipped (live), 39 subtests.
- CE-SEC mocks: 61 passed, 60 subtests.
- BPL-012, ERP-012 and SEC-004: 20 passed, 16 subtests.
- BPL-025 conformance with `make_harness`: 208 passed. With `make_frappe_harness` and `CHANGE_ENGINE_ENV=test`: 208 passed.
- `scripts/tests`: 22 passed, 29 subtests.
- `check_docs`, `check_repo_hygiene`, `scan_secrets`, `check_plan_independence` and `check_lanes --base origin/main --actor partner`: see the PR.
- Not checked: any real bench. Every engine fact in the design note is UNVERIFIED.

## Implementation brief (ADR-0031 condition 4)
The orchestrator's brief, summarised: implement ERP-029 as an implementation sub-agent for the partner. Write a design note under 150 lines covering the states, deterministic resolution of unknown outcomes by idempotency-key read-back with no blind retry, stuck outcomes and human-floor escalation, append-only journaling, and the OPR-004 and OPR-007 gate. Implement offline beside the policy store, reconciling ERP-023 claims against an injected reader, with append-only journaling that fails closed. Leave `action_policy_enforcer.py`'s behaviour unchanged; a narrow store hook is allowed if justified. Write the tests first: applied, failed and unknown with a later resolution, a reader error, a duplicate reconcile, a tampered journal and a cross-tenant entry. List them in `tests.yml`. Do not edit `adapter/engine.py`, `adapter/frappe_backend.py`, `api/route_guard.py`, `docs/PLAN.md`, `contracts/` or `services/`. Do not rebase, force-push or start subagents.

## Tokens or cost
Unknown.

## Next step
- Tier 3 human line-by-line review and a cross-model review of this PR.
- The founders answer Q-558.
- OPR-004 and OPR-007 supply a real engine reader with a tested fence, and the inbox route for stuck outcomes (design note section 7).
- The ERP-029 row status is changed in PLAN via PR #251's owner (not edited here).
