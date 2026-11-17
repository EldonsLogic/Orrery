# Session log: qa-004-compiler-snapshots

Date: 2026-11-17
Author: eldon
Tool and model: claude
Plan IDs: QA-004,DAT-009

## Summary
QA-004: snapshot tests for the compiler: one valid snapshot (full artifact plus plan view, cross-checked against the existing golden file and the contract schema before it was written) and 27 refusal snapshots (stable codes and paths only, no message text); 69 tests. Snapshots are rewritten only with `UPDATE_SNAPSHOTS=1`; a missing snapshot fails and prints the command; a difference prints a unified diff of the first hunk. Whole services suite 1204 passed; `services/blueprint` alone 1044 passed.

Limits: the repo has one Blueprint fixture and no invalid or branding fixtures, so the 27 refusal cases are named edits of that fixture, the mapping or the registry. A separate production snapshot was dropped (byte-identical to sandbox, over the size budget); a test compares the production compile with the sandbox snapshot. `contracts/examples` Blueprints are not covered. The cycle refusal has an empty path because the compiler emits none.

DAT-009 (synthetic data generator for dev, demos and previews, ADR-0018) is closed: `services/datasets/` (DAT-002) is that generator, seeded and deterministic.

Model and prompt: Claude Sonnet subagent from a scoped brief (new files only under `compiler_snapshots/`). Orchestrator re-ran both suite styles.

## Files touched
- services/blueprint/tests/compiler_snapshots/: tests, helper, 28 snapshots
- docs/PLAN.md: QA-004 and DAT-009 done

## Decisions
- None.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Add invalid and branding Blueprint fixtures so refusal snapshots come from real files; cover contracts/examples.
