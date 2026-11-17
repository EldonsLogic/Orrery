# Session log: ce-sec-003-security-fixes

Date: 2026-11-14
Author: partner
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: CE-SEC-003

## Summary
Fixed the six blocking security findings in Eldon's review of PR #34, plus the should-fix items. Added 20 regression tests and checked the SQL path against real MariaDB on the synthetic bench, which found and fixed one more bug.

A Codex delegate given the same brief finished without changing anything and gave no reason. This session did the work instead.

## Findings and fixes
1. **`eval` replaced by a fixed grammar.** The new module `guarded_apply/policy_expression.py` parses conditions with `ast` and walks an explicit allow-list. Nothing is compiled or executed.
   - Allowed: field names, literals and lists of literals, comparisons (`is` only against None), `and`, `or`, `not`, unary minus, and the two helpers `is_field_changed('x')` and `has_role('x')` with one string literal each.
   - Conditions are rejected when registered.
   - At evaluation, a condition that cannot be evaluated counts as a violation (fail closed).
   - The eval-era `SafeEvalContext` and `SafeDocWrapper` are removed.
2. **Tier 0 cannot be overridden.** Ids of built-in policies, and any id starting with `TIER0_`, are refused on register and unregister, in the catalog and again in the store.
   - The API sets the tier itself (always 1). A caller-supplied `governance_tier`, or any field outside the allow-list, is refused.
   - Built-in policies always win over a stored row with the same id.
3. **Fails closed.**
   - Every store read or write error raises `PolicyStoreError`.
   - Enforcement then denies with `POLICY_STORE_UNAVAILABLE`, instead of skipping persisted policies.
   - A failed revision read raises instead of restarting at 1.
   - Table setup no longer swallows errors; it is gone from the store.
4. **The site comes from the request only.**
   - Under Frappe, `get_current_site_id` uses `frappe.local.site` only and refuses a different explicit site. The endpoints no longer take `site_id`, and refuse it if sent.
   - With a database, the catalog keeps no process-wide copy of site policies, so nothing goes stale across workers.
   - The in-memory site map is used only in standalone tests.
5. **No caller-supplied roles inside Frappe.** Session roles decide. `user_roles`, `caller_roles`, `actor`, `site_id` and `governance_tier` sent to a policy endpoint inside a Frappe request are refused. Registering and removing policies needs an admin role and fails closed.
6. **No DDL at request time.** The tables are created by the migration patch `change_engine.patches.ce_sec_003_create_policy_tables`, registered under `[post_model_sync]` in `patches.txt` and run by `bench migrate`. The patch uses `frappe.db.sql_ddl`. The store never runs `CREATE TABLE`.

Should-fix items:
- The revision is read with `SELECT ... FOR UPDATE` in the same transaction as the write.
- The audit table has no update or delete path in code. The docstring says the database does not enforce immutability.
- Tests now cover the cases the review listed.

## Bug found by the live check
- On real MariaDB, the first `save_policy` failed. ISO timestamps with a timezone (`...+00:00`) were written into `DATETIME(6)` columns, which MariaDB rejects (error 1292).
- This was in the original PR. The unit tests never ran the SQL, so they could not see it.
- Fix: timestamps are converted to naive UTC strings before the write.

## Evidence
- **Unit suite:** `PYTHONPATH=. python -m unittest discover -s change_engine/tests -t .` in `apps/engine/change_engine` ran 107 tests, OK. That is 87 existing plus 20 new in `tests/test_ce_sec_003_security.py`.
  - The tests ran in a scratch virtualenv with `pydantic>=2`, because the system pydantic is v1.
  - One existing test (`test_policy_enforcer` test 7) now passes admin roles to `register_runtime_policy`. The endpoint requires them by design.
- **Live check on the synthetic bench,** site `erp001.localhost`, with the branch code put first on `PYTHONPATH` in a temporary container folder:
  - the patch created the tables;
  - two saves gave revisions 1 then 2 (CREATED, UPDATED), with 2 audit rows;
  - a Tier 0 save was refused;
  - a mismatched site was refused;
  - after a rollback, 0 test rows remained.
  - The two empty tables stay on the synthetic site.

## Not covered
- **Concurrency.** Two real concurrent writers were not run. `FOR UPDATE` is used, but the race is not tested on the bench.
- **The patch through `bench migrate`.** The patch ran by direct call, not through `bench migrate` with the app installed from this branch.
- **The HTTP surface.** The whitelisted endpoints were not called over HTTP through the gateway.

## Different-model review (Codex, GPT-6.1 Terra) and follow-up fixes
The review said not to merge yet. It found three blocking items, all fixed in this session:
1. **The store could delete a persisted Tier 0 row** if called directly. `delete_policy` now refuses `TIER0_` ids. Test added.
2. **A Frappe context without a session user was treated as standalone.** Frappe is now detected by the session user or by the request site. A Frappe context with no session gets no roles and has caller context refused. Test added.
3. **A broken database interface fell back to the in-memory store.** The store now uses memory only when it is explicitly standalone, meaning there is no Frappe request site. Inside a Frappe runtime, a missing `db.sql` raises `PolicyStoreError`. Test added.

Should-fix from the same review:
- **Creating a policy is now a plain INSERT** (no upsert). A concurrent creation of the same id now fails on the unique key instead of overwriting it at revision 1. A real concurrent run is still not done.
- **Audit immutability is by convention only.** It stays documented as such.

Evidence after the fixes:
- 111 unit tests, OK (24 in the security file).
- The live check on the synthetic bench passes again: revisions 1 and 2, Tier 0 and site mismatch refused, rollback clean.

Side note on the test suite:
- The existing test `test_live_mariadb_suite_b`, already on main, logs in to any MariaDB on `127.0.0.1:3306` as root/admin by default and creates its own database `ce_poc_db`.
- On this machine that port belongs to the old prototype's local database container, not the platform bench, so this session's runs and the reviewer's touched only `ce_poc_db` there.
- Nothing was deleted. The test should skip unless it is explicitly enabled; that change is proposed as a follow-up, not part of this PR.

## Decisions
- None.

## Tokens or cost
Unknown.

## Next step
A non-Claude reviewer reviews #34, then Eldon re-reviews. The live concurrency test belongs with ERP-021.
