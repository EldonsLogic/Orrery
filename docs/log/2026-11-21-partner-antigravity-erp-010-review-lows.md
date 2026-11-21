# Session log: erp-010-review-lows

Date: 2026-11-21
Author: partner
Tool and model: antigravity (Gemini 4 Argon)
Plan IDs: ERP-010

## Summary
Resolved the three Low findings from the cross-model review on PR #201 (`ERP-010` HR skeleton): restricted pay-affecting `Leave Type` fields (`is_lwp`, `is_ppl`, `fraction_of_daily_salary_per_leave`) to `HR_ADMIN_ROLES` and marked `Leave Type` as `riskClass: ledger` in the manifest; closed the self-service employee-ID oracle on `Leave Application` by returning `role_not_permitted` for both missing and non-owned employee records; and moved the `"Applicant account"` custom-field label into `strings.json` with unreviewed Arabic and English entries (`fieldLabels.applicant_account`).

## Files touched
- `components/core/hrms_skeleton/manifest.json`: marked the `Leave Type` entity artifact with `"riskClass": "ledger"`.
- `components/core/hrms_skeleton/specs.py`: added `DocSpec.admin_fields`, set `admin_fields=frozenset({"is_lwp", "is_ppl", "fraction_of_daily_salary_per_leave"})` on `Leave Type`, and read the `custom_applicant_user` label from `load_strings()["fieldLabels"]["applicant_account"]["en"]`.
- `components/core/hrms_skeleton/service.py`: added `_require_write_roles` so payloads containing any `spec.admin_fields` require `HR_ADMIN_ROLES` in both `upsert` and `apply_configuration` preflight/execution, and checked self-service ownership before raising `employee_not_found` so self-service callers receive `role_not_permitted` for both missing and someone else's employee IDs.
- `components/core/hrms_skeleton/strings.json`: added `fieldLabels.applicant_account` with English and Arabic (`حساب مقدّم الطلب`, covered by `reviewStatus: proposed_for_native_speaker_review`, ADR-0033).
- `components/core/hrms_skeleton/README.md`: documented the `HR Manager`/`System Manager` requirement for pay-affecting `Leave Type` fields.
- `components/core/hrms_skeleton/tests/test_manifest_and_scope.py`: asserted `Leave Type` has `riskClass: "ledger"` alongside the salary entities.
- `components/core/hrms_skeleton/tests/test_service.py`: added regressions for `Leave Type` pay-affecting fields (`upsert` and `apply_configuration` preflight) and the self-service employee-ID oracle.
- `components/core/hrms_skeleton/tests/test_strings.py`: added `test_applicant_account_label_has_english_and_arabic` verifying bilingual `fieldLabels.applicant_account` coverage and no hard-coded label in `specs.py`.

## Verification
- Applied test changes onto `origin/main` first and confirmed all new assertions failed before applying the implementation changes.
- `uv run --no-project --with jsonschema python -m unittest discover -s components/core/hrms_skeleton/tests -t . -v`: 149 passed (148/149 under bare system `python3` without `jsonschema`).
- `uv run --no-project --with pytest python -m pytest scripts/tests -q`: 22 passed, 29 subtests passed.
- `python3 scripts/check_docs.py`, `python3 scripts/check_repo_hygiene.py`, `python3 scripts/scan_secrets.py`, `python3 scripts/check_plan_independence.py`, `python3 scripts/check_lanes.py --base origin/main --actor partner`: all passed.
- Not verified locally: live Frappe/ERPNext bench execution (`Q-475` to `Q-477`) and native-speaker Arabic review (ADR-0033).

## Decisions
- Left `MONEY` scale at `2` in `specs.py` for now as currency-configurable scale belongs with multi-currency/country-pack wiring before 3-decimal currencies are enabled.

## Tokens or cost
Unknown.

## Next step
Cross-model review and Tier 3 founder line-by-line review (ADR-0031, ADR-0035) on the `ERP-010` follow-up PR.
