# Session log: bpl-004-compiler

Date: 2026-11-17
Author: eldon
Tool and model: claude
Plan IDs: BPL-004

## Summary
BPL-004: a deterministic, pure compiler from Blueprint, component registry and engine mapping to the compiled artifact (initial builds only). It refuses invalid Blueprints, missing or ineligible components (fail closed per environment), bad mappings and dependency cycles; it computes no figures, rates or rules. 81 compiler tests; the whole Blueprint suite passes (710, no skips) including a round trip of the trading fixture through the fake adapter. Open questions Q-50 to Q-62 recorded.

Also: the fake adapter (#56) had been stacked on #40 and never reached main; it landed in #71. An earlier `git add -A` swept six in-progress compiler files into the GOV-048 commit on main; this PR replaces them with the complete compiler.

Model and prompt (ADR-0031 condition 4): Claude Opus (subagent) from a scoped brief (allowed paths services/blueprint/compiler, tests/compiler, one README section; deterministic, fail closed, no figures computed in code; golden file derived from the contract). Not rigid-zone: it emits configuration only. The golden expected artifact was derived by a separate script from the contract and matched the compiler.

## Files touched
- services/blueprint/compiler/: new package
- services/blueprint/tests/compiler/: 81 tests and a golden artifact
- services/blueprint/README.md: compiler section
- docs/open-questions.md: Q-50 to Q-62
- docs/PLAN.md: BPL-004 done

## Decisions
- None; open questions Q-50 to Q-62.

## Tokens or cost
Unknown or approximate, if known.

## Next step
BPL-012 (partner, real adapter) and BPL-027 (integration). BPL-007 apply and rollback orchestration.
