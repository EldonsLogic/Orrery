# Session log: erp-015-review-round-2

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: ERP-015

## Summary
Fixed Eldon's cross-model review of PR #229 (review on 07a8ad4; branch head was 7ec5e55). The changes are to tests only; no product code changed. The tests now cover back-dated entries and reposting. The engine's own repost job is run in-process, and ledger, bins and GL are checked against the oracle in posting order. The full live layer passed on a fresh throwaway bench. ERP-015 stays `doing` until Q-514 is answered.

## Review findings
- Medium 1, back-dated entries and reposting: fixed.
  - `simulate()` now revalues the posted, uncancelled moves in posting order (date, then time) after every submitted move. An issue is rejected if, in posting order, it would leave any move short. A cancellation removes its move.
  - New forced cases on `E15-BACK`. `b3` and `b4` are receipts dated the day before every other move, `b5` cancels `b4` (a back-dated move), and `b6` issues after the repost.
  - Expected figures were worked out by hand in `BACKDATED_EXACT`: b3 400.00, b1 900.00 (rate 60), b2 660.00 / -240.00, b6 480.00 / -180.00, final bin 8 at 480.00. Without a repost b2 would stay at 300.00 / -200.00.
  - The probe runs `repost_entries` (the engine's hourly scheduler job; the dev bench has no worker) in-process after each move. It also dumps the posting date and time of every row and the Repost Item Valuation rows.
  - The new live `test_9` checks four things: the reposts ran and were dated from the back date, the ledger and bins match the oracle, `BACKDATED_EXACT` holds, and each b voucher's GL (Stock In Hand against Stock Adjustment) equals its reposted ledger difference. It also checks that b4's GL reverses exactly.
  - Offline: `test_oracle_replays_back_dated_moves_in_posting_order` covers the figures before and after the cancellation and shows that submission order differs. It also covers a back-dated issue that leaves a later issue short (rejected) and a cancellation that would leave a later move short (the oracle raises). Two new mutations are caught: a back-dated receipt not reposted, and a cancelled back-dated receipt not reposted.
- Medium 2, live module in the real-bench runner: not done in this PR, as instructed (another PR is changing `infra/`). The coordinator will record the gap as a plan row.
- Low 4: the `FORCED_EXACT["g6"]` comment now says it is a regression pin of observed engine behaviour under ADR-0031 and Q-514 (a), not an independent expectation.
- Low 5: fixed.
  - `check_run` now requires a `NegativeStock` error for g7, g12 and g14.
  - The "left nothing behind" check now works on the live path. It looks for any row of the move's item and warehouses at its recorded posting time, as well as by voucher. A rejected move has no voucher on the live path, and `perfect_engine` now gives it none too.
  - Every move's recorded posting time must match the oracle's order.
  - New mutations are caught: a rejection for another reason, a rejected move leaving a row, and a move posted at another time.
- Low 6: fixed. `test_6` and `test_7` first read the pinned engine figures: g6 at 2762.94 / 627.94, and q1 at 12.35 and 9.995951417. If a figure has changed, or the data cannot be read, the test returns without failing. unittest then reports an unexpected success, which fails the run, so the only failure the decorator can absorb is the known mismatch.
- Low 7: fixed. `_refuse_a_used_site` runs before any setting is changed. It refuses a site that has ERP-015 postings, any company other than the probe's own, or any GL entry.
- Mechanical: main merged with `git merge --no-ff origin/main`.
  - The only conflict was `docs/open-questions.md`. I kept both sides: our Q-514 and main's Q-515 to Q-519. `docs/tests.yml` merged cleanly.
  - Mistake: I made the merge commit with `-c core.hooksPath=.githooks`, a directory that does not exist, so the hooks did not run on it. I did not amend it. I ran the pre-commit hooks by hand on the merge range (`pre-commit run --from-ref HEAD^1 --to-ref HEAD`) and the commit-msg hook on its message, and all passed. The ERP-015 commit itself ran with hooks on.

## Evidence
- Live run on a new throwaway Compose project `erp015r2-3468` (no host DB port), fresh synthetic site `erp015r2c.localhost`: 18 tests, OK (expected failures=2). test_0 to test_5, test_8 and test_9 pass; test_6 and test_7 are expected failures.
- Two earlier sites on the same project failed before any check ran, for two reasons:
  - `erp015r2.localhost`: main's event stream (`record_events._site_tenant`) now needs `tenant_id` in the site config, so the probe's first Item insert failed. The module docstring now gives the `bench --site <site> set-config tenant_id t_<name>` step.
  - `erp015r2b.localhost`: posted fully, but exposed two of my bugs, both fixed. The posting-time check used op positions within an item subset, and is now caught offline. `test_9` filtered repost entries by voucher, but the engine reposts by item and warehouse.
- On `erp015r2b` the engine's E15-BACK ledger after the repost was b3 400 / b1 900 (rate 60) / b2 660 (-240) / b6 480 (-180). The cancelled b4 rows had `is_cancelled = 1`. All six Repost Item Valuation rows were `Completed` and `Item and Warehouse` based.
- Observed, not a decision: the repost deletes and recreates the GL rows of reposted vouchers (`repost_gle_for_stock_vouchers`) even with `enable_immutable_ledger = 1`. The setting only changes how cancellations post. Worth knowing for the audit-trail story; I did not add an open question.
- Probe refusal was checked in the bench container with a stub site: fresh and own-company-only sites are allowed; another company, GL entries and ERP-015 postings are refused. It also refused the used site `erp015r2c` for real.
- Offline: the ERP-015 module ran 18 tests, OK (10 live skipped). ERP-014 ran 16 tests, OK (7 skipped), on the engine path and through the infra loader. `scripts/tests` had 22 passed. `check_docs`, `check_repo_hygiene`, `scan_secrets`, `check_plan_independence` and `check_lanes --actor partner` all passed.
- Teardown: only my own project `erp015r2-3468` was removed, with its volumes.

## Files touched
- `apps/engine/change_engine/change_engine/tests/test_erp_015_inventory_valuation.py`:
  - posting-order oracle
  - back-dated cases and `test_9`
  - stricter `check_run`
  - `test_6` and `test_7` guards
  - g6 pin comment
  - docstring
- `apps/engine/change_engine/change_engine/tests/erp_015_bench_probe.py`:
  - per-move date and time
  - in-process repost
  - posting times and repost rows in the dump
  - used-site refusal
- `docs/open-questions.md`: merge resolution only (both sides kept).
- Merge of `origin/main` (the other files come from main).

## Decisions
- None. Q-514 stays open.

## Tokens or cost
Unknown.

## Next step
- ERP-015: answer Q-514, resolve `test_6` and `test_7`, then set ERP-015 to `done`.
- Coordinator: add a plan row to run the ERP-015 live module, with its back-dated cases, in the real-bench runner (`REQUIRE_ERP015_LIVE=1`). The bench needs `tenant_id` set on the site.
