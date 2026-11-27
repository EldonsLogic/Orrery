# Session log: qa-022-no-engine-imports

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: QA-022

## Summary
Added scripts/check_no_engine_imports.py (ast-based; flags import, from-import and literal dynamic imports of frappe, erpnext and hrms under services/, ADR-0080 point 3), with tests, wired into CI (repo-hygiene job) and pre-commit. It passes on the whole repo; the engine names in services/blueprint/tests/factory/test_analysis.py are strings and are not flagged.

## Files touched
- scripts/check_no_engine_imports.py, scripts/tests/test_check_no_engine_imports.py: new check and 9 tests
- .github/workflows/ci.yml (shared path), .pre-commit-config.yaml: wiring
- docs/PLAN.md: QA-022 set to doing

## Decisions
- None.

## Tokens or cost
Unknown.

## Next step
Merge after review, then set QA-022 to done (QA-022).
