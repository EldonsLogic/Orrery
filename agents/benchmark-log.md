# Agent benchmark log

Status: accepted
Owner: eldon

Append-only record for [benchmark.md](benchmark.md). One row per run; never edit a row, add a new one. Tokens and duration are as reported by the harness for the delegated run.

| Date | Task | Class | Model (tier) | Tokens | Duration | Outcome | Defects found by the orchestrator | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-11-16 | SEC-003 prompt-injection defence design (PR 66) | Design document | Fable 5.2 (strongest) | 126k | 4 min 46 s | accepted | 0 | 400 lines, 34 attack cases, 36 requirements; verified sources limited to three, the rest marked UNVERIFIED |
| 2026-11-16 | DAT-001 data classification and retention (PR 67) | Research with sources | Fable 5.2 (strongest) | 171k | 11 min 29 s | accepted | 0 | 37 statutory rows: 9 official text, 6 non-official text, 6 secondary, 16 UNVERIFIED; Qatar none verified; figures not re-verified by the orchestrator |
| 2026-11-17 | BPL-004 Blueprint compiler (PR 72) | Rigid or deterministic code | Opus (strongest) | 292k | 16 min 23 s | accepted | 1 | Found that the fake adapter was not on main (a process error upstream, not the agent's); 81 tests, golden file derived from the contract; six files vanished mid-run and were rewritten identically |
| 2026-11-17 | DAT-002 synthetic datasets (PR 76) | Mechanical implementation | Sonnet (mid) | 139k | 6 min 11 s | accepted | 0 | 105 tests, determinism four ways; scope kept; lane gap reported |
| 2026-11-17 | BRD-004 token layering resolver (PR 79) | Mechanical implementation | Sonnet (mid) | 156k | 9 min 1 s | rework | 1 | 262 tests passed alone but one test imported `conftest` by name and failed when all services were collected; fixed by the orchestrator |

Reading these five: one small defect in two of five runs, both caught by running the whole suite, not by the agent's own run. The cheapest useful check is to run every suite together before merging. Five runs are too few to compare models.
