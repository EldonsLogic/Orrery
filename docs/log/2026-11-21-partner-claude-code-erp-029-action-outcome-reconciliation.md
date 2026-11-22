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

## Review fix round (continued on antigravity after a Claude rate limit)
Date: 2026-11-22
Author: partner
Tool and model: antigravity (Gemini 4 Argon, continuing Claude Opus 5.5 WIP `ba87c95`)

### Findings fixed (Gemini 4 Argon comment and Fable 5.2 review for Eldon on `d775c35`)
1. **Whole-run atomic `outcome_conflict` detection (Gemini Medium 1, Fable Medium 2):**
   - `reconcile()` commits all transitions of a run in one `BEGIN IMMEDIATE` transaction (`_commit()`), or refuses and writes nothing.
   - `_check_run()` checks every journaled final entry of the tenant (including requests outside `request_ids`) against `outcome_for` before any engine read-back and again under `BEGIN IMMEDIATE` in `_commit()`, raising `ReconciliationRefused("outcome_conflict", tuple(conflicts))` with the journal unchanged.
   - Tested with the reviewer's repro (`request-1` applied, `request-2` journaled failed by read-back and then recorded as applied, `request-3` unknown) across `request_ids=None`, `("request-1",)`, `("request-3",)` and `("request-2",)`, plus a conflict recorded concurrently during read-back.
2. **In-flight handler protection and under-lock outcome re-read (Fable High 1):**
   - `ActionOutcomeReconciler` now requires `handler_deadline: timedelta` (`0 < handler_deadline < stuck_after`). When `outcome_for` is `None` and `now - audit.timestamp < handler_deadline`, a `not_applied` read-back returns `("unknown", "handler_in_flight")` so a slow handler is not marked `failed` before it finishes.
   - Inside `BEGIN IMMEDIATE` in `_commit()`, `outcome_for` is re-read before inserting so a terminal outcome recorded while the read-back was running wins (`("applied", "recorded")`).
3. **Preserve specific failure reasons on `stuck` escalation (Gemini Medium 2):**
   - Replaced the `"stuck"` reason override with a dedicated `stuck` column (`INTEGER NOT NULL CHECK (stuck IN (0, 1) AND (stuck = 0 OR state = 'unknown'))`), included in the HMAC calculation.
   - `readback_mismatch`, `readback_invalid`, `reader_error`, `admission_unbound`, `readback_pending` and `handler_in_flight` remain intact in both the journal and `ReconciledOutcome` when `stuck = True`, and the transition from `stuck = 0` to `stuck = 1` is journaled once.
4. **Sequence constraint and exhaustive chain verification (Gemini Low 3):**
   - Added `CHECK (sequence > 0)` to `action_outcome_reconciliation` and a schema layout check in `__init__` that refuses any older draft table lacking the `stuck` column or `CHECK (sequence > 0)`.
   - `_verify()` reads all rows in `ORDER BY sequence` from sequence 1 (`sequence == prev + 1`) and verifies that the sequence count never shrinks from an earlier check on the instance, refusing any gap, duplicate, or `sequence <= 0` with `journal_tampered`. `_commit()` catches `sqlite3.IntegrityError` and raises `ReconciliationRefused("journal_tampered")`.
5. **Backwards clock refusal (Gemini Low 4):**
   - `_check_run()` refuses with `clock_unavailable` when `now` is earlier than any admission timestamp or any latest journal entry timestamp for the tenant, matching `action_policy_store.py:147`.
6. **Mutation coverage, single-instance thread safety and design note gates (Fable Medium 3, Low 4, Low 5):**
   - Added `threading.Lock()` per reconciler instance (`test_one_instance_shared_across_threads`).
   - Added tests killing mutations on key/submitter echo, `not_applied` cleanliness, binding submitter vs audit submitter, `admission_key()` tenant filter, and a barrier-forced contradictory-readback race under `BEGIN IMMEDIATE`.
   - Updated `docs/architecture/action-outcome-reconciliation.md` sections 2-5, 7 and 8 (including external head anchor and ERP-023 audit-row MAC protection in the section 7 live-handler gate checklist).

### Verification (review fix round)
- ERP-029: 64 passed (up from 32 before the review fix round; 61 in WIP `ba87c95`).
- Mutation checks across `action_outcome_reconciler.py` and `action_policy_store.py`: 26 of 26 mutations killed.
- ERP-023: 73 passed.
- ERP-021: 7 passed.
- ERP-026 offline: 30 passed, 36 skipped (live), 39 subtests.
- CE-SEC mocks: 61 passed, 60 subtests.
- BPL-025 conformance: 208 passed (`make_harness`) and 208 passed (`make_frappe_harness`, `CHANGE_ENGINE_ENV=test`).
- `scripts/tests`: 36 passed, 29 subtests.
- `check_docs`, `check_repo_hygiene`, `scan_secrets` and `check_lanes --base origin/main --actor partner`: all passed.

## Fix round 2 (Eldon)
Date: 2026-11-22
Author: partner
Tool and model: antigravity (Gemini 4 Argon)

### Findings fixed (Fable 5.2 re-review of `f111281`, for Eldon)
1. **Journal conflicts instead of refusing the run (Medium 1, blocking):**
   - When a recorded final outcome contradicts a journaled terminal state, `_commit()` writes one HMAC-chained `outcome_conflict` entry (`state = 'unknown'`, `reason = 'outcome_conflict'`, `stuck = 1`, guarded by a partial unique index) per conflicted request. The entry is written once, sticky, returned as escalated (`stuck: true`), and never resolved automatically.
   - Other requests in the same run (and in targeted runs such as `reconcile(("request-3",))`) continue reconciling and escalating, including `stuck`, in a single transaction.
   - While any conflict is open for the tenant (evidence that the reader's `not_applied` fence failed), new `not_applied` read-backs are never finalised as `failed`; they stay `unknown` (`readback_pending`) and escalate at `stuck_after`. Recorded final outcomes, exact `applied` read-backs and stuck escalations continue to be written.
   - Updated `docs/architecture/action-outcome-reconciliation.md` to document conflict journaling and remove the earlier "refuses the whole run / writes nothing" claim about conflicts.
2. **Apply `handler_deadline` to recorded `unknown` outcomes (Low 2):**
   - `_decide()` now applies `handler_deadline` whenever `state == "failed"` (from a `not_applied` read-back) and `now - audit.timestamp < handler_deadline`, covering both a missing outcome and a recorded `unknown` outcome while an engine commit may still be in flight.
3. **Restore in-memory chain head on rollback (Low 3):**
   - `_commit()` and `_verify()` snapshot `(self._sequence, self._prev, dict(self._latest))` and restore it on any rollback or exception so a failed transaction (e.g. `sqlite3.OperationalError` mid-run) never triggers a false `journal_tampered` on the next run of the same instance.
4. **Journal `reason` changes before `stuck_after` (Low 4):**
   - `_commit()` now journals an entry whenever `reason != latest.reason` while `state == "unknown"` (e.g. `readback_pending` transitioning to `readback_mismatch` or `handler_in_flight`).
5. **Mutation tests (Low 5):**
   - Added dedicated tests for: `stuck` removed from `_mac()`; tail shrinkage refusal (`self._sequence < floor`) on the same instance; `sqlite3.IntegrityError` mapping in `_commit()`; the exact `stuck_after` boundary; and the exact `handler_deadline` boundary (for both missing and recorded `unknown` outcomes).

### Verification (fix round 2)
- Tests first: 10 failed, 61 passed before the `action_outcome_reconciler.py` changes; 71 passed after.
- Mutation checks: all targeted mutations (removing conflict journaling, removing recorded-`unknown` deadline guard, removing rollback head restoration, removing `reason != latest.reason`, removing `stuck` from `_mac`, removing `self._sequence < floor`, removing `except sqlite3.IntegrityError`, mutating `>= self._stuck_after` to `>`, and mutating `< self._handler_deadline` to `<=`) make tests fail.
- ERP-023: 73 passed; ERP-021: 7 passed; ERP-026 offline: 30 passed, 36 skipped; CE-SEC mocks: 61 passed; BPL-025 conformance: 208 passed (`make_harness`) and 208 passed (`make_frappe_harness`, `CHANGE_ENGINE_ENV=test`); `scripts/tests`: 36 passed.
- `check_docs`, `check_repo_hygiene`, `scan_secrets` and `check_lanes --base origin/main --actor partner`: all passed.
