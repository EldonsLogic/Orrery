# Session log: inf-009-browser-runner-placement

Date: 2026-11-21
Author: partner
Tool and model: antigravity / Gemini 4 Hydrogen
Plan IDs: INF-009

## Summary
Drafted Proposed ADR-0052 and the supporting architecture diagram for Tier 5 isolated browser runner placement, evaluating four options against isolation, in-country residency, credential non-storage, egress, audit, prompt-injection, and cost criteria, and defining SEC-015 requirements and open questions Q-515 to Q-519.

## Files touched
- `docs/PLAN.md`: claimed `INF-009` as `doing` (owner `partner`) in the first commit.
- `docs/decisions/ADR-0052-isolated-browser-runner-placement.md`: Proposed ADR evaluating four placement options, recommending Option B (separate isolated cloud account/VPC per active operating region running per-session disposable microVMs), and specifying `SEC-015` controls.
- `docs/decisions/INDEX.md`: added Proposed `ADR-0052` entry.
- `docs/architecture/isolated-browser-runner.md`: Mermaid trust-boundary diagram, boundary invariant table, and session lifecycle.
- `docs/open-questions.md`: added `Q-515` to `Q-519` for founder/counsel decisions (`Q-514` left reserved).
- `docs/log/2026-11-21-partner-antigravity-inf-009-browser-runner-placement.md`: this session log.

## Decisions
- Proposed [ADR-0052](../decisions/ADR-0052-isolated-browser-runner-placement.md) (Status: Proposed, pending cross-model review and both founders' acceptance): recommends Option B (separate isolated cloud account/project and VPC per active region running per-session disposable microVMs), with `Q-515` capturing the minimum dedicated-VPC + microVM-node-pool floor if a chosen `INF-001` regional provider lacks multi-account isolation.

## Tokens or cost
Unknown.

## Next step
Cross-model review and founder review of Proposed ADR-0052 (Tier 2); resolve `Q-515` to `Q-519` (and close `Q-2`) before accepting ADR-0052 and starting `SEC-015` (egress and credential controls) and `DSC-017` (Tier 5 browser session).
