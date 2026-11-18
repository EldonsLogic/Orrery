# Session log: bpl-015-component-sandbox

Date: 2026-11-18
Author: eldon
Tool and model: claude-code
Plan IDs: BPL-015

## Summary
Built the component factory sandbox (services/blueprint/factory): temp-dir copy with limits and O_NOFOLLOW, manifest and registry admission checks, allow-listed test commands with a scrubbed environment, only with --trusted-source, never above level tested. Logical sandbox only; OS-level isolation is INF-014. Sonnet subagent built it; I reran the factory tests (20).

## Files touched
- services/blueprint/factory/, tests/factory/, README
- docs/PLAN.md

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown or approximate, if known.

## Next step
INF-014 before running any third-party component code; no separate BPL-014 harness exists, the registry admission rules stand in for it.
