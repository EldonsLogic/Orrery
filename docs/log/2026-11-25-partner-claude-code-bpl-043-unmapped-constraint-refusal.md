# Session log: bpl-043-unmapped-constraint-refusal

Date: 2026-11-25
Author: partner
Tool and model: claude-code (Claude Sonnet 5.5 child wrote the code test-first; Claude Opus 5.5 coordinator reviewed and applied)
Plan IDs: BPL-043

## Summary
An unmapped `entity.add` (and `_ensure_doctype_exists` itself) now refuses any field with `unique` or `indexed`, with or without a gate approval, at execute and in `check_ready`, with the side-effect-free `plan_rejected` / `unique_or_index` the BPL-031 path raises (Q-603, ADR-0068 not yet accepted). Before, a gated unmapped entity inserted a custom type whose fields carried `unique` and `search_index`, which is constraint DDL outside the guarded DDL gate. Unmapped entities without constraints and mapped entities behave as before.

## Files touched
- apps/engine/change_engine/change_engine/adapter/frappe_backend.py: `_refuse_constrained_fields`, called first in `_ensure_doctype_exists` and in `_check_entity_add` (unmapped branch, after the protected-subject check); `_project_new_type` projects `_NO_CONSTRAINT` for every field of a type the adapter makes.
- apps/engine/change_engine/change_engine/tests/test_bpl_043_unmapped_constraint_refusal.py: new, 13 tests (execute, helper, check_ready, through the engine, regression guards).
- apps/engine/change_engine/change_engine/tests/test_bpl_041_check_ready_refusals.py: one test renamed and inverted (`test_a_unique_field_in_a_type_an_earlier_entity_add_creates_is_refused`): it asserted the old bypass (a unique field of a new custom type is held by the earlier step).
- .github/workflows/tests.yml: new file added to the BPL-027/031/041 step.

## Tests
- New file and the renamed test fail before the fix (8 failures: execute x3, helper, check_ready x2, engine apply with the gate approval, the renamed 041 test) and pass after.
- Regression guards that pass before and after: false flags, a clean unmapped entity, a mapped entity keeping its own refusal, a clean `{}` helper call, a clean plan in `check_ready`, and the apply without the gate approval (the DDL gate already rejects it as `approval_missing`; the backend-level tests cover the no-approval case).
- BPL-043, 041, 031 (both), 027 fixture, 012, 033: 117 passed, 10 skipped. All 60 engine files in tests.yml: 1,528 passed, 86 skipped, 27 Hijri-only failures (same as main).

## Not verified
- The real bench: no run against a live engine site. All checks are on the offline simulated engine.
- The engine's apply result drops error details, so the through-the-engine test checks `stage == prepare` (the readiness check) instead of the reason code.

## Decisions
- None. Unique and indexed fields on adapter-made types stay refused until ADR-0068 is accepted.
- Plan rows added: BPL-043 (`doing`), CE-SEC-008 (deploy-path durability defects from the #309 reviews), BPL-044 (DocField snapshot gap from the #310 re-review).

## Tokens or cost
Unknown.

## Next step
Review of the BPL-043 PR (stacked on #310, BPL-041); then the unique/index design (ADR-0068), which lifts this refusal.
