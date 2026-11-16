# Session log: agents-may-push

Date: 2026-11-16
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: GOV-044

## Summary
Both founders (together, in chat) gave coding agents standing permission to commit, push their feature branch and open PRs. AGENTS.md and CLAUDE.md now say so; main, force-push and unreviewed merges stay forbidden.

## Files touched
- AGENTS.md (Branches and PRs), CLAUDE.md: standing permission wording
- docs/PLAN.md: GOV-044 (doing); docs/STATUS.md regenerated

## Decisions
- None (no ADR; a working-rule change agreed by both founders). The partner confirms it in his review of this PR.

## Tokens or cost
Not measured.

## Next step
Partner reviews GOV-044. agents/orchestrator.md and agents/roles.md still say sub-agents do not commit unless the task says so, which stays correct.
