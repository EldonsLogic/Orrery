# Delegation playbook

Status: accepted
Owner: eldon

How an orchestrating agent splits work across sub-agents and models, safely, when two founders work in parallel. Tiers and role specs: [routing.md](routing.md), [orchestrator.md](orchestrator.md). Rules of record: [../AGENTS.md](../AGENTS.md), [../docs/RULES.md](../docs/RULES.md).

## 1. Decide whether to delegate
Delegate when the task is independent, well specified and checkable. Do the work yourself when it needs your accumulated context, is small, or is a judgment call between options. Never delegate a decision that belongs to the founders.

## 2. Pick the model by task
| Task | Tier | Claude models (as used by the founders) |
|---|---|---|
| Architecture, ADRs, contracts, security review, accounting or tax logic, hard planning, deciding what fits | Strongest | Fable 5.1 or Opus 5.5 |
| Long-form writing that must be accurate and persuasive (partner brief, strategy) | Strongest | Opus 5.5 |
| Implementing a scoped task from a spec; writing specs, schemas, docs, design-system files; fan-out of many documents | Mid | Sonnet 5.5 |
| Boilerplate, formatting, link fixes, summaries, simple lookups | Small | Haiku 5.5 |
Other tools (Codex, Antigravity): use the vendor's strongest model for Strongest, its mid model for Mid, its fastest for Small; fill the names in [model-registry.md](model-registry.md). Escalate one tier when a task fails twice; de-escalate when it is mechanical. Review with a different model than the author.

## 3. Write a brief, do not paste a wall of text
Put the brief in a file outside the repo (a temporary folder) and tell the sub-agent to read it. A brief states: goal and plan ID; files to read first; the only paths it may write; what it must not do (no git, no network or installs unless allowed, nothing outside its paths, no secrets); deliverables; checks it must run (`check_docs.py`, `check_repo_hygiene.py`, tests); claims discipline (cite sources, `UNVERIFIED`); and a short report format (files, check results, what it assumed or could not do).

## 4. Parallelise only disjoint work
One writer per path. Launch agents together only when their write paths do not overlap; run dependent steps in order. If a requirement changes while agents are running (a new country, a new rule), send them a message or resume them; do not let them finish on stale instructions.

## 5. Verify, never trust a self-report
After each agent: `git status` must show only the allowed paths; run the checks yourself; open the key outputs; re-compute any numbers; spot-check claims against sources; render visual work and look at it. Fix what is wrong, or send it back with specifics.

## 6. Integrate and leave a trail
Update the plan row statuses, write the session log (`scripts/new_log.py`), regenerate `docs/STATUS.md`, commit on a branch named with the plan ID, push, open a PR. Do not merge your own PR. Clean up: remove temp files outside the repo, delete merged branches and any worktrees.

## 7. Lessons we learned (do not repeat)
- Large prompts to sub-agents failed intermittently: use brief files.
- Sub-agents that cannot reach a font or file will invent or approximate: give them the file path or mark the gap as open.
- A sub-agent told "do not invent" will transcribe faithfully but leave gaps; if you want gaps filled, say so, and label additions PROPOSED.
- Unverified numbers creep in from decks and blogs: label them or source them before external use.
- Scratch files, rendered images, snapshots and local paths leaked into the repo until the hygiene gate existed; run it before finishing.

## 8. Start a session in any tool
Paste this as the first message (Claude Code reads CLAUDE.md automatically; for other tools point to AGENTS.md; whether Codex or Antigravity auto-read AGENTS.md or GEMINI.md is UNVERIFIED):
```
You are working in the Orrery repo with two founders working in parallel.
Read AGENTS.md, then docs/RULES.md, then docs/STATUS.md and the latest 3 files in docs/log/.
Then confirm which plan row in docs/PLAN.md you are taking (or pick one from "Ready to start" in STATUS.md),
claim it (status doing + owner), work on a branch named with its plan ID, delegate scoped sub-tasks by model tier
as in agents/delegation-playbook.md, and finish with: session log, PLAN and STATUS updated, checks passing, branch pushed, PR opened.
Ask me if anything is unclear. Do not merge your own PR or push to main.
```
