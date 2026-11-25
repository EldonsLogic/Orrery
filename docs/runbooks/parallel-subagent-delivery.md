# Runbook: shipping plan rows with parallel subagents

Status: draft (GOV-053), written from the method that worked in this repo on the G0 and G1 rows. Not yet re-tested by a second founder.
Owner: eldon

## Purpose
Ship one or more plan rows (see [PLAN.md](../PLAN.md)) with an orchestrating agent and parallel subagents, so both founders can run it the same way. This runbook is the how-to. The rules it applies are in [AGENTS.md](../../AGENTS.md), [RULES.md](../RULES.md), [ONBOARDING.md](../ONBOARDING.md) section 5, [delegation-playbook.md](../../agents/delegation-playbook.md) (briefs, verification), [routing.md](../../agents/routing.md) (tiers), [team-protocol.md](../../agents/team-protocol.md) section 14 (review workflow) and [ADR-0035](../decisions/ADR-0035-risk-tiered-review.md) (review tiers). Where this file and those disagree, they win; tell the founders in `docs/open-questions.md`.

## Preconditions
- You know which founder you are (ONBOARDING section 1; `gh api user --jq .login`). The row's owner and the lane must match.
- `git pull` on `main` is clean; the row is `todo` with its Depends `done`.
- The one-time setup in ONBOARDING section 1 is done (pre-commit hooks installed).
- Checks run from the repo root: `python3 scripts/build_status.py`, `check_docs.py`, `check_repo_hygiene.py`, `scan_secrets.py`, plus the tests the row names.

## 1. Choose the models by tier
Use the tier names; current model names live in [model-registry.md](../../agents/model-registry.md).

| Work | Tier | Claude model |
|---|---|---|
| Architecture, contracts, security and compliance review, tax or ledger logic, hard debugging, planning | Strongest | Opus |
| Scoped implementation from a spec, validators, endpoints, screens | Mid | Sonnet |
| Boilerplate, fixtures, tests from a spec, docs, link fixes, search | Small | Haiku |

- Escalate one tier after two failed attempts; de-escalate purely mechanical work.
- Review uses a different model from the author. For a Sonnet-written change, review with Opus or another vendor's model. For Tier 3 (rigid zone and security) use Strongest.
- Never name a retired model in a brief, log or doc. Use the tier.

## 2. One worktree per plan row, outside the repo
Parallel rows edit the same shared files (`docs/PLAN.md`, `docs/open-questions.md`, the session log folder), so each row gets its own checkout. This is the one case where worktrees are justified ([routing.md](../../agents/routing.md) rule 6).

- Create it from `main` with a branch named after the plan ID, e.g. `gov-053-subagent-delivery-runbook`, in a folder beside the repo, not under it: `<parent-of-repo>/Seshna-<plan-id-lowercase>-<slug>`. Never under `.claude/worktrees/` inside the repo, because each copy carries `node_modules`, and copies inside the repo have grown to gigabytes.
- One agent writes in one worktree. Agents for different rows never share a worktree.
- Keep a worktree only for an open row. Remove it after the merge (section 11).

## 3. Give each agent a brief file and explicit paths
- Put the brief in a file outside the repo (scratch directory). Large prompts failed intermittently; a brief file did not. The brief states the goal and plan ID, files to read first, the **only** paths it may write, what it must not do, the checks to run, the claims rule (`UNVERIFIED`, cite sources) and a short report format.
- The brief says: **no git**. Agents do not run `git add`, `commit`, `push`, `stash`, `checkout` or `reset`.
- Split by disjoint paths. Two agents never write the same file. Shared files (`docs/PLAN.md`, `docs/open-questions.md`) are written only by the orchestrator.
- Tell agents what they cannot verify and to label it. Do not ask a subagent to "not invent" and then expect gaps filled; ask for gaps to be marked, and label additions PROPOSED ([delegation-playbook.md](../../agents/delegation-playbook.md) section 7).

## 4. Check the agent's output yourself
After each agent returns:
1. `git status` in its worktree; only the allowed paths may appear. Anything else: revert it or send it back.
2. Open the key files. Do not trust a self-report.
3. Re-run the checks yourself (section 5), including the row's tests.

## 5. Orchestrator: test, then commit explicit paths
- Re-run the tests and the four repo checks in the worktree after the last edit.
- Remove cache folders before staging: `rm -rf .pytest_cache`. Run Python tests with `-p no:cacheprovider` so none is created.
- Build any secret-like literal (a fake key, a token shape) at runtime from fragments, so `scan_secrets.py` does not flag the test file.
- Stage by explicit path: `git add docs/runbooks/parallel-subagent-delivery.md docs/runbooks/README.md ...`. **Never `git add -A` or `git add .` at the repo root**; they pick up scratch files, `node_modules`, caches and generated output.
- Commit message names the plan ID (`GOV-053: ...`); the commit-msg hook rejects one without it.
- Build artefacts: the web build rewrites `web/tsconfig.json`. Restore it before staging (`git checkout -- web/tsconfig.json`) and never commit the rewrite.
- Web tooling: `web/package.json` pins `pnpm@10.34.9` in `packageManager`. Use `npx pnpm ...` when pnpm is not on PATH; do not install it globally.

## 6. Claim the row before the push
- In `docs/PLAN.md` set the row `doing` with the owner, in the same branch, before the first push (AGENTS: claim before touching its files). Set `done` only in the PR that delivers it, after its checks pass.
- Never edit a row another founder has `doing`.

## 7. Session log
- `python3 scripts/new_log.py --author <eldon|partner> --tool <tool> --slug <topic> --ids <PLAN-IDs>`, then fill it in. Model tier used per agent goes in the body (tier name is enough).
- Code PRs need a log (CI). Tier 1 docs-only PRs do not ([ADR-0035](../decisions/ADR-0035-risk-tiered-review.md) item 5), but a log is still useful when the process changed.
- Logs are append-only: a new file per session, never edit an old one.

## 8. Plan-ID and question-number collisions
Two branches opened in parallel often pick the same next number.
- If a PR adds plan rows (GOV-, SEC-, etc.) or questions (`Q-n` in `docs/open-questions.md`), and `main` gained the same number after your branch was cut, renumber your added rows after merging `main` (next free number), and update every reference in your own files.
- Do not renumber rows already on `main`.
- Check with `check_plan_independence.py` and `check_docs.py` after renumbering.

## 9. Merge-main conflicts
- `docs/open-questions.md`: keep both sides' rows, then apply section 8.
- `docs/PLAN.md`: keep the other side's status changes on rows you did not touch; for your rows, keep your status and owner. Re-run `check_plan_independence.py`.
- `docs/STATUS.md` is generated. Do not hand-merge it: resolve by taking either side and regenerate with `python3 scripts/build_status.py` ([ADR-0035](../decisions/ADR-0035-risk-tiered-review.md) item 7 moves this to CI).
- Logs and ADRs: never merge an edit into an old file; if both sides added files, both stay.
- After a merge from `main`, re-run the checks before pushing.

## 10. Review
- **Tier 1 (docs only):** CI green is enough for the author's merge under ADR-0035. The other founder skims afterwards. Confirm how the GitHub ruleset treats Tier 1 first (ADR-0035 leaves the mechanism UNVERIFIED).
- **Tier 2 (ordinary code, contracts, ADRs, scripts, CI):** one review from the other founder, with a different model than the author. A fresh reviewer agent is a useful first pass, not a substitute for the founder's review.
- **Tier 3 (rigid zone and security: tax, e-invoicing, ledger-adjacent, auth, tenancy, policy, secrets):** full review as today, including the line-by-line human review under ADR-0031 and the security review. A subagent review may run first and never replaces the human step.
- **Cross-model review for Tier 3:** a read-only reviewer on a different model reads the diff, the relevant decisions and the risks, and writes findings to a file outside the repo. It edits nothing. The fixer applies only real defects in the same worktree and reports the commit it fixed.
- **Blocking findings only:** a review blocks only for a bug, security issue, broken rule or missing required check. Everything else becomes a follow-up row or open question. Reviewers list blocking items first.
- **Re-review request:** give the commit last reviewed, the new commit, the findings being answered and the test results ([team-protocol.md](../../agents/team-protocol.md) section 14.3).
- **Two rounds maximum.** After the second, the founders settle it in one message and record the outcome in the PR.
- Run CI and reviews in parallel once the PR is stable. A stacked PR is not approved before the one under it; avoid stacks deeper than two.

## 11. Push, PR and CI
- Push the feature branch only: `git push -u origin <branch>`. Never push to `main`; never force-push.
- Open or update the PR with `gh pr create` or `gh pr edit`, filling the PR template. Say how to view the change if it is visible (ADR-0018).
- `finish_session.py` checks the push and the PR. Run it before stopping.
- Wait for CI with a bounded command, not an open-ended loop, for example `timeout 600 gh pr checks <number> --watch`. If it is still pending or red when the budget ends, report the state and stop; do not keep polling.
- A red check: read the failing log, fix the cause on the branch, push again. Do not bypass hooks (`--no-verify`).
- Merge only the PRs the founder has approved for merge ([AGENTS.md](../../AGENTS.md) Branches and PRs). Never merge your own Tier 3 PR.

## 12. Cleanup after the merge
Once the PR is merged and the worktree is clean:
```
git worktree remove <path-to-worktree>
git branch -d <merged-branch>
git worktree prune
```
- Confirm the worktree has no uncommitted work and the branch is merged before removing. Use `-d`, not `-D`.
- Remove any scratch brief or output files outside the repo.
- Say in one line in the log that cleanup happened.

## 13. Pitfalls seen in this repo
- **Engine name in a test regex.** A test or doc that spells the engine's name in a customer-visible path trips the hygiene check ([check_repo_hygiene.py](../../scripts/check_repo_hygiene.py), ADR-0016). Use "the engine" or build the pattern from fragments; keep the name out of `web/`, locale, template and fixture files.
- **Retired prototype name.** It fails hygiene in new docs; write "change engine".
- **Local machine paths.** Absolute paths to a user's home folder fail hygiene. Write paths relative to the repo, or a placeholder.
- **Secret-like literals.** Fake keys in tests fail `scan_secrets.py`; build them at runtime.
- **Build rewrites.** `web/tsconfig.json` changes on build; restore before staging.
- **Cache folders.** `.pytest_cache` appears after a test run; remove it and use `-p no:cacheprovider`.
- **Hooks rejected the first commit.** A pre-commit hook may fail once (it can reformat or regenerate a file). Re-stage the explicit paths and commit again with the same message. Never use `--no-verify`.
- **Generated files.** `docs/brand/tokens/*.css` and `docs/brand/logo/*` are regenerated by their script, never hand-edited.
- **Parallel renumbering.** See section 8.
- **Stale brief.** If a requirement changes while agents run, message them or stop and restart them; do not let them finish on the old brief.

## Verification
- `python3 scripts/check_docs.py` passes.
- `python3 scripts/check_repo_hygiene.py` passes.
- `python3 scripts/scan_secrets.py` passes (optional here, CI runs it).
- The row's tests pass in the worktree and again after the merge from `main`.

## Rollback
This runbook is text only. Revert it through a PR; do not edit it in place without a log entry.

## Who
Either founder's orchestrating agent, with the founder who owns the row. The partner's and Eldon's sessions use the same steps; Tier 3 review always needs a human.
