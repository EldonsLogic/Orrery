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
