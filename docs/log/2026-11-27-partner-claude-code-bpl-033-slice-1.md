# Session log: bpl-033-slice-1

Date: 2026-11-27
Author: partner
Tool and model: claude-code / claude-opus-5-5 (worker and coordinator)
Plan IDs: BPL-033

## Summary
BPL-033 slice 1, the two blockers the BPL-027 bench class found on the real-bench runner (#381): a refused step that wrote nothing now compensates cleanly to the exact prior export, and a Link field whose target document type does not exist is refused before any write. Coordinated from docs/log/2026-11-26-partner-claude-code-partner-g1-sprint.md.

## Task trail
- Worker: Claude Opus 5.5 high (T3 `delegate_task`, own worktree from main, no git). Allowed: `adapter/engine.py`, `adapter/frappe_backend.py`, `adapter/simulated_frappe.py`, a new `tests/test_bpl_033_slice1_*.py`, one `tests.yml` line.
- Defect 1, cause A: `_apply_or_restore_custom_field` (`adapter/frappe_backend.py`) raised `engine_unavailable` without `side_effect_free` even when nothing was written: the DDL gate's refusal (`REJECTED`) and the engine's own validation error (`FAILED_CLEAN`, field and column absent). `_execute_all` then set `comp_fault`, and `_compensate` (`engine.py`) gave up before undoing any step (export hash changed, `recovery_required` at `compensate`). Fix: only those two clean cases count as side-effect free: the gate's non-additive refusal of a plan it could inspect (`plan_rejected` / `storage_not_additive`) and the verified-absent engine refusal. A failed lock, lookup, read or uninspectable plan still fails closed. The whole step must be clean (no earlier field of the step created, no type created by it); on a clean refusal the step's pending intent rows are deleted.
- Defect 1, cause B (found on the bench): undoing step 56 failed because `_quarantine_field` hid a field before clearing "required", and the engine refuses to hide a required field (`HiddenAndMandatoryWithoutDefaultError`). Fix: quarantine clears "required" first.
- Defect 2: `_refuse_missing_link_targets` runs in `check_ready` (it knows which types earlier steps create, and allows a self-Link) and again on the execute path before any write; refusal `plan_rejected`, `reasonCode` `subject_missing`, `pointer` `/entities/<target>` (the contract's reason-code list has no `link_target_missing`). `engine.py` keeps a `check_ready` refusal's details, so the reason reaches the apply outcome.
- Tests: new `test_bpl_033_slice1_rollback_and_link_target.py`, 10 tests, wired into the BPL-033 step of `tests.yml`; on unmodified main 6 of the then 9 failed; all 10 pass. Full suite: 1883 passed, 86 skipped, 1 failed: BPL-008 `test_06`, which applies the trading fixture whose current compiler order puts `sales_order` (a Link to `sales_quote`) before `sales_quote`; it passes once Eldon's BPL-051 (#391) lands. With the Link check switched off the suite is green.
- Bench (local, pinned, the `bpl-046-real-bench-class` runner plus these adapter files): with the defect 1 fixes, step 57's refusal compensates steps 1 to 56, the export hash equals the one before the apply, the site is `ready`, and no audit rows are held. With all fixes, `test_03` ends `failed_clean` at prepare with `subject_missing` / `/entities/sales_quote` and no step runs.

## Files touched
- apps/engine/change_engine/change_engine/adapter/engine.py, adapter/frappe_backend.py: as above.
- apps/engine/change_engine/change_engine/tests/test_bpl_033_slice1_rollback_and_link_target.py: new.
- .github/workflows/tests.yml: the new test in the BPL-033 step.

## Decisions
- Coordinator: keep both fixes in one PR and wait for #391 rather than split or edit BPL-008's test; the PR stays a draft until #391 merges and the full suite is green.

## Tokens or cost
Unknown.

## Next step
- After #391: merge main, run the full suite, then the BPL-027 bench class (#381), including Eldon's ask: a rollback of two entities that link to each other.
- Left of BPL-033: "exact prior state" holds for the export only (the engine keeps hidden residue by design: Custom Field 43 to 125, Property Setter 109 to 273, DocType 925 to 928, Warehouse 5 to 7, UNVERIFIED whether the 3 extra DocTypes are hidden); undos of role, report, workflow and approval steps after a clean refusal are not exercised; the Link check for steps 58 to 85 on real Frappe is UNVERIFIED; a compensated outcome carries `engine_unavailable` (retryable) for the engine-validation case; a partly written step still ends `recovery_required` without a reason; and the row's earlier hardening items.
