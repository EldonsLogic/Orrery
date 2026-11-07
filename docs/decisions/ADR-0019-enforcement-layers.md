# ADR-0019: Enforcement layers for the operating rules

Status: Accepted
Owner: eldon
Approved by: Eldon and partner

## Context
The founders want the rules (logging, plan updates, no pushes to main, clean repo, one writer per path) followed on every task by every agent. Nobody can honestly guarantee that AI agents and people always comply. The aim is to make skipping a rule fail loudly at several independent points, and to be exact about what remains unguaranteed.

## Decision
Layered enforcement, each layer independent:
1. **Agent instructions** (AGENTS.md, RULES.md, delegation playbook): every session starts by identifying the founder and reading the rules, and ends with `python3 scripts/finish_session.py`, which refuses to say FINISHED until the tree is committed, STATUS regenerated, all checks and the task trail pass, the branch is pushed and a PR is open.
2. **Local hooks** (`pre-commit install` installs commit, commit-msg and pre-push hooks): no commit on `main`, every commit message names a plan ID, no push to `main`, and the repo checks and task trail run before any push. Client-side, so a deliberate `--no-verify` bypasses them; agents are forbidden to bypass.
3. **CI on every PR** (docs gate, hygiene, secret scan, PR log gate, trail check): a PR that breaks a rule shows red.
4. **Main guard** (`main-guard.yml`): after every push to `main` it re-runs the checks and opens an issue for both founders if `main` was pushed to directly or a check fails. Detection and alert, not prevention.
5. **Review**: the other founder reviews each PR with a different model than the author used. Only a person can judge whether a log and plan update are truthful and complete.
6. **GitHub branch protection** (required checks, required review, admins included): the only layer that makes the gates blocking on the server. It needs a paid GitHub plan for a private repo (GOV-008, open question). Recommended.

## What is not guaranteed
Without layer 6, a founder or an agent using admin rights can still merge a red PR or push to `main`; layers 4 and 5 then catch it afterwards. No script can verify that a log is accurate or that a plan status is true. Completeness of documentation rests on layers 1 to 5 together plus honest review.

## Alternatives rejected
- Trusting instructions alone: agents drift and forget.
- Making the repo public to get free branch protection: not acceptable for a private product.
- Auto-reverting direct pushes: too aggressive without founder consent; revisit if it happens.

## Consequences
- GOV-024 done; GOV-008 stays blocked until the plan decision. Founders install the hooks (GOV-010).
- Every commit message carries a plan ID; every session ends with `finish_session.py`.

## Supersedes
Extends ADR-0009 and ADR-0017.
