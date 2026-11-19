# Session log: erp-013-review-fixes

Date: 2026-11-19
Author: partner
Tool and model: codex / gpt-6.1-sol, high reasoning effort
Plan IDs: ERP-013

## Summary
Addressed PR #202's HIGH-1, MED-1 through MED-4 and actionable LOW findings with adversarial regressions. The deterministic importer and SQLite reference backend remain under Tier 3 review; live financial posting is UNVERIFIED and ERP-013 remains doing.

## Files touched
- `apps/engine/change_engine/change_engine/importer/`: server-side DSC-019 checks, scoped master resolution and snapshots, atomic company opening guard, early capability authorization, bounded error/failure handling, currency allowlist and Unicode formula defense; README records exact limits and offline scope.
- `apps/engine/change_engine/change_engine/tests/test_erp_013_review_fixes.py`: forged-clean Arabic duplicate attacks at all three stages; duplicate batch IDs and competing connections; prior-value audit and rollback; missing controls/details, dangling references and classification bypass; stale master approval; Unicode formulas, caps, authentication, failure retention, currencies and mapped capabilities.
- Existing importer tests: valid fixtures include masters and controls; scope denials cover preview as well as apply. Financial precision and rollback coverage retained.
- `.github/workflows/tests.yml`: include both importer test modules in the existing step; no other CI step changed.
- `docs/PLAN.md`: ERP-013 doing, partner-owned, offline-ready and live-pending Q-303.
- New Q-303, proposed ADR-0046 and its index entry, and this new log. Discovery source, other founders' paths and old logs/ADRs were read-only.

## Decisions and review disposition
- User explicitly assigned partner (`sayegh9`); `gh api user` confirmed the account. Fetched and checked out the requested branch; read the full Claude Sonnet 5.5 review at head `9a8426915e178284c60d7791fc80427671322de3`.
- HIGH-1: supplied DSC-019 evidence cannot authorize a batch. Each stage directly reruns the unmodified deterministic producer on submitted datasets with server-owned entity mappings. Import schemas supply their own required-field checks rather than transaction-document defaults. Findings, quarantine and name groups fail closed even under an internally consistent forged report.
- MED-1: one opening per tenant/company, independent of batch ID/date, serialized with writes and journal. Existing reference opening records also block a new claim. No supersede/reversal path is invented; master-only batches remain allowed.
- MED-2: approval hashes cover prior/next master state and referenced masters; apply recomputes under the write transaction. The journal stores verbatim before/after values. Rollback removes claims, writes, journal and audit, restoring prior records. Exact committed retries use their original hash plus a normalized source digest.
- MED-3: nonzero control lines require matching details, including offsetting lines with net zero. Details require a corresponding control and exact totals. Account/customer/supplier/item/warehouse links resolve against the batch or existing scoped masters; existing account types cannot be reclassified through this importer.
- MED-4 / LOW-3: checked open questions on origin/main before adding reserved Q-303. Live Frappe Opening Invoice Creation Tool / Journal Entry / Stock Reconciliation wiring, control effects and roles remain UNVERIFIED. Requested ADR-0039 is absent from the checked main branch; Q-303 records that unresolved reference rather than inventing an accepted mapping.
- LOW-1: NFKC detection copy and leading Unicode whitespace/Cf/Cc handling catch fullwidth and invisible-prefix formulas; all text Cf/Cc controls are rejected without changing accepted spelling.
- LOW-2: explicit supported ISO-4217 subset SAR/AED/EGP/QAR/USD/EUR/GBP; arbitrary three-letter codes fail closed. Currency precision remains an explicit reviewed configuration input.
- LOW-4: authenticate before data traversal in every stage. Public errors stop at one, with an explicit possible-truncation flag. DSC-019's accumulating API is bounded to 250 rows per entity and a conservative two-million-cell pairwise name comparison budget. Sanitized failure history retains at most 256 rows per tenant; initial validation/auth refusals write none. Backend read failures are sanitized.
- LOW-5: generic importer requires backend-issued `opening_import`; only the offline backend maps trusted legacy engine role names. Proposed ADR-0046 records these additional security/transaction boundaries; it accepts no prior proposal or human review gate.
- The user requested all findings and regressions in the existing PR. This exceeds the approximate small-PR guideline; every source/test file remains below 500 lines. No merge or phase/gate exit is authorized or claimed.

## Verification
- Initial adversarial run: 31 failed, one passed, reproducing forged clean reports, duplicate openings, missing snapshots/reconciliation/links, Unicode formula bypasses, late auth and unbounded failure storage. Additional failing tests exposed an existing-master reclassification bypass, offsetting control lines without details, unsanitized backend read exceptions and excessive long-name comparison work; each was corrected.
- Mutation verification: relaxing the upstream row budget makes `test_upstream_findings_are_bounded_before_calling_accumulating_api` fail. Restored original source bytes in a finally block; the regression then passes.
- Final Python 3.12 importer suites: 101 passed (61 original cases plus 40 review regressions).
- Final offline engine suite: 281 passed, 16 skipped, 54 subtests passed. Explicitly excludes only `test_live_mariadb_suite_b.py`.
- Full discovery suite (read-only dependency verification): 462 passed, 5 expected failures.
- Unrestricted engine run initially failed collection for missing pymysql. Installed that test dependency only in the external test environment, then reran: 279 passed, 16 skipped, 54 subtests passed, five existing live-suite setup errors because the local MariaDB connection was refused. Failing live cases: `test_case_1_get_lock_contract_and_connection_drop`, `test_case_2_metadata_lock_contention_and_fail_fast_timeout`, `test_case_3_concurrent_user_request_latency_during_ddl_queueing`, `test_case_4_end_to_end_snapshot_reconciler_under_live_contention`, `test_case_4b_happy_path_deployment_on_unlocked_table`. No live bench or posting evidence is claimed.
- Bare repository pytest collection failed on the existing duplicate `test_review_fixes` module names in control-plane identity and operate runtime. An importlib-mode diagnostic also failed collection on existing local-helper/conftest imports: brand `test_derive_tenant_theme`, `test_tenant_contrast`; blueprint adapter `test_adp_apply`, `test_adp_envelope`, `test_adp_members_events`, `test_adp_plan_preview`, `test_adp_rollback_export`, `test_adp_site_artifact`, `test_fake_selfcheck`; compiler `test_cmp_snapshots`; factory `test_analysis`, `test_factory`; registry `test_registry_admission`, `test_registry_compat`, `test_registry_queries`, `test_registry_store`; identity `test_mfa_review_fixes`, `test_mfa_service`; operate `test_stream`, `test_authority`, `test_loop`, `test_review_fixes`, `test_trace_gateway`, `test_errors`, `test_manifest_classes`, `test_toolapi`. These unrelated paths were not edited; a repository-wide green test claim is not made.
- Required docs, hygiene, partner lane check against origin/main, secret scan, plan independence and whitespace checks pass. A broad collection run generated ignored pytest cache node IDs containing synthetic security-test strings, which the secret scanner flagged; removed that generated cache and reran the unchanged scanner.
- Post-push closure uses `python3 scripts/finish_session.py`; its actual outcome is reported in the PR reply. CI is not polled. No merge is performed.

## Tokens or cost
Unknown.

## Next step
Different-model re-review of the corrected head, Eldon's named/dated Tier 3 line-by-line human and security review, native Arabic review, and Q-303 live posting/role mapping evidence. ERP-013 stays doing. Do not merge under this brief.
