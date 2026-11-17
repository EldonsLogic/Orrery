# Session log: brd-004-token-layering

Date: 2026-11-17
Author: eldon
Tool and model: claude
Plan IDs: BRD-004

## Summary
BRD-004: a deterministic, pure token resolver (`services/blueprint/tokens/`) layering base tokens, product theme, tenant branding and user preference into resolved light and dark tokens plus scoped CSS, with the theme algorithm version recorded. It reuses `derive_tenant_theme` for the guardrails. Locked-token overrides, unknown tokens, bad slugs and hex values and CSS-injection attempts are refused with stable codes (`TKN-...`); any colour refusal gives the tenant exactly the product theme. 262 new tests (the AA contrast check is re-implemented independently); the whole services suite passes (1135). Open questions Q-63 to Q-75.

Fix during landing: one test imported `conftest` by name, which broke when all services were collected together; it now uses a direct path.

Not done: no server wiring (BRD-005 theme engine, BRD-006 guardrail UI), no contract change (the Blueprint contract lacks `themeAlgo` and `resolved`; Q-63).

Model and prompt: Claude Sonnet subagent from a scoped brief (allowed paths `services/blueprint/tokens/` and tests; reuse the brand tools; refuse locked overrides; deterministic). Orchestrator re-ran the suites and fixed the test import. Not rigid-zone.

## Files touched
- services/blueprint/tokens/: resolver package
- services/blueprint/tests/tokens/: tests
- services/blueprint/README.md, docs/open-questions.md (Q-63 to Q-75), docs/PLAN.md (BRD-004 done)

## Decisions
- None; open questions Q-63 to Q-75.

## Tokens or cost
Unknown or approximate, if known.

## Next step
BRD-005 theme engine and BRD-006 guardrail UI use this resolver; the contract needs `themeAlgo` and `resolved` (Q-63).
