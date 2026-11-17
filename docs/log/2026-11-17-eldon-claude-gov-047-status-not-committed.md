# Session log: gov-047-status-not-committed

Date: 2026-11-17
Author: eldon
Tool and model: claude
Plan IDs: GOV-047

## Summary
Stopped committing the generated `docs/STATUS.md`. It conflicted on nearly every merge and PR (each merge needed `--theirs` plus a regenerate). `docs/STATUS.md` is now a short hand-written pointer; `python3 scripts/build_status.py` prints the status (use `--write` for an ignored local copy); CI shows it in each run summary.

Removed: the freshness check in `check_docs.py`, the CI step and main-guard step that diffed STATUS, the pre-push diff, and the finish_session regenerate-and-commit check. No gate, lane, security, approval or phase-exit rule changed. Wording updated in AGENTS.md, RULES.md, ONBOARDING, START-HERE, team-protocol and the delegation playbook.

This is the CI-generated STATUS follow-up from ADR-0035 (both founders agreed on 2026-11-16, per Eldon). The partner's agent can object on this PR or by a follow-up row; it is easy to revert.

Model and prompt: Claude in Claude Code; brief: "stop the STATUS merge conflicts that hold up both founders".

## Files touched
- scripts/build_status.py, check_docs.py, check_pre_push.py, finish_session.py, session_start.py: no STATUS freshness
- .github/workflows/ci.yml, main-guard.yml: summary instead of diff
- docs/STATUS.md: pointer
- AGENTS.md, docs/RULES.md, ONBOARDING, START-HERE, team-protocol, delegation-playbook: wording
- docs/PLAN.md: GOV-047

## Decisions
- ADR-0035 follow-up; no new ADR.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Remaining ADR-0035 follow-ups: partner's recorded review to accept ADR-0035; reword the PR template to the tiers.
