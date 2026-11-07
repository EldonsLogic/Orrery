# ADR-0021: Public repository with branch protection

Status: Accepted
Owner: eldon
Approved by: Eldon and partner

## Context
GitHub only offers branch protection on a private repo with a paid plan. The founder declined the plan and chose to make the repository public. ADR-0009 and earlier text assumed a private repo.

## Decision
- The repository is public and read-only for outsiders. A `LICENSE` file states all rights reserved (interim, counsel to finalise under LEG-002); nothing in the repo is open source.
- Branch protection on `main`: pull requests required, status checks docs-gate, secret-scan, repo-hygiene and pr-log-gate must pass, force pushes and deletion blocked, enforced for admins. Required approving reviews are 0 (founders authorise merges, RULES.md rule 10); raise to 1 when both founders are active.
- Secret scanning with push protection and private vulnerability reporting are on. Outside contributors need approval to run workflows, and interactions are limited to collaborators (six-month limit, renew).
- Everything committed is public: no secrets, personal data, customer or pilot data, or confidential material. Confidential documents (partner briefs, decks, investor material) stay outside the repo.

## Alternatives rejected
- Paid plan: declined by the founder.
- Staying private without protection: leaves the rules advisory.

## Consequences
- Strategy, research, pricing hypotheses, the plan and the threat model are visible to anyone, including competitors. Commit history already shows two author identities and a founder's real name and email in some commits; history is not rewritten.
- Public forks are possible under GitHub's terms regardless of the licence notice.
- Supersedes the "private monorepo" wording of ADR-0009. GOV-008 and GOV-009 done.

## Supersedes
Part of ADR-0009 (private repo statement).
