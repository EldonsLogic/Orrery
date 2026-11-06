# ADR-0017: Operating rules for two founders and their agents

Status: Accepted
Owner: eldon
Approved by: Eldon (founder instruction); partner review pending (GOV-013)

## Context
Two founders work in parallel on different AI subscriptions and tools. The repo must stay clean, current and usable by any agent that opens it cold, and delegation across sub-agents and models must be safe and cheap.

## Decision
- The full standing rules live in `docs/RULES.md`; `AGENTS.md` is the short canonical version. Every session starts by reading them and ends with a log file, updated plan and status, passing checks, a pushed branch and a PR.
- One writer per path via plan-row claims; small PRs; no force-push; no self-merge; no pushes to `main` after the bootstrap. Merges are founder-authorised.
- The repo holds project content only. A hygiene gate (`scripts/check_repo_hygiene.py`, CI and pre-commit) rejects scratch files, local paths, archives, PDFs and office files, oversized files, layout violations, the retired prototype name and engine names on customer-visible paths.
- External documents (partner briefs, decks, investor material) are produced outside the repo and carry source labels for every figure.
- Delegation follows `agents/delegation-playbook.md`: model by tier, brief files, explicit allowed paths, no git for sub-agents, verification by the orchestrator, lessons recorded.
- `docs/STATUS.md` (generated) lists what is built and what is ready to start so any agent can pick work without asking.

## Alternatives rejected
- Informal conventions: do not survive parallel work by two people and several tools.
- A single shared handoff file: causes merge conflicts; replaced by one log file per session.

## Consequences
- Plan item GOV-021 done. Branch protection (GOV-008) and partner access (GOV-009) complete the setup.
- Agents spend a little time on checks and logs; in return anyone can continue anywhere.

## Supersedes
Extends ADR-0009 (repo workflow); does not replace it.
