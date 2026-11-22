# Session log: sec-022-review-followups-6

Date: 2026-11-22
Author: partner
Tool and model: claude-code (Sonnet 5.5)
Plan IDs: SEC-022,BPL-032

## Summary
Closed Low 1 of Eldon's re-review of merged #273: a step's pointer root is now tied to its kind at plan time (`KIND_ROOTS`), so `location.upsert /roles/x`, `location.upsert /company/x` and `settings.set /entities` are refused with `unsupported_value_type` on both adapters, with nothing written and no `recovery_required`. Low 2 (schema validation skipped without `jsonschema`) is not fixed here: it needs its own plan row and a decision (fail closed, or make `jsonschema` a hard engine dependency).

## Files touched
- apps/engine/change_engine/change_engine/adapter/engine.py: `KIND_ROOTS` (derived from `STEP_KINDS`, `SECTION_OF`, `SETTINGS`) and one extra clause in `_judge`.
- apps/engine/change_engine/change_engine/tests/test_sec_022_review_followups_6.py: new tests (mapping written out literally; Low examples; every kind under every other known root; every valid kind and a `bpdiff`-shaped step still plan).
- .github/workflows/tests.yml: new module listed in the SEC-022 step.
- docs/decisions/ADR-0051-adapter-role-and-state-namespacing.md: item 7 (Proposed) states the full root-to-kind rule.

## Decisions
- ADR-0051 item 7 extended in place (the ADR is still Proposed). Kind to root: `settings.set` -> `/company`, `/compliance`, `/i18n`; `component.*` -> `/components`; `location.*` -> `/locations`; `entity.*`, `field.*`, `relation.*`, `option.*` -> `/entities`; `role.*` -> `/roles`; `workflow.*` -> `/workflows`; `approval.*` -> `/approvals`; `report.*` -> `/reports`.

## Evidence
- New module: 394 failed (subtests) and 7 passed with the mapping defined but not enforced; 7 passed, 612 subtests passed after the `_judge` clause.
- Mutations, all caught except one equivalent: clause removed (394 fail); `option` under `/locations` (13); `field` under `/roles` (11); `settings.set` also `/entities` (9); `settings.set` only `/company` (9); `location.upsert` also `/roles` (5). Surviving: unmapped kinds allowed any root, unreachable because `_judge` refuses unsupported kinds earlier.
- SEC-022 modules 128 passed; BPL-027 offline, BPL-008, BPL-012, ERP-012, ERP-023, ERP-027 and BPL-007 305 passed, 11 skipped; ERP-020, ERP-021, phase2, phase3 and policy enforcer OK; phase4 1 failure (the known pre-existing one); CE-SEC mocks 61 passed; both conformance harnesses 208 passed, no vector changed; `bpdiff` 146 passed.

## Tokens or cost
Not measured.

## Next step
Eldon's cross-model re-review of this PR. Low 2 needs a plan row (SEC-022 or a new one) and a founder decision.
