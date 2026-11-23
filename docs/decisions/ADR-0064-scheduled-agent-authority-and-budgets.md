# ADR-0064: Scheduled agents: owner authority, draft-only runs and two-level budgets

Status: Proposed
Owner: eldon
Approved by: pending (Tier 3: agent authority and budgets; needs the other founder's line-by-line review and a different-model security review)

## Context
OPR-013 adds agents that run on a cadence with no human in the turn. [ADR-0048](ADR-0048-agent-authority-propose-not-act.md) (Proposed) says OPR-013 must conform to it but does not say whose authority a scheduled run carries, how its budget is held across runs, or what happens when the owner loses access. [agent-least-privilege](../security/agent-least-privilege.md) sets the on-behalf-of user to the owner (OQ-1 open) and ALP-019, ALP-025, ALP-026, ALP-031 and ALP-033. The model-call contract ([model-call.md](../../contracts/model-call.md), [ADR-0054](ADR-0054-model-call-contract.md), Proposed) reserves and meters per call but has no standalone period reservation. First slice: `services/operate/runtime/schedule.py`.

## Decision
1. **Owner authority, never more.** A schedule's tenant and owner come from the verified principal; a body tenant or owner that differs is refused (`tenant_mismatch`, `owner_mismatch`). Its agent role must be one of the owner's own roles (`role_escalation`); no caller-supplied role field exists. Its tools must be on that one role's agent menu (`resolve_allowlist`, `tool_not_allowed`).
2. **Draft-only.** A scheduled tool may not be R2, refused by `authority.tool_refusal`, or a non-read verb on a posting entity (ledger, stock, tax, e-invoice, payroll by class or name): `draft_only`. A run only records proposals (`ctx.draft`) for the human review queue; nothing executes. Runs are tainted from the start (ALP-019).
3. **Re-checked at run time.** The owner's current roles are read before each run; losing the agent role suspends the schedule (`owner_permission_lost`, ALP-026). Tools are re-resolved against current tool definitions.
4. **Two budget levels.** The run cap is held against the per-period cap before the run (`budget_exhausted` with an `agent.budget_exceeded` record when spent plus the hold would cross it), and is the `run` layer of the PLT-026 port, which reserves and meters every call. After the run the hold settles to the metered `meter.ai_usage` cost; an unreadable meter counts the whole hold. Port refusals end the run (`port_refused`).
5. **Fail closed.** Any error discards the run's drafts and still counts metered spend. A port bound to another tenant is `tenant_mismatch`. A backwards, non-finite or non-numeric clock runs nothing (`clock_fault`). Missed slots collapse into one run; a slot that comes due while a run is open is refused (`overlap`) and runs on the next tick.
6. **Audit.** Every schedule change (`schedule.created`, `.updated` with changed fields, `.disabled`, `.suspended`) and run (`agent.run_started`, `.tool_proposed`, `.run_completed`, `.run_failed`, `.budget_exceeded`) is recorded without args or model text; if the audit write fails the change or run does not happen (`audit_unavailable`).

## Alternatives rejected
- A service identity or agent role for scheduled runs: it could outrank its owner (ADR-0043, ADR-0048 item 2).
- Let scheduled runs propose R2 actions: unattended R2 proposals multiply review load; start narrow, widen by ADR.
- Rely only on per-call gateway budgets: a schedule could spend its whole tenant budget one run at a time.

## Consequences
- Must be done: host wiring (durable store, real scheduler, gateway port) in a later slice; `schedule.*` audit types are not in the event contract yet (Q-597); pausing on exhaustion (ALP-033, Q-598) and dropping queued triggers of a killed agent (ALP-025) are not built.
- Values (minimum cadence 300 s, caps) are placeholders (Q-156).

## Supersedes
None. Refines ADR-0048 for scheduled runs; does not edit it.
