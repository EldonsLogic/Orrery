# Session log: bpl-046-index-sync

Date: 2026-11-27
Author: partner
Tool and model: claude-code / claude-sonnet-5-5 (worker), claude-opus-5-5 (coordinator)
Plan IDs: BPL-046

## Summary
BPL-046: split from draft PR #381 on Eldon's offer, so the provisioning index fix and the field length and precision fix can merge before the BPL-027 bench class is green.

## Task trail
- Worker: Claude Sonnet 5.5, own worktree from main, no state-changing git. Source: branch `bpl-046-real-bench-class` (#381, head 553b9937); the original work and its reviews are described in that branch's session log.
- Taken whole (unchanged on main since the merge base): `api/endpoints.py`, `test_bpl_046_field_length_ddl.py`, `scripts/provision_tenant_site.py`, `test_erp_003_tenant_provisioning.py`.
- 553b9937 landed on #381 during this session (Medium from Eldon's re-review: a quote inside a SQL comment could carry DDL along with an index clause; every sent clause must now fully match Frappe's index shape). Both files were taken again at that commit.
- Taken in part: the `tests.yml` step line; the runner's index-sync call and report, `NEW_SITE_TIMEOUT` 360 s, `INDEX_SYNC_TIMEOUT` 120 s, `PROVISION_TIMEOUT` 480 s, `VALUATION_TEST_TIMEOUT` 600 s; one new runner test; the README paragraph.
- Budget: the phases that remain total 3690 s (300+120+480+60+120+300+2x480+2x600+30+120). `real-bench.yml` is unchanged: its 75 minutes (4500 s) leave 810 s, above the 300 s headroom the test requires. Its path filters already list `scripts/provision_tenant_site.py`.
- Checks: change-engine suite 1883 passed, 86 skipped. Runner tests 126 run, OK, 10 skipped. Provisioning tests 18, OK.
- Real bench, from #381's CI (read only): in runs 46009708802 (68a964cc) and 46049294094 (311e58ac) the index sync ran on the ce005, erp014 and erp015 sites and the CE-SEC-005 (16), ERP-014 (7) and ERP-015 (10) tests passed; those runs failed in the BPL-027 class.
- UNVERIFIED: the stricter index match of 553b9937 on a real bench (#381 run 46050437048 was still in progress; no bench was run in this session). This PR's own real-bench CI run covers it.
- UNVERIFIED: the timings in the runner comments (new-site, index sync, valuation layers) are carried over from #381, not measured again.

## Files touched
- apps/engine/change_engine/change_engine/api/endpoints.py: pass `length` and `precision` to the Custom Field.
- apps/engine/change_engine/change_engine/tests/test_bpl_046_field_length_ddl.py: new.
- .github/workflows/tests.yml: that test added to the BPL-027 offline step.
- scripts/provision_tenant_site.py: `INDEX_SYNC_PY`, `index_sync_command` and the fail-closed provisioning step.
- apps/engine/change_engine/change_engine/tests/test_erp_003_tenant_provisioning.py: index sync tests.
- infra/dev/docker/run_real_bench_ci.py: index sync on every provisioned site; timeouts.
- infra/dev/docker/tests/test_erp_031_real_bench_valuation.py: runner test for the index sync and its time limit.
- infra/dev/docker/README.md: index sync paragraph.

## Decisions
- None new. The index sync follows the partner's option A, recorded in #381's session log; the DDL gate is unchanged.

## Tokens or cost
Unknown.

## Next step
BPL-046: #381 keeps the BPL-027 phase as a draft until BPL-051, BPL-033 slice 1 and BPL-032 land.
