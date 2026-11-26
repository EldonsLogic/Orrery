# Model routing

Status: accepted
Owner: eldon

Choose the cheapest tier that can do the job reliably. Model names change; tiers do not. Current models per tier: [model-registry.md](model-registry.md). Costs are UNVERIFIED.

## Tiers
| Tier | Use for | Examples |
|---|---|---|
| Strongest | Architecture, ADRs, contracts, security review, accounting and tax logic, planning, hard debugging, anything touching the ledger or compliance | Blueprint schema, tenancy design, ZATCA component review |
| Mid | Implementation of a scoped task with clear acceptance criteria | A validator, an API endpoint, a screen |
| Small | Boilerplate, tests from a spec, docs, search, formatting, summaries, translation drafts | Fixtures, README updates, link fixes |

## Rules
- Review uses a different model (ideally a different vendor) than the author. Security and compliance reviews use Strongest.
- Escalate one tier when a task fails twice. De-escalate when a task is purely mechanical.
- Deterministic logic (ledger, tax, e-invoice, payroll maths) is written and reviewed at Strongest and tested with property tests; never delegated below Mid.
- Arabic text: Strongest or Mid drafts, an Arabic-speaking human approves anything user-facing or legal.

## Default tier per subagent role
The orchestrator runs at Strongest and owns the plan row, the briefs, git, the session log and the final check. Subagents start at these tiers unless the task touches a Strongest-only area above:
| Role | Does | Tier |
|---|---|---|
| Explorer | Reads code and indexes, returns file paths and facts; edits nothing | Small |
| Researcher | Reads external sources, writes findings with URLs and access dates to `docs/research/` | Mid |
| Worker | Edits the allowed paths in its brief and runs their checks | Mid |

## Advisor checkpoints (trial, GOV-073)
An advisor is a model of the orchestrator's tier run one effort level higher (for example Opus as advisor to an Opus orchestrator). It reads and comments but never edits files or runs git. Use Fable as advisor only where Eldon's cost rule allows Fable (the first review of a Tier 3 tax, ledger or security PR). Skip the advisor on Tier 1 work. The orchestrator asks it at three moments only:
1. **Before a plan**: before claiming a plan row or drafting an ADR, is the approach right and is anything already decided elsewhere?
2. **On a repeated error**: when the same task fails twice (the escalation rule above), is the work in the wrong place, and should it stop rather than retry?
3. **Before done**: before `scripts/finish_session.py` and the PR, what is missing (a test, a log entry, a rule)?

Give the advisor the brief, the diff and the error, not the whole transcript. The advisor does not replace the cross-model PR review: a same-vendor advisor is a self-check, and the PR is still reviewed with a different model (AGENTS.md). Record each advisor call, what it caught and its token cost (or "unknown") in the session log; the trial becomes a rule only after a comparison with a baseline (GOV-038, [team-protocol.md](team-protocol.md) section 9).

## Orchestrator rules
1. Break work into small scoped tasks, each with a plan ID, goal, files in scope and acceptance criteria. Never hand out "build X".
2. Run research and independent files in parallel subagents; do not parallelise edits to the same file.
3. Cap context: give a subagent the role file, the task and the few files it needs. Read indexes (INDEX.md, STATUS.md, PLAN.md rows), not whole folders.
4. Keep files under about 500 lines; split if larger.
5. Subagents write findings to files with sources; they return short reports.
6. Do not use worktree isolation unless two agents must edit the same files; clean up worktrees after merging.
7. The orchestrator never commits or pushes unless the session task says so, and always ends the session with a log file.
8. Anything an agent cannot verify is labelled UNVERIFIED.
