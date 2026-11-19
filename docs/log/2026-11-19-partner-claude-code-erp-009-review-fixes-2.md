# Session log: erp-009-review-fixes-2

Date: 2026-11-19
Author: partner
Tool and model: claude-code / sonnet-5.5
Plan IDs: ERP-009

## Summary
Re-checked every MED item of the cross-model review of PR #162 against the code at `005dfbd`. Most were already fixed, but three real defects remained that the tests' fakes hid; this session fixes them.

## Files touched
- `apps/engine/change_engine/change_engine/adapter/record_events.py`: `changed_fields` now works on real engine documents (they are not dicts; compared through `as_dict()`, save-time bookkeeping stripped from child rows, the test-only `prior` field removed from the production ignore list); a new record never inherits the subject ID of an earlier deleted record with the same name; only a sink `EventError` rejection dead-letters a row, other failures retry forever.
- `apps/engine/change_engine/change_engine/patches/erp_009_create_event_outbox.py`: subject table uses a nullable `live` flag in its unique key (retired subjects keep their reverse mapping but free the name); column DDL errors are no longer swallowed.
- `apps/engine/change_engine/change_engine/tests/test_erp_009_record_events.py`: non-dict document, delete and re-create, outage versus rejection, and patch tests; the fake document no longer smuggles `prior` as a field.
- `apps/engine/change_engine/README.md`: delivery and re-create behaviour.

## Decisions
- Review finding "one poison row blocks the queue" stays fixed, but quarantine is limited to rejections of the event itself. A sink outage must not silently drop audit events after five scheduler ticks (the previous behaviour).
- Dev sites that already ran an earlier head of this PR have the old subject table (`deleted` column) and will not re-run the patch: drop `tabChange Engine Event Subject` and `tabChange Engine Event Outbox` and migrate again. Nothing is deployed.
- Not checked: other open PRs for `Q-217` to `Q-221` collisions (main ends at Q-209).

## Verification
- Before the fixes the new tests failed (19 failed with the new fixture schema, including the three new defect tests). After: `PYTHONPATH=apps/engine/change_engine python3 -m pytest apps/engine/change_engine/change_engine/tests/test_erp_009_record_events.py -q`: 22 passed.
- No real MariaDB or bench was available in this session; the SQLite fixture stands in. `GET_LOCK` and the live engine tests were not re-run.

## Tokens or cost
Unknown.

## Next step
Cross-model re-review of ERP-009 (Tier 3). Confirm the event receiver and tenant ID handoff before enabling publication.
