# Session log: sec-022-review-followups-7

Date: 2026-11-22
Author: partner
Tool and model: claude-code (Claude Sonnet 5.5)
Plan IDs: SEC-022,BPL-032

## Summary
Closed Eldon's Medium 1 on #274 (a field type could change through `entity.set_property` without being recorded, one form with no gate): `entity.*` steps now need exactly `/entities/<id>`, `entity.set_property` may not name `id`, `fields` or `relations`, and `field.set_property` may touch `type` only as exactly `/type`; plus the Low 2 test pinning the `KIND_ROOTS` fallback. Tier 3, tests first: the new module had 88 failing checks before the change and none after; 12 mutations of the new checks are all caught.

## Files touched
- apps/engine/change_engine/change_engine/adapter/engine.py: `_judge` pointer shape and property rules for `entity.*` and `field.set_property`; `ENTITY_STRUCTURAL_PROPERTIES`, `_property_head`; a non-string `property` no longer raises on the semantic lookup.
- apps/engine/change_engine/change_engine/tests/test_sec_022_review_followups_7.py: new, both adapters.
- .github/workflows/tests.yml: the new module in the SEC-022 step.
- docs/decisions/ADR-0051-adapter-role-and-state-namespacing.md: new item 8 (Proposed).

## Decisions
- [ADR-0051](../decisions/ADR-0051-adapter-role-and-state-namespacing.md) item 8 (Proposed): deny list of structural entity properties, not an allow list, so no property that planned before and does not touch the element lists is newly refused.
- Not done, still open: taking a field's type for the `/options` check from the engine instead of the site config (Eldon's suggestion); schema validation skipped without `jsonschema` (Eldon's Low 3).

## Tokens or cost
Unknown.

## Next step
Security review by a different model, then Eldon line by line (SEC-022, BPL-032). Live bench behaviour is UNVERIFIED (offline only).

## Review fix (cross-model review, GPT-6.1 Sol, partial)
The review stopped before its report, but the defect it reproduced is real. `_segs` drops any text before the first `/`. So with schema validation skipped, `field.set_property` with property `x/type` planned `auto_approved` and wrote `type` without recording it. `x/options` and `x/target` also skipped their exact-spelling checks.

Fix (Claude Opus 5.5, coordinator): every kind that carries `params.property` now needs a well-formed pointer (`PROPERTY_KINDS`). On fields and relations, `type`, `options` and `target` are accepted only as exactly `/type`, `/options` and `/target` (`EXACT_ELEMENT_PROPERTIES`). ADR-0051 item 8 is updated.

Tests first: 90 failing checks before the fix, none after. Four mutations of the new rule are all caught. `change_engine/tests`: 1389 passed, 87 skipped.

## Eldon's review of #280 (Fable 5.2, at 1c1d929): fixes
- **Medium 1** (`field.set_property /id` renames a field onto a link field's id with no gate): fixed. `SETTABLE_PROPERTIES` is an allow list taken from the Blueprint schema for entity, field and relation set_property steps, and it excludes `id` (and `fields` and `relations` on entities). Relation `options` is kept, because it is the engine link target, guarded by the target checks.
- **Medium 2** and **Low 3** (text before the first `/`, and a malformed property raising mid-apply): already fixed in 82769db (`PROPERTY_KINDS`).
- **Low 4** (the deny list let `/Fields`, `/fields ` and `/%66ields` through): fixed by the allow list. This replaces `ENTITY_STRUCTURAL_PROPERTIES`.
- **Low 5** (ADR item 8 overstated): reworded to name exactly what it rests on.

Tests first: 34 failing checks before the fix. The shape tests in follow-ups 5 and 7 that used the made-up property `/x` now use `/labels`, or expect a refusal. Four mutations of the allow list are all caught. `change_engine/tests`: 1393 passed, 87 skipped.

## Cross-model review of 82769db and 079b1b3 (GPT-6.1 Sol): APPROVE, one Low fixed
The Sol review approved. It confirmed that all 5 of Eldon's findings are addressed, that no current compiler output is newly refused, and that relation `/options` still reaches its target checks. Engine suite: 1393 passed. Its two mutations were both caught.

Its Low: the relation tests built `parents: ["customer"]`, which is malformed, so they could pass on parent validation alone. Fixed: they now use `_relation_step` on the seeded relation `rel_item`, with a control showing that a valid relation step passes the rule. Switching off the relation exact-property guard now fails 6 checks; before, it failed none.
