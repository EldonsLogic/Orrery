# Session log: erp-011-trading-pack

Date: 2026-11-19
Author: partner
Tool and model: codex / gpt-6.1-sol
Plan IDs: ERP-011, ERP-028

## Summary
Prepared the native trading configuration pack: price lists, item prices, quantity discounts, company credit limits, rep master rates and draft-order attribution. No tenant activation or production certification is claimed. ERP-011 remains doing until merge; ERP-028 records missing runtime lifecycle/CI integration.

## Files touched
- components/sales/trading/: internal library, manifest, bilingual error keys, boundary tests, rollback-only native proof and operational limitations.
- docs/PLAN.md: claimed ERP-011 before code edits; added ERP-028 as a real activation dependency.
- This new session log only. No engine, gateway, contract, workflow, accepted ADR or other branch changes.

## Decisions
- Reuse native hooks and document/field permissions, without changing the authorization model. The host supplies its trusted current request and owns approvals, auditing and transactions. No caller-supplied identity/role/site and no permission bypass or commits in the library.
- Native hidden-field handling can silently restore protected values. Added explicit read/write checks for Customer.credit_limits and child company/limit/bypass fields; errors return only i18n keys, never hidden credit amounts.
- No financial calculations: engine computes price effects, credit exposure and commission estimates. Commission allocation only validates percentage shares. Accounting sensitivity is conservatively declared; no settlement, accrual, GL or payroll code.
- Retain the fictional sales.price_list ID and entity artifacts unchanged. The new sales.trading_distribution ID provides callable functions and requires an explicit fixture/mapping integration, not a silent replacement.

## Verification
- TDD red: 30 boundary acceptance failures before implementation. Green: 48 cases after native helpers and security edge coverage. Hidden credit-table tests then failed (2), and hidden credit-child tests failed (4), before the corresponding field-access checks were added.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=components/sales/trading COVERAGE_FILE=<temporary coverage file> python -m coverage run --branch --source=trading -m pytest components/sales/trading/tests -q`: 54 passed. `coverage report -m`: 125 statements, 0 missed; 36 branches, 0 partial; 100% implementation coverage. This excludes native engine internals, the integration fixture driver and UI/E2E coverage.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/blueprint python -m factory check components/sales/trading --run-tests --trusted-source --out <temporary report>`: ok true, levelReached tested, 54 blocking tests passed, 0 static findings. Run with the external session test environment, using the existing pytest/jsonschema requirements; no dependency files changed.
- Native `tests/bench_trading.py:run(engine)` through the pinned synthetic container: five proofs passed (price/list creation, scoped discount creation, positive credit upsert with bypass cleared, draft commission attribution with unchanged GL count, actual authenticated permission denial). Finalizer restored the original user and rolled back all fixture writes. Initial runs exposed missing synthetic masters; the proof now creates required masters within the same rollback-only transaction. No skipped bench test is counted as passing.
- Inspected installed module version strings: Frappe 15.126.0, ERPNext 15.124.5, HRMS 15.64.8. Image source SHAs could not be established (no source .git directories); source commit identity UNVERIFIED.
- Registry/schema probe: strict admission with the existing fixture registry passed, the sales.price_list fixture was unchanged, sandbox resolution passed, and production resolution refused with CMP-COMP-004.
- `python -m pytest services/blueprint/tests/registry services/blueprint/tests/factory -q`: 196 passed.
- `python3 scripts/check_docs.py`: 0 errors, 0 warnings. `check_repo_hygiene.py`: OK. `scan_secrets.py`: 0 hits. `check_plan_independence.py`: OK. `git diff --check`: clean.

## Runtime evidence and deferred dependencies
- apps/engine/change_engine/change_engine/adapter/frappe_backend.py, FrappeRuntimeBackend.execute_step: all branches inspected; no component lifecycle handlers and no unsupported-operation rejection at its tail.
- Instrumented subclass probe called component.enable, component.configure and component.disable with a site-session sentinel and no document APIs available. Each returned None without document calls. This proves the backend path is currently a silent no-op, not successful activation.
- guarded_apply/policy_enforcer.py registers TIER0_SO_CREDIT_LIMIT_BYPASS for Sales Order only. No claim is made for invoice/delivery enforcement, hidden balances across other surfaces, credit-controller exemptions, concurrency or discount approvals without end-to-end evidence.
- ERP-028: runtime handlers must apply the pack under caller scope, fail closed on unsupported operations, integrate fixture IDs/mapping, wire its tests into CI, and prove activation/recovery. ERP-023 owns action-policy/approval enforcement.
- Certification: local factory reaches tested, with accounting sensitivity true, no reviewer or fabricated CI/canary evidence. Existing CI does not run this pack; publication is deferred to ERP-028. Native version compatibility is based on the local rollback-only proof, not a production or CI certificate.
- Accountant treatment review, independent cross-model/founder review and native Arabic/RTL review are outstanding. No phase/gate exit.

## Tokens or cost
Not measured.

## Next step
Independent review of this PR, then ERP-028 integration. No subagents, messages, PR watching, force pushes or merges were used. Vercel deployment failures are ignored per the task instruction.
