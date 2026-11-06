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

## Orchestrator rules
1. Break work into small scoped tasks, each with a plan ID, goal, files in scope and acceptance criteria. Never hand out "build X".
2. Run research and independent files in parallel subagents; do not parallelise edits to the same file.
3. Cap context: give a subagent the role file, the task and the few files it needs. Read indexes (INDEX.md, STATUS.md, PLAN.md rows), not whole folders.
4. Keep files under about 500 lines; split if larger.
5. Subagents write findings to files with sources; they return short reports.
6. Do not use worktree isolation unless two agents must edit the same files; clean up worktrees after merging.
7. The orchestrator never commits or pushes unless the session task says so, and always ends the session with a log file.
8. Anything an agent cannot verify is labelled UNVERIFIED.
