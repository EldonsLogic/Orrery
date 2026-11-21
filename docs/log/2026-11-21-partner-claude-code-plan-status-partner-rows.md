# Session log: plan-status-partner-rows

Date: 2026-11-21
Author: partner
Tool and model: claude-code / claude-opus-5-5
Plan IDs: CE-SEC-005,SEC-004,ERP-009,CMP-006,CMP-021,ERP-020,ERP-027,ERP-023,PLT-024,ERP-026,CMP-033

## Summary
Checked eleven partner rows that were still `doing` after their PRs merged. For each one I compared the full row text with what main holds, the PR's last reviews and its session logs. Seven rows are now `done`. Four stay `doing`, and the table below gives the exact remaining item for each. Eldon asked for this check.

## Files touched
- `docs/PLAN.md`: status only, `doing` to `done` for CE-SEC-005, CMP-006, CMP-021, ERP-020, ERP-027, ERP-023, ERP-026. No other row, column or owner changed.
- This log.

## Decisions
Rule applied: a row is `done` only if every deliverable in its row text is on main and nothing the row promises is still open. Residual Low items from reviews that the row text does not promise are listed but do not keep a row open.

| Row | Merged PR(s) | Decision | Evidence | Remaining item (if `doing`) |
|---|---|---|---|---|
| CE-SEC-005 | #134 (2026-11-19) | done | `.github/workflows/real-bench.yml` and `infra/dev/docker/run_real_bench_ci.py` are on main. Eldon's Opus review approved with nits, all addressed in `c8294de`. `real-bench-tests` is green on the latest main-based PR runs on 2026-11-21 (16 live tests in run 44912765239). One earlier run on `erp-020-engine-headless` (44893242651) failed before that PR's token fix. | - |
| SEC-004 | #131 (2026-11-21) | doing | Suites, the fail-closed live runner and `.github/workflows/sec-004-live-isolation.yml` are on main. Eldon approved `3757d3f`. `gh run list --workflow sec-004-live-isolation.yml` shows no runs. | First green run of `sec-004-live-isolation.yml` on main, by the weekly schedule or `workflow_dispatch`. Eldon's review: the live suite has never run in CI. |
| ERP-009 | #162 (2026-11-21) | doing | Outbox emitter and hooks are on main. Eldon approved the Tier 3 change at `e3181d4`, with a post-merge concur and five Lows. | Q-311: provisioning allows hyphenated tenant ids that the emitter rejects, so the emitter cannot feed the stream for a provisioned tenant. The partner PR that resolves it must merge before the app is installed on any tenant (merge comment on #162). |
| CMP-006 | #161 (2026-11-21) | done | `apps/engine/compliance/ksa/` (58-account chart, 20 company defaults, VAT treatments with 16 reason codes), tests and `docs/compliance/ksa-coa-and-tax-codes.md` are on main. Eldon approved the Tier 3 change at `41b36d8`. The coordinator's brief says the founder waived the Arabic-speaking accountant review on 2026-11-21. That waiver is not recorded in the repo. | - (Note: the data stays `status: draft` and `review: unreviewed`. ADR-0031 condition 3 still requires accountant review before the status leaves draft, before Phase 2 and before any real data. Q-8 and Q-267 stay open.) |
| CMP-021 | #158 (2026-11-20) | done | `components/compliance/country_pack/` (schema, fail-closed loader, override merger, `resolve_country_pack` selecting from `company.country` and `compliance.countryPack`), tests, a CI step and `docs/compliance/country-pack-framework.md` are on main. Eldon's re-review on 2026-11-20: MERGE-READY, nothing remaining. | - (Q-289, Eldon's schema follow-up in `contracts/`, is an improvement, not a row deliverable.) |
| ERP-020 | #148 (2026-11-21) | done | Route guard, WSGI guard, internal-only compose networks (no published port, no egress) and tests are on main. Eldon approved the Tier 3 change at `f354379` after the real-bench token fix. | - (Residuals in other rows: full ADR-0016 invisibility needs PLT-024 and QA-016, the interim shared token is SEC-002's, and live `doc_events` enforcement is not exercised.) |
| ERP-027 | #125 (2026-11-19) | done | The DDL plan gate fix and tests for all four doctypes are on main. The live pinned bench applied fresh fields on Customer, Sales Order, Sales Invoice and Item, and a negative control rejected real drift (`2026-11-19-partner-codex-erp-027-review-fixes.md`). Eldon's Opus re-review: MERGE-READY on code; his `52c348b` comment said a Tier 3 line-by-line review was still needed, and no separate Tier 3 approval is recorded. Eldon merged it himself after CI passed. `real-bench-tests` has been green on later main-based runs. | - (Open Lows: the `FrappeDeploymentAdapter(offline_ddl_simulator=True)` env check and the `rev_default` fallbacks at `api/endpoints.py:327` and `:1647`.) |
| ERP-023 | #203 (2026-11-21) | done | `action_policy_enforcer.py`, `action_policy_store.py` and the tests against the SEC-019 table are on main. Eldon approved the Tier 3 change at `6cbd8b8`. All checks are green. | - (ADR-0027 is still Proposed and Q-44 is open. Eldon calls acceptance a separate founder edit. Outcome reconciliation is ERP-029. Untracked follow-ups: move the SQLite claims journal into the tenant database before a live handler, and bound refusal journal growth.) |
| PLT-024 | #123 (2026-11-21) | doing | The gateway edge core is on main. Eldon's last PR comment (2026-11-19, re-review of `f7e2d9c`) asked for a founder line-by-line review after the conflict fix. No review or approval is recorded on #123, and the partner merged it. | (1) Eldon's recorded Tier 3 line-by-line review of the merged `services/gateway/edge/` (ADR-0035). (2) The live binding that the row text names still waits on a durable audit spool, identity-bound audit records and size caps (`services/gateway/README.md`). No plan row owns that binding yet. Also open: the Low about refusing active content types (`image/svg+xml`, `application/xhtml+xml`, `text/xml`). |
| ERP-026 | #126 (2026-11-21) | done | ADR-0041, the MariaDB store, the production guard and the restart and restore tests are on main. The `ERP-026 adapter state on MariaDB 11.4` job passed on main (run 44909869640, `e6e48f7`). `real-bench-tests` is green. Eldon approved the Tier 3 change at `1218a20`. | - (ADR-0041 is still Proposed. Eldon calls acceptance a separate founder edit. The Low residuals in his review stay open.) |
| CMP-033 | #124 (2026-11-19) | doing | ADR-0042 is on main as Proposed. Eldon re-reviewed it as MERGE-READY as Proposed, not as Accepted. | The decision is not yet made. Before ADR-0042 moves to Accepted: founder answers to its open questions 1, 3, 4 and 5; both founders' sign-off on the pilot fallback signer exception; ADR-0038 accepted; and fixes for the two Medium design points (ICV-order submission per unit, permanent signer failure). |

## Verification
`check_docs.py`, `check_plan_independence.py`, `check_repo_hygiene.py`, `scan_secrets.py`, `check_lanes.py --base origin/main --actor partner` and `build_status.py` were run before commit. Results are in the PR.

## Tokens or cost
Unknown.

## Next step
Founders: record the CMP-006 accountant-review waiver, give the PLT-024 Tier 3 review, and decide whether ADR-0027, ADR-0041 and ADR-0042 are accepted. Partner: Q-311 fix (ERP-009), trigger `sec-004-live-isolation.yml` (SEC-004), and add a plan row for the PLT-024 live binding.
