# Session log: bpl-044-docfield-snapshot

Date: 2026-11-26
Author: partner
Tool and model: claude-code / claude-sonnet-5-5 (worker), claude-opus-5-5 (coordinator)
Plan IDs: BPL-044

## Summary
BPL-044 (#310 re-review N2): before a field step, the execute path now reads the type's own DocField rows as well as the Custom Field snapshot, so a field of an adapter-made type no longer returns `recovery_required` on a later `field.add`, `relation.add` or re-add after quarantine. Ambiguity and unreadable state fail closed. Coordinated from docs/log/2026-11-26-partner-claude-code-partner-g1-sprint.md.

## Task trail
- Worker: Claude Sonnet 5.5 high (T3 `delegate_task`, own worktree from main c8fbac58, no git). Allowed paths: `adapter/frappe_backend.py`, `adapter/engine.py` (unchanged), new `tests/test_bpl_044_docfield_snapshot.py`.
- `_has_docfield` reads `tabDocField` on the snapshot's connection; a failed read raises (`engine_unavailable`), never "absent".
- Fail closed with `recovery_required` before any field write when a name is both a Custom Field and a DocField, when the DocField belongs to a type the adapter did not make, or when a DocField has no column. An errored snapshot keeps its old refusal. No DDL and no lock change.
- Tests first: the new file had 8 failures before the fix, 12 passed after. Hand mutations: 8 of 8 caught (the read, its use in both branches, ambiguity, ownership, errored snapshot, swallowed read error).
- Coordinator re-ran the full change-engine suite after merging main: 1865 passed, 86 skipped, 0 failed.

## Files touched
- apps/engine/change_engine/change_engine/adapter/frappe_backend.py: `_has_docfield`, DocField read in `_apply_or_restore_custom_field`.
- apps/engine/change_engine/change_engine/tests/test_bpl_044_docfield_snapshot.py: new regression tests.
- .github/workflows/tests.yml: the new test joins the BPL-027 offline step (CI fails closed on unmapped tests).
- docs/PLAN.md: BPL-044 done once this merges (left `doing` here).

## Decisions
- None by the founders. Design choice: ambiguity refuses rather than letting the Custom Field win.

## Tokens or cost
Unknown.

## Next step
- UNVERIFIED on a real bench: the `tabDocField` query and the setter restore on adapter-made types. Bench check for the batched bench session: unmapped `entity.add`, then `field.add` of the same field succeeds with no Custom Field row and setters present.
- Outside this row: `take_snapshot` in `api/endpoints.py` (and the guarded-apply schema reconciler that uses it) still reads only Custom Field; `simulated_frappe.py` does not answer `tabDocField`. Candidate follow-up row if the reviewer agrees it is reachable on this path.
- BPL-033 and BPL-042 (same files) follow after this merges.
