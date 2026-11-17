# Agent-team benchmark

Status: accepted
Owner: eldon

Purpose: judge a prompt, role or routing change against a baseline before adopting it ([team-protocol.md](team-protocol.md) section 9). A change is adopted only if it improves the measured result without raising defects. This file defines the tasks and metrics; [benchmark-log.md](benchmark-log.md) is the append-only record. A benchmark never changes approval gates, evaluation rules, lanes or the phase exit check.

## Metrics (per run)
| Metric | How measured | Source |
|---|---|---|
| Outcome | `accepted` (merged without rework), `rework` (the orchestrator fixed defects before merge), or `failed` (discarded) | The orchestrator, after the checks below |
| Defects found by the orchestrator | Count and one-line description | Verification step |
| Checks passed first time | Tests, docs gate, hygiene, secret scan | Command output |
| Tokens | Reported by the harness for the run | Subagent usage note |
| Duration | Wall time of the run | Subagent usage note |
| Model and tier | The model name and the routing tier ([routing.md](routing.md)) | The brief |
| Scope kept | Only the allowed paths changed; no git use unless briefed | `git status` after the run |

Cost in money is not recorded here (prices change; see [model-registry.md](model-registry.md)); tokens are.

## Baseline task classes
Each class uses a real task from the plan. A candidate change is run on at least one task of each class that it could affect, against the baseline recorded for that class.
| Class | Typical task | Pass criteria |
|---|---|---|
| Design document | A spec with attack cases or decisions (for example SEC-003) | Every required section present, claims sourced or marked UNVERIFIED, no invented figures, checks pass |
| Research with sources | A policy that needs statutory figures (for example DAT-001) | Each figure verified with URL and access date or marked UNVERIFIED; the report states the verified count |
| Rigid or deterministic code | A compiler or resolver (for example BPL-004) | Determinism proven, fail-closed refusals tested, golden values derived from the contract and not from the code under test |
| Mechanical implementation | A generator, tokens, fixtures (for example DAT-002, BRD-004) | Tests pass in isolation and when the whole suite is collected, scope kept, no real data |
| Review | A cross-model review of a PR | Findings with file and line; real defects found; no invented defects |

## How to run and record
1. Fix the task, the allowed paths and the acceptance checks in the brief. Run the baseline model and the candidate on the same brief.
2. Verify the result yourself (run the checks, read the diff for scope). Do not trust the agent's report.
3. Append one row to the log: date, task, class, model and tier, tokens, duration, outcome, defects, notes. Rows are never edited; a correction is a new row.
4. Adopt a change only through a PR that links the two runs. A regression (more defects, outcome worse than baseline) is recorded and the change is not adopted.

## Limits
- Few runs per class: treat differences as hints, not statistics. A single run is not a baseline for a decision on its own.
- Token and duration figures depend on the harness and load; compare runs of similar size.
- The orchestrator's checks are the ground truth for defects found; a defect found after merge is added as a note on the original row.
