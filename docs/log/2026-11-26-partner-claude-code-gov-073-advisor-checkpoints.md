# Session log: gov-073-advisor-checkpoints

Date: 2026-11-26
Author: partner
Tool and model: claude-code / opus-5.5
Plan IDs: GOV-073

## Summary
The partner shared a diagram of a Claude Code agent setup (an Opus main session at high effort, a Fable advisor speaking at three moments, a code-side router for clear-cut decisions, three medium-effort subagents). Compared it with `agents/routing.md` and `agents/team-protocol.md` and adopted the parts that fit as a trial: three advisor checkpoints (before a plan, on a repeated error, before done) and a default tier per subagent role (explorer Small, researcher and worker Mid). Fixed the partner's out-of-date Claude Code row in `agents/model-registry.md`. Account verified as sayegh9; session-start status read (gate G0).

## Files touched
- docs/PLAN.md: new row GOV-073 (partner, doing).
- agents/routing.md: sections "Default tier per subagent role" and "Advisor checkpoints (trial, GOV-073)".
- agents/model-registry.md: the Claude Code Fable, Opus, Sonnet and Haiku rows now list both founders; removed the stale partner row (Claude 3.5 Sonnet / Opus).
- docs/log/2026-11-26-partner-claude-code-gov-073-advisor-checkpoints.md: this log.

## Decisions
- The advisor is a self-check and does not replace the cross-model PR review in AGENTS.md.
- Not adopted: an advisor that reads every tool call (token cost), and a probabilistic router (recurring judgment calls become script checks instead, as with `scripts/lanes.json`). The diagram's fork counts and the `/advisor` command are UNVERIFIED.
- Project subagent definitions under `.claude/agents/` were left out: `.claude` is not an allowed top-level entry in `scripts/check_repo_hygiene.py`, and a new top-level folder needs an ADR. The per-role tiers live in `agents/routing.md`, which every tool reads.

## Tokens or cost
Unknown.

## Next step
Eldon reviews the shared `agents/` changes (Tier 2). Record advisor calls and catches in later session logs, then compare against a baseline under GOV-038 before making the checkpoints a rule. Optional follow-up: an ADR for a `.claude/agents/` folder if the founders want tier choices enforced through tool configuration.

## Review follow-up (Eldon's two notes on 634eb294)
- Cost: the advisor is now the orchestrator's tier one effort level up (Opus to an Opus orchestrator), Fable only where Eldon's cost rule allows it, no advisor on Tier 1 work, and each call's token cost is recorded for GOV-038 (`agents/routing.md`).
- Version: the Claude Code Strongest row now says Claude Fable 5.2 (`claude-fable-5-2`) in `agents/model-registry.md`; the same stale "Fable 5.1" in `agents/delegation-playbook.md` line 14 is fixed too.
