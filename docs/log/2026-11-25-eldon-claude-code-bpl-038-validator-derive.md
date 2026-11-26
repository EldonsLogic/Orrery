# Session log: bpl-038-validator-derive

Date: 2026-11-25
Author: eldon
Tool and model: claude-code
Plan IDs: BPL-038

## Summary
Validator rule 10 now calls the token resolver's OKLCH derive (`tokens.brand_tools.derive_colours`, themeAlgo 1) instead of its own HSL search (ADR-0057 Q-64). A grid test found 46 colours where rule 10 and the resolver disagreed; all agree now. Error codes BP-BRAND-001/002 are kept: a derive refusal is 001, a light-theme darkening is 002 with an adjustment record.

## Files touched
- services/blueprint/validator/rules_branding.py: rule 10 calls the derive
- services/blueprint/tests/test_rule10_resolver_agreement.py: new grid test
- services/blueprint/tests/test_contrast.py, test_rules.py: expectations updated to the OKLCH verdicts
- docs/PLAN.md: BPL-038 done

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown or approximate, if known.

## Behaviour change
- Known change for the founders: dark-theme derivations are now silent. The derive is authoritative and rule 10 reports only light-theme darkening (BP-BRAND-002).

## Next step
Removed in review fixes: `colour.auto_adjust`, `lightness`, `_with_lightness`, `MAX_LIGHTNESS_SHIFT`. `passes_all` stays (used by the contrast tests). Rule 10 only reports light-theme adjustments; the dark primary is always derived.

## Partner review fixes, round 2 (Gemini 4 Argon findings)
1. Rule 10 and the resolver disagreed on hex input: `HEX_RE` is now used with `fullmatch` only; a trailing newline is refused, and a present but invalid accent (or a string primary that is not `#RRGGBB`) emits `BP-BRAND-001`. Tests in `services/blueprint/tests/test_rule10_review_fixes.py` and the agreement grid test.
2. `BP-BRAND-002` reported the wrong ratio (surfaces only). New `tokens.brand_tools.failing_pair` reuses the derive's own `_fails` and `contrast_pairs`; the warning and adjustment carry `pair`, `ratioBefore`, `ratioAfter`, `threshold`. `#0F766E` now reports `secondary-pressed/background` at 4.11 before. Property tests over a colour grid check `ratioBefore < threshold <= ratioAfter`.
