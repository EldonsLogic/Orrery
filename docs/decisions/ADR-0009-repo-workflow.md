# ADR-0009: Repo workflow

Status: Accepted
Owner: eldon
Approved by: Eldon; partner review pending (GOV-013)

## Context
Two founders use different AI models and tools. The repo is the shared memory. Past practice used one shared HANDOFF file, which would collide.

## Decision
Private monorepo. Work happens on branches named with the plan ID, merged by pull request only; main is protected after bootstrap (GOV-008). Each session writes its own log file in docs/log/; docs/STATUS.md is generated. CI enforces the docs gate, secret scan and a new-log-file rule for code changes. Reviews cross models: a change written with one model is reviewed with another. Work is delegated by model tier (agents/routing.md). Agents do not commit or push unless the session task says so; pushing is handled by the founders' own setup.

## Alternatives rejected
- Polyrepo: slows cross-cutting changes.
- Single HANDOFF file: merge conflicts, lost history.
- Notion as source of truth: drifts from code (strategy/09 idea 7).

## Consequences
- Every merge needs a log file and a plan update.
- Branch protection depends on the GitHub setup (GOV-002, GOV-008).
- Model-tier rules need maintenance (GOV-012).

## Supersedes
none
