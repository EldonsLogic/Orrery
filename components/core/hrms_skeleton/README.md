# core.hrms_skeleton

Status: draft (certification level `tested`; awaiting the named human review, ADR-0031 and ADR-0035 Tier 3)
Owner: partner

HR skeleton for v1 (plan row `ERP-010`). It prepares employees, leave and salary structure for WPS/SIF output (`CMP-015`, G3). It does **not** run payroll.

## What it does
- **Twelve doctypes, default deny.** `Employee`, `Department`, `Designation`, `Branch`; `Leave Type`, `Leave Period`, `Leave Policy`, `Leave Allocation`, `Leave Application`; `Salary Component`, `Salary Structure`, `Salary Structure Assignment` ([scope spec](../../../docs/specs/core-module-scope-trading.md) section 4). `is_allowed_doctype` / `assert_allowed_doctype` match exactly and refuse everything else, named or not. Child tables (`Leave Policy Detail`, `Salary Detail`) are reachable only through their parent.
- **No payroll maths.** No payroll run, salary slip, tax, GOSI or social-security formula, gratuity or end-of-service calculation, and no leave-balance calculation. Fields that carry a formula, condition or rate (`formula`, `condition`, `gosi_rate`, ...) are refused with `payroll_logic_not_allowed`. The component only checks and stores fixed configuration; the engine and the country packs own every figure (ADR-0031).
- **Exact values.** Amounts and days are `Decimal` from strings, ints or `Decimal`; floats, booleans, NaN, infinity, exponent notation, non-ASCII digits and negatives are refused, with a maximum, a decimal-place limit and a range per field. Dates are ISO `YYYY-MM-DD` and must be real calendar dates; a leave or period range cannot end before it starts.
- **Scope and identity.** One `HrmsService` is bound to one tenant and one company. The session's tenant, the store's tenant and the requested tenant must all match; the company must be permitted for the session user. Roles, user, approver, tenant and site are never read from a payload (`caller_identity_not_accepted`); they come from the authenticated session. Unknown fields are refused.
- **Roles.** The engine's own permission and permission levels apply as well as the role table below; both must pass.

| Action | Roles |
|---|---|
| `Employee`, `Leave Policy`, `Leave Allocation`, `Salary Component`, `Salary Structure`, `Salary Structure Assignment` | `HR Manager`, `System Manager` |
| `Department`, `Designation`, `Branch`, `Leave Type`, `Leave Period` | the two above and `HR User` |
| File or edit a `Leave Application` (only while `Open`) | the three above, and `Employee` for their own record only |
| Approve or reject a `Leave Application` | `HR Manager`, `Leave Approver`, `System Manager`; **never the applicant**, whatever roles they hold. A `Leave Approver` who is not `HR Manager` or `System Manager` must be the application's designated approver. |

## Keyed idempotent apply (ADR-0028)
Each record is found by a stable business key inside the tenant (and the company, where the doctype has one), then created, updated for changed fields only, or left alone. Re-applying never creates a duplicate and writes nothing when nothing changed.

| Doctype | Key |
|---|---|
| `Employee` | `employee_number` + company |
| `Department` | `department_name` + company |
| `Designation`, `Branch`, `Leave Type` | their name field |
| `Leave Period` | company + `from_date` + `to_date` |
| `Leave Policy` | `title` |
| `Leave Allocation`, `Leave Application` | `employee`, `leave_type`, `from_date`, `to_date` (+ company) |
| `Salary Component` | `salary_component` |
| `Salary Structure` | `name` + company |
| `Salary Structure Assignment` | `employee`, `salary_structure`, `from_date` (+ company) |

If two records match one key the apply stops with `ambiguous_key`; it never picks one.

**Activation and recovery.** `apply_configuration(records)` validates and role-checks every record before the first write, then applies them referenced-first (designations, branches, departments, employees, leave setup, salary setup). It does not keep its own journal. If a run stops part-way (a crash, a refused write), run the same configuration again: finished records report `unchanged`, the rest are created. The caller's guarded apply (ADR-0028) decides when to run it and records the result. Nothing is deleted by this component.

Leave decisions are separate: `decide_leave_application(key, "approve" | "reject")`. Re-sending the same decision reports `unchanged`; the opposite decision is refused (`leave_application_already_decided`).

## Files
- `scope.py`, `specs.py`: the allow-list, keys, fields and roles.
- `validation.py`: value and record checks. `service.py`: the guarded operations. `access.py`: the `Session` and `Store` interfaces.
- `frappe_backend.py`: adapters that run the service inside the engine as the calling user. `memory.py`: in-memory ones for tests.
- `strings.json`: Arabic and English text for every refusal code and doctype label. The Arabic is unreviewed (`reviewStatus: proposed_for_native_speaker_review`, ADR-0033). Nothing customer-facing names the engine (ADR-0016).

## Not verified yet
- Field names and engine calls have not been run on the pinned bench (Q-280). `testedAgainst` in the manifest is empty for that reason.
- Submitting or cancelling `Leave Allocation`, `Leave Application` and `Salary Structure Assignment` is not done here (Q-281).
- Platform HR role names do not exist yet (Q-282).
- Not reviewed by a named human, so `reviewedBy` is empty. It touches payroll structure, so ADR-0031 line-by-line review and the ADR-0034 reviewer rule apply before `reviewed`.

## Tests
```
python3 -m unittest discover -s components/core/hrms_skeleton/tests -t . -v
```
Needs `jsonschema` (installed in CI). The manifest test fails if it is missing.
