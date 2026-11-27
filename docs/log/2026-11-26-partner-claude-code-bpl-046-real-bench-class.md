# Session log: bpl-046-real-bench-class

Date: 2026-11-26
Author: partner
Tool and model: claude-code / claude-sonnet-5-5 (worker), claude-opus-5-5 (coordinator)
Plan IDs: BPL-046

## Summary
BPL-046 (BPL-041 slice 2): real-bench CI gets a BPL-027 phase that runs the trading-fixture bench class on a fresh site with `REQUIRE_BPL027_LIVE=1`, so any skip or a vacuous run fails. Coordinated from docs/log/2026-11-26-partner-claude-code-partner-g1-sprint.md.

## Task trail
- Worker A: Claude Sonnet 5.5 high (T3 `delegate_task`, own worktree from main, no git). Allowed paths: `infra/dev/docker/run_real_bench_ci.py`, `infra/dev/docker/docker-compose.bpl027-test.yml`, `infra/dev/docker/tests/`, `infra/dev/docker/README.md`, `.github/workflows/real-bench.yml`.
- `run_real_bench_ci.py`: layers the BPL-027 compose file. It adds a last phase: pinned requirements install, a fresh `bpl027-*` site, an in-container class run, `REQUIRE_BPL027_LIVE=1`, at least 10 live tests, any skip fails. It shares the pass/fail check with ERP-014 and ERP-015.
- `docker-compose.bpl027-test.yml`: read-only `docs/brand/tools` and `docs/brand/tokens` mounts. Without them the fixture compile fails (`BP-BRAND-001`).
- `real-bench.yml`: timeout 75 to 90 minutes. The phases total 4770 s, leaving 630 s of headroom.
- Runner tests: 135 run, OK, 10 skipped (baseline 125). Change-engine suite: 1853 passed, 86 skipped.
- Local bench run of the new phase alone (scratch driver, longer limits): 10 ran, 7 failed. `test_01`, `test_01b` and `test_02` passed. `test_03` ended `recovery_required` at step 42 (`entity.add /entities/customer`): "DDL rejected before execution: executed ADD COLUMN clauses differ from the approved plan" (`custom_customer_code varchar(140)`). Tests 04 to 08 failed on that missing prerequisite.
- Likely cause (UNVERIFIED): the plan uses `length` = `maxLength` 20, while `apply_native_custom_field` omits `length`. Engine fix dispatched to Claude Opus 5.5 in this worktree (hard debugging, DDL path).
- A2 (Claude Opus 5.5 high, same worktree, no git): root cause of the step 42 refusal. The plan builds the column from `length` and `precision` (`schema_reconciler.py:477`, `:577`), but `apply_native_custom_field` (`api/endpoints.py:1746`) left both off the Custom Field, so Frappe used varchar(140) and decimal(21,9). Fix: 4 lines pass `length` and `precision`; the DDL gate is unchanged. New `test_bpl_046_field_length_ddl.py`: 5 tests, 3 failed before the fix, all pass after; one checks the gate still refuses a mismatch. Wired into the BPL-027 step of `tests.yml` (that step 106 passed, 10 skipped). Full suite 1858 passed, 86 skipped.
- Bench after the fix (three fresh sites, same result): test_01, test_01b and test_02 pass; steps 42 to 55 apply, and the columns come out as planned (varchar(64), decimal(21,2), decimal(21,3)). test_03 now fails at step 56 (`entity.add /entities/sales_invoice_line`): for `custom_item` the engine's own plan also contains `ALTER TABLE tabSales Invoice Item ADD INDEX creation`, and the gate rightly refuses an unapproved index. `Sales Invoice Item` has `sort_field = creation` and no `creation` index on a fresh site, and Frappe adds that index on every schema sync. This needs a founder decision; tests 04 to 08 are not reached.
- Also found: after that refusal (no field write, no audit row), the rollback ended `recovery_required` with an export hash different from before the apply. Cause UNVERIFIED, code in `adapter/engine.py` (`_compensate`); candidate for BPL-033.
- Cleanup: the `bpl046fix-*` stack, volumes, networks, image and env file removed; no other container touched.
- Founder decision (partner, 2026-11-27): option A. Provisioning adds the indexes the engine expects, before any apply, on every tenant site. The DDL gate stays exact.
- A3 (Claude Opus 5.5, same worktree, no git): option A plus Eldon's three Lows from his #381 review.
  - Root cause: Frappe's `MariaDBTable.create()` adds no `creation` index. `alter()` adds one for every `sort_field = creation` table (`frappe/database/mariadb/schema.py:84`) and adds missing `search_index` indexes (`:78`). A dry run of Frappe's own `updatedb` on all 838 tables of a fresh site found 61 `sort_field = creation` tables, all without the index, plus `tabAddress Template` `country_index`. It also found 277 MODIFY re-emits, mostly decimal defaults read back as `0.000000000` (plus a few such as `link_filters json`), so a full sync is not acceptable. UNVERIFIED: that every one is in the gate's no-op allow-list.
  - Provisioning (`scripts/provision_tenant_site.py`): after `bench new-site`, `INDEX_SYNC_PY` runs Frappe's `updatedb` on every non-single, non-virtual table. It sends only the `ADD INDEX` statements. MODIFY-only statements are not sent, and any other DDL (ADD COLUMN, DROP, ADD UNIQUE, create table) fails closed. Provisioning fails if the report is missing or unreadable. The report is returned and printed.
  - Runner: the brief assumed the runner used this script; it does not. `run_real_bench_ci.py` has its own `bench new-site`, so its `_provision_site` now runs the same `INDEX_SYNC_PY` (imported from the script) last in the same `sh -e` call, on all four sites.
  - Still on their own `bench new-site`, not converted: `smoke_headless_engine.py`, `run_50_tenant_load_spike.py`, `run_phase0_proofs.py`.
  - Lows:
    - The phase installs every pin of `services/blueprint/requirements.txt` except pytest.
    - `PROVISION_TIMEOUT` = 360 s new-site + 120 s index sync.
    - `VALUATION_TEST_TIMEOUT` 900 to 600 s (the layers took 22 to 36 s in CI runs 45998661302 and 46000455776). Phase total 4890 s; the job stays at 90 min, leaving 510 s of headroom.
    - `real-bench.yml` paths gain `services/blueprint/**`, `contracts/**` and `docs/brand/**`.
  - Bench (local, fresh `bpl027-a1` site through the changed runner path):
    - Provisioning plus index sync took 341 s. The sync added 62 indexes and did not send 277 MODIFYs; a second run on the same site after the class, through `index_sync_command`, added 0. The pip install took 5 s.
    - test_01, test_01b, test_02: pass.
    - test_03: step 56 now applies. It fails at step 57 (`entity.add /entities/sales_order`): Frappe refuses its `sales_quote` Link Custom Field (`WrongOptionsDoctypeLinkError`). The options come from the `entity_to_doctype` fallback `Sales Quote` (`adapter/mapping.py:209`, used at `adapter/frappe_backend.py:616`); `entity.add /entities/sales_quote`, which creates it, is step 59 (offline compile of the same artifact). A plan-order defect: a Link is added before its target document type. Outside this task's paths; stopped.
    - The compensate step after that failure again ended `recovery_required` (BPL-033), a stop condition. Cause UNVERIFIED, not fixed. Data point: `CustomField.on_update` validates the fields before the schema update, so no DDL was sent for step 57.
    - test_04 to test_08: fail on the missing `applied` prerequisite (not reached). The BPL-032 role.upsert gap (test_06) is not reached.
  - UNVERIFIED: the ce005, erp014 and erp015 sites with the index sync were not run locally; real-bench CI runs them. Tables created later (a custom document type made by an apply) are not covered by provisioning.
  - Checks:
    - Change-engine suite: 1882 passed, 86 skipped.
    - Runner tests: 136, OK, 10 skipped.
    - Provisioning tests: 17, OK (3 new).
    - `check_docs`, `check_repo_hygiene` and `check_plan_independence`: OK.
  - test_06 of the provisioning tests now checks only the set-config commands for `python` (the index sync is a python program).
  - Branch diff 583 added, 48 removed lines against the merge base: over the 400-line guide.
  - Cleanup: the `bpl046a-bench` stack, volumes, network, image and scratch env file removed.
- Eldon's review at 68a964cc (Sonnet 5.5 for him): the three Lows closed; one Medium: the index sync checked only how a statement starts, so `ADD INDEX a, DROP INDEX b` or `ADD INDEX a; DROP TABLE x` would be sent, and `MODIFY x, ADD INDEX y` was skipped whole. Fixed by the coordinator: each statement is split into top-level clauses (outside parentheses, backticks and quotes); a `;`, an unbalanced statement, any clause other than ADD INDEX or MODIFY, or any UNIQUE outside backticked names fails closed; only the ADD INDEX clauses run, rebuilt into one statement; MODIFY clauses are counted. Tests for the review's cases plus a quoted comma and a `unique_code` column; two mutants (check only the first clause; no clause split) each fail 4 tests. Idempotence stays a manual bench check (stated in the comment); `INDEX_SYNC_TIMEOUT` is a budget only (stated).

## Files touched
- apps/engine/change_engine/change_engine/api/endpoints.py (pass `length` and `precision`), apps/engine/change_engine/change_engine/tests/test_bpl_046_field_length_ddl.py (new), .github/workflows/tests.yml (one step line).
- scripts/provision_tenant_site.py and apps/engine/change_engine/change_engine/tests/test_erp_003_tenant_provisioning.py (BPL-046 index sync).
- infra/dev/docker/run_real_bench_ci.py, infra/dev/docker/docker-compose.bpl027-test.yml, infra/dev/docker/README.md, infra/dev/docker/tests/test_erp_031_real_bench_valuation.py, infra/dev/docker/tests/test_ce_sec_005_real_bench_ci.py, infra/dev/docker/tests/test_inf_015_redis_auth.py, .github/workflows/real-bench.yml.

## Decisions
- Coordinator: the PR opens only once the class passes, or with the next defect named. Merging the phase while the class fails would turn real-bench CI red on every engine PR.

## Tokens or cost
Unknown.

## Next step
- Plan order for step 57 (a Link added before its target document type), then the BPL-033 compensate failure, then a full local run of the phase, then the PR. Real-bench CI stays red on this branch until then.
- UNVERIFIED: the 600 s class limit is unmeasured for a passing run (the failing run took 106 s locally).
- Noted, not changed: the change-engine README's BPL-027 section is stale. The `tests.yml` infra filter (`infra/`, `apps/engine/`) does not cover `scripts/`, so a change to `scripts/provision_tenant_site.py` alone skips the runner tests that now import it (the ERP-003 step, gated on `engine`, misses it too).
