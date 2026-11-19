# Runbook: periodic plan review

Status: draft (GOV-020)
Owner: eldon

## Purpose
Keep `docs/PLAN.md` honest: re-rank what is ready, close or hand back stale work, and check the current gate's criteria. Numbers come from the script, not memory.

## Preconditions
`git pull`; the latest session logs are merged.

## Steps
1. Run `python3 scripts/plan_review.py` (`--logs N` changes how many recent logs count; default 15).
2. Stale `doing` rows (no recent log names them): finish them, set them back to `todo`, or set `blocked` with the blocker in `docs/open-questions.md`.
3. Gate inversions (a row depends on a later gate): move one gate or drop the dependency, with a one-line reason in the log.
4. Blocked rows: name the blocker and who unblocks it.
5. Ready `todo` rows per owner: re-rank, keep each owner on one or two. Do not edit the other founder's rows; message them (ADR-0025 independence).
6. Current gate: compare the open rows with the gate criteria in `GATES.md`; a criterion with no open plan row gets one.
7. Record the review in a session log (`python3 scripts/new_log.py ... --ids GOV-020`) listing what changed.

## Verification
The script exits 0 and a second run after your edits shows the findings you fixed gone.

## Rollback
Plan edits are ordinary PRs; revert the PR.

## Who
Each founder reviews their own rows weekly; both read the gate section together before a phase exit check.
