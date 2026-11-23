# Session log: erp-013-opening-balances-importer

Date: 2026-11-19
Author: partner
Tool and model: codex / gpt-6.1-sol, high reasoning effort
Plan IDs: ERP-013

## Summary
Implemented the staged opening-balance/master-data importer with a transactional offline reference backend, real upstream contract fixtures and a Tier 3 review boundary. No production ledger posting or phase/gate exit is claimed.

## Files touched
- `apps/engine/change_engine/change_engine/importer/`: bounded default-deny validation, exact Decimal reconciliation, explicit tabular mapping, bilingual errors, context/report-bound hash, authenticated human confirmation, tenant/company isolation and atomic journaled storage.
- `apps/engine/change_engine/change_engine/tests/test_erp_013_opening_importer.py`: synthetic regression/integration tests against actual DSC-011 CSV/XLSX extraction and DSC-019 reports, including restart, concurrent writers and rollback after journal insertion.
- `.github/workflows/tests.yml`: one importer step added; all existing main steps retained.
- `docs/PLAN.md`: only ERP-013 changed, claimed doing then marked done for implementation per the brief. Review and real-data acceptance are not implied.
- New ADR-0045, its index entry and this new log. No already-merged log or Eldon-lane source was edited.

## Implementation brief and decisions
The user assigned this session as partner's implementation sub-agent: implement ERP-013 under the engine importer path; inspect DSC-011/019 and the adapter read-only; allowlist Customer/Supplier/Item/Warehouse/Account; validate exact trial balance, AR/AP and stock controls; block quarantine and unconfirmed duplicates; implement validate/preview/hash-bound human apply, backend roles, scoped idempotency and full rollback; provide bilingual engine-neutral errors, regression/integration tests, CI and README; push the named branch and open a Tier 3 PR without merging or polling CI. Only reserved Q-290–Q-299 could be used for genuine new questions; no question entries were needed.

- [ADR-0045](../decisions/ADR-0045-opening-import-transaction-boundary.md) proposes the injected session/transaction boundary; it is not accepted by this implementation.
- DSC-019's complete v1 report is mandatory and bound to all mapped source rows. It has no confirmation contract: any findings, quarantine, owner review or name groups block apply. A clean report must be regenerated upstream after resolution. A report is evidence, not signed authentication; trusted intake must generate it.
- Every trial-balance line states its control classification. Mixed currencies within a batch fail closed. Source numbers are never corrected. Stock rounded values are comparisons only, using ADR-0033 ROUND_HALF_UP.
- SQLite demonstrates atomic reference import records and the durable journal, not native GL/subledger/stock posting. No public endpoint or implicit simulated fallback was introduced. A live backend must prove native document permissions, account/link classification, same-transaction posting/journal behavior and avoidance of duplicate control effects before customer use.
- Implementation spans more than the approximate 400-line guideline because the requested entity, security, upstream and failure-boundary cases are delivered together. Each source/test file remains below 500 lines. Tier 3 review must assess the complete boundary; no checks or approval gates were bypassed.

## Verification
- Initial importer collection failed because the new package API did not exist. Tests were written before implementation. Early failures exposed an incomplete XLSX fixture and quarantine error precedence; both were fixed.
- Additional failing regressions exposed inherited Decimal exponent/trap settings, downgraded report findings and malformed duplicate-group collections. Each fails closed after its fix. Final self-review also added a failing regression for master-before-detail writes and fixed the ordering.
- Importer suite: 61 pass locally. Exact `0.1 + 0.2 == 0.3`, one-cent imbalance, all reconciliation classes, formula payloads, float/nonfinite rejection, caps, report provenance, role/session denial, confirmation, hash mutation, restart/concurrency, tenant/company isolation and full insert/update/journal rollback are covered.
- Earlier offline engine run: 238 pass, 16 skip, 54 subtests pass. Combined upstream connector/prevalidation plus importer run before the last two tests: 170 pass. Final Python 3.12 combined run (offline engine plus DSC-011/019 suites): 353 pass, 16 skip, 54 subtests pass.
- An unrestricted engine-suite run stopped during collection: the existing live `test_live_mariadb_suite_b.py` imports unavailable `pymysql`. It was explicitly excluded from the offline run; no live database or bench evidence is claimed.
- Main advanced while working. A first lane check compared the old branch head against newly fetched main and reported upstream Eldon paths. Updated with `git pull --rebase origin main`; no conflicts, and the lane check then passed with no foreign edits.
- Required repository checks pass: docs (zero errors/warnings), hygiene, lanes against origin/main, secret scan (zero hits), plan independence and git diff whitespace. The post-push closure command is `python3 scripts/finish_session.py`; its final outcome is reported with the PR handoff. CI is not polled under this brief.

## Tokens or cost
Unknown.

## Next step
Different-model security/code review and Eldon's named, dated line-by-line human review (Tier 3, ADR-0031/0035), then native Arabic review. No merge is authorised by this brief. Native production posting and applicable accountant/phase-exit evidence remain unverified.
