# Session log: ce-sec-003-fresh-install

Date: 2026-11-16
Author: partner
Tool and model: codex / gpt-6.1-terra; codex / gpt-6-luna
Plan IDs: CE-SEC-003

## Summary
Fixed missing policy tables on fresh installation and before model synchronization.

## Files touched
- apps/engine/change_engine/change_engine/hooks.py: create tables before app installation synchronizes models.
- apps/engine/change_engine/change_engine/patches.txt: run the patch before model sync on upgrades.
- apps/engine/change_engine/change_engine/tests/test_ce_sec_003_security.py: assert both registration paths.

## Decisions
- None. DDL remains outside request and document-validation paths.

## Tokens or cost
Not measured.

## Next step
CE-SEC-003 stays doing. Obtain independent security review and the other founder's review before merge.

## Verification
- 33 targeted unit tests passed with Pydantic 2.
- On a disposable synthetic bench, two concurrent authenticated writers produced revisions 2 and 3; the audit trail retained revisions 1 through 3. An unauthenticated registration request returned HTTP 403.
- Initial clean migration failed: fresh installation marked the patch complete without creating tables. A second test with the install hook passed fresh installation and normal migration. Removing the patch record and tables in the disposable database allowed a further migration to exercise and verify the pre-model-sync patch. The disposable resources were removed.
- The HTTP 403 check was unauthenticated and did not prove an authenticated non-admin denial. Production load and live multi-tenant isolation were not tested.
