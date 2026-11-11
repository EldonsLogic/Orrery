# The 30 role contracts

Status: accepted
Owner: eldon

Thirty logical roles in six functions, from the self-improving agent team guide ([team-protocol.md](team-protocol.md)). A role is a contract that any agent or human can take, one role per agent per task. Do not run all thirty: start with three to five and add roles only when the work needs them.

## Defaults that apply to every role
- **Tools:** the allow-list in the task brief; read and edit only inside the owned paths; no `git commit` or `git push` unless the session task says so; no network or installs unless the brief allows.
- **Files:** a role owns only what its brief lists, inside one founder's lane (`scripts/lanes.json`). The other lane needs a recorded waiver.
- **Context:** the global rules, the role's own file, and the exact files and checks of the task.
- **Handoff:** an output artifact plus an evidence summary (what ran, what passed, what was not checked) to the orchestrator.
- **Escalation:** unclear requirement, a needed permission, a policy conflict or a failed second attempt goes to the orchestrator, and from there to the founders ([../docs/open-questions.md](../docs/open-questions.md)).
- **Model tier:** by [routing.md](routing.md). The reviewer is never the author's model.

## 1. Leadership
| # | Role | Mission | Owns | Evidence | Escalates to |
|---|---|---|---|---|---|
| 01 | Orchestrator ([orchestrator.md](orchestrator.md)) | Split a request into a task graph, delegate, keep the repo consistent | Task graph, PLAN and STATUS updates, session log | Every task has a result or a logged blocker; checks pass | Founders |
| 02 | Planner | Order work by dependency and gate; keep plan rows independent (ADR-0025) | Proposed PLAN rows | `check_plan_independence.py` passes | Orchestrator |
| 03 | Architect ([architect.md](architect.md)) | Design, ADRs and contract proposals | `docs/decisions/`, contract proposals | ADR lists alternatives and consequences; contract examples validate | Both founders (contracts need both) |
| 28 | Scheduler | Sequence parallel tasks inside time, token and cost limits; no two writers on one path | Task schedule | No path conflicts; budgets respected | Orchestrator |
| 29 | Delegation | Write briefs, pick the model tier, verify what comes back | Brief files (outside the repo) | `git status` shows only allowed paths | Orchestrator |

## 2. Engineering (acts inside the founder's lane)
| # | Role | Mission | Owns | Evidence | Escalates to |
|---|---|---|---|---|---|
| 04 | Backend ([implementer.md](implementer.md)) | Services and engine-side code for one scoped task | Task files under `services/` or `apps/engine/` | Unit tests; lane guard passes | Architect |
| 05 | Frontend | Web workspace with i18n, right-to-left and design tokens | Task files under `web/` | Tests; no hard-coded colours or strings; RTL check | Architect, Arabic linguist |
| 06 | Infrastructure | Benches, hosting, CI, backups | `infra/`, `.github/` (shared, needs review) | Restore drill; CI green | Security, founders |
| 07 | Database | Schema and migrations; tenant isolation in the data tier; never raw ledger writes | Task files in its lane | Migration and isolation tests | Architect, Security |
| 08 | Integration | Connectors, adapters, Blueprint-to-engine mapping | `connectors/` (Eldon), engine adapter (partner) | Conformance fixtures; idempotency tests | Architect |

## 3. Quality
| # | Role | Mission | Owns | Evidence | Escalates to |
|---|---|---|---|---|---|
| 09 | Testing ([test-writer.md](test-writer.md)) | Tests and evals; red, then green | Test and eval files in its task | Acceptance criteria covered; failing test reproduced first | Reviewer |
| 10 | Reviewer ([reviewer.md](reviewer.md)) | Independent review by a different model | Read-only | Findings with severity; no self-review | Founders |
| 11 | Security ([security-reviewer.md](security-reviewer.md)) | Threat review, injection, leaks, tenant isolation | `docs/security/` (shared) | Threat-model checks; canary tests | Founders |
| 20 | Reliability | Failure modes, recovery and duplicate-effect tests | Fault-injection tests, runbooks | Interrupted-operation results documented | Architect |
| 24 | Risk and Approval | Enforce approval gates, the human floor and the action policy; never edits them | Policy checks | Approval-binding tests | Founders |

## 4. Research and knowledge
| # | Role | Mission | Owns | Evidence | Escalates to |
|---|---|---|---|---|---|
| 12 | Research | Sourced facts with URL and access date | `docs/research/` (Eldon) | Sources dated; unverified items labelled | Founders |
| 13 | Documentation ([doc-keeper.md](doc-keeper.md)) | Logs, plan, status, docs | Task docs, logs | Links valid; STATUS fresh | Orchestrator |
| 14 | Context | Assemble the minimum context for a task (files, rules, tools) | Brief contents | No stale or oversized context | Orchestrator |
| 15 | Memory | Keep verified decisions and evidence only | ADRs, logs, open questions | Entries cite evidence; no guesses stored as facts | Founders |
| 25 | Knowledge | Glossary, indexes and search over repo docs | `docs/glossary.md`, indexes | Indexes complete | Documentation |

## 5. Evaluation and improvement
| # | Role | Mission | Owns | Evidence | Escalates to |
|---|---|---|---|---|---|
| 16 | Evaluation | Run real tests, review diffs, keep success and failure logs | `evals/` (Eldon) | Reproducible runs | Reviewer |
| 17 | Benchmark | Hold baselines for representative tasks | `evals/` | Baseline recorded before any change | Evaluation |
| 18 | Prompt Engineer | Keep prompts and briefs as versioned files | `agents/` | Version compared with baseline | Improvement |
| 19 | Optimization | Reduce cost and latency without losing correctness | Proposals | Benchmark parity | Cost Control |
| 26 | Improvement | Propose one versioned change per observed failure; promote only measured gains; keep rollback | PRs to `agents/` | Measured gain over baseline; rollback in git | Founders |

## 6. Operations
| # | Role | Mission | Owns | Evidence | Escalates to |
|---|---|---|---|---|---|
| 21 | Observability | Traces, logs, metrics, cost per tenant | Task files | Alerts and dashboards defined | Operations |
| 22 | Release | Pull requests, release rings, version pins, phase exit runs | `.github/` (shared), release notes | Checks green; exit run recorded | Founders |
| 23 | Operations | Runbooks, incidents, support | `docs/runbooks/` | Drill results | Founders |
| 27 | Cost Control | Budgets and caps per task and per tenant | Budget records | Caps enforced | Founders |
| 30 | Audit | Verify the trail: logs, approvals, lane guard, phase exits | Read-only | Task trail check passes; gaps reported | Founders |

## Existing role files and where they map
`orchestrator.md` (01), `architect.md` (03), `implementer.md` (04, 05, 07, 08 by lane), `test-writer.md` (09), `reviewer.md` (10), `security-reviewer.md` (11), `doc-keeper.md` (13, 25), plus `arabic-linguist.md` and `compliance-checker.md`, which support Frontend, Research and Risk and Approval. The other roles are contracts without their own file until a task needs them; create the file by copying a similar one and add it to [README.md](README.md).

## Typical starting teams
- A scoped code task: Orchestrator, Backend or Frontend, Testing, Reviewer, Documentation.
- A design or ADR: Orchestrator, Architect, Security, Reviewer, Documentation.
- A phase exit run: Orchestrator, Testing, Evaluation, Audit, Reviewer.
- A self-improvement trial: Orchestrator, Improvement, Benchmark, Evaluation, Reviewer.
