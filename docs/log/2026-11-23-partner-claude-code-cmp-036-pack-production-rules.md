# Session log: cmp-036-pack-production-rules

Date: 2026-11-23
Author: partner
Tool and model: claude-code (Sonnet 5.5, as the implementation sub-agent for the partner's coordinator thread)
Plan IDs: CMP-036,CMP-035

## Summary
Built CMP-036, test-first: production loading now needs a per-market product-choice list for PLATFORM-DEFAULT facts on locked paths, refuses open blockers and pending references (resolved only by a recorded status, founder login and date), and applies the Lows from Eldon's review of #282 (evidence status, duplicate keys, manifest meaning, closed evidence keys, founder and reviewer binding, nesting and date hygiene). The four shipped packs stay refused in production and load in sandbox and test; no pack JSON changed.

## Files touched
- components/compliance/country_pack/evidence.py: product-choice list reader and path rule, locked-path PLATFORM-DEFAULT check, verified_official label reconciliation, open-blocker and outside-fact checks, `accessed` lower bound, closed evidence key set
- components/compliance/country_pack/certification.py: founders map binding (owner, reviewer, approving founder), manifest meaning checks, `requires` resolution, strict reads
- components/compliance/country_pack/loader.py: strict reads for pack.json, clean refusal on deep nesting
- components/compliance/country_pack/strict_json.py (new): duplicate-key and recursion-safe JSON reading
- components/compliance/country_pack/product_choice_paths.json (new): per-market list; Saudi rounding provisional (Q-601), UAE and Qatar rounding provisional (UNVERIFIED), Egypt empty
- components/compliance/country_pack/tests/test_production_rules.py (new): 44 tests, one group per rule
- components/compliance/country_pack/tests/test_country_pack_go_live_gate.py: fixture owner and reviewer are now founder logins (sayegh9, EldonsLogic); the founder-loop test sets owner and reviewer per founder
- components/compliance/country_pack/tests/test_certification_evidence.py: the "PLATFORM-DEFAULT with a ref loads" assertion now expects the product-choice refusal (ADR-0067 reverses it)
- components/compliance/country_pack/tests/pack_checks.py: CI `pending()` counts only open entries
- docs/decisions/ADR-0067-country-pack-production-blockers-and-product-choice.md (new, Proposed); docs/decisions/INDEX.md: new row, ADR-0063 row notes the ADR-0059 amendment
- docs/compliance/country-pack-framework.md: documents the new production rules

## Decisions
- [ADR-0067](../decisions/ADR-0067-country-pack-production-blockers-and-product-choice.md) (Proposed): Q1 option C, Q2 option A, blocker resolution record, the Lows. Readings I chose and flagged for review: `resolution.by` must be a founder login; an outside-schema entry blocks only when it lists a locked path in `paths`; `verified_official` is checked per locked leaf; `requires` resolution checks ids and capabilities, not version ranges; the approving founder must be the manifest owner's founder.
- No new open question: Q-601 already covers the Saudi rounding answer.

## Tokens or cost
Unknown.

## Next step
Eldon's Tier 3 review and a different-model security review of this PR. Then, per market, the accountant answers behind the provisional list entries (Q-601) and rework of the Egypt identity-path defaults before any pack is certified.
