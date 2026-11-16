# Session log: accept-force-with-lease

Date: 2026-11-14
Author: eldon
Tool and model: claude-code / sonnet-5-5
Plan IDs: GOV-036

## Summary
The founder (Eldon) accepts, as a one-time exception, the `--force-with-lease` push of 2026-11-11 that rewrote the partner's own unmerged PR branches during the ERP-001 rebase (see `2026-11-11-partner-codex-erp-001-rebase.md`).

## Files touched
- None besides this log.

## Decisions
- Accepted as a one-time exception to "no force-push, no history rewrite" (AGENTS.md), because only the partner's own unmerged branches were rewritten and nobody else had commits on them.
- Not a rule change: the rule stands. Stacked branches are updated by merging the lower branch into the upper one, as the partner already committed to in `2026-11-14-partner-claude-code-erp-001-review-fixes.md`.
- Founder statement given in chat on 2026-11-14; the partner should acknowledge it in his next log.

## Tokens or cost
Unknown.

## Next step
Partner acknowledges this in his next log. No plan row changes.
