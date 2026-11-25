# Session log: bpl-045-derived-reorder-row

Date: 2026-11-25
Author: eldon
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: BPL-045

## Summary
Records Eldon's answer on field order in incremental compile (Q-627) and adds plan row BPL-045 to build it.

## Files touched
- docs/PLAN.md: new row BPL-045 (todo).
- docs/open-questions.md: Q-627, resolved.

## Decisions
- Q-627 (Eldon, 2026-11-25, in chat): the compiler may emit a derived reorder step that is not tied to one diff op. The contract names the step and lists the add or remove ops it reconciles. A position on `*.add` was rejected because it changes the diff format that several readers use.

## Tokens or cost
Unknown.

## Next step
Build BPL-045 once #321 (BPL-039 slice 1) merges, because it changes `services/blueprint/compiler/incremental.py` from that PR.
