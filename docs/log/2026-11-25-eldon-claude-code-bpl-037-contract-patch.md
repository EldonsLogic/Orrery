# Session log: bpl-037-contract-patch

Date: 2026-11-25
Author: eldon
Tool and model: claude-code
Plan IDs: BPL-037

## Summary
BPL-037: settings.set step uniqueness keyed on params.property (Q-51) and labelOverrides named in engine-adapter 9.3 (Q-52), contract 0.1.3, per ADR-0057.

## Files touched
- contracts/engine-adapter.md (0.1.3), contracts/compiled-artifact.schema.json (rule text): contract text
- services/blueprint/compiler/steps.py, compiler/__init__.py, adapter/fake.py: duplicate_step_keys, notes, contract version
- services/blueprint/tests/compiler/test_cmp_step_uniqueness.py: new tests
- docs/PLAN.md: BPL-037 status

## Decisions
- Implements ADR-0057 Q-51 and Q-52 (no new decision).

- Review follow-up: duplicate_step_keys wired into compile as CMP-ART-006; sort key restricted to settings.set; artifact schema stays 0.1.0 (text-only, no shape change).
- The partner adapter still advertises 0.1.2. That is compatible (versions compare on major.minor); left as a partner-lane follow-up.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Close Q-51 and Q-52 in docs/open-questions.md once merged (other lane/row).
