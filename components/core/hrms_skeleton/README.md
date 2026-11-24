# core.hrms_skeleton

Status: draft (certification level `tested`; awaiting the named human review, ADR-0031 and ADR-0035 Tier 3)
Owner: partner

HR skeleton for v1 (plan row `ERP-010`). It prepares employees, leave and salary structure for WPS/SIF output (`CMP-015`, G3). It does **not** run payroll.

## What it does
- **Twelve doctypes, default deny.** `Employee`, `Department`, `Designation`, `Branch`; `Leave Type`, `Leave Period`, `Leave Policy`, `Leave Allocation`, `Leave Application`; `Salary Component`, `Salary Structure`, `Salary Structure Assignment` ([scope spec](../../../docs/specs/core-module-scope-trading.md) section 4). `is_allowed_doctype` / `assert_allowed_doctype` match exactly and refuse everything else, named or not. Child tables (`Leave Policy Detail`, `Salary Detail`) are reachable only through their parent.
- **No payroll maths.** No payroll run, salary slip, tax, GOSI or social-security formula, gratuity or end-of-service calculation, and no leave-balance calculation. Fields that carry a formula, condition or rate (`formula`, `condition`, `gosi_rate`, ...) are refused with `payroll_logic_not_allowed`. The component only checks and stores fixed configuration; the engine and the country packs own every figure (ADR-0031).
- **Exact values.** Amounts and days are `Decimal` from strings, ints or `Decimal` and are checked and written back from their own digits and exponent, so the ambient decimal precision can never round a figure; floats, booleans, NaN, infinity, exponent notation, non-ASCII digits and negatives are refused, with a maximum, a decimal-place limit and a range per field. Dates are ISO `YYYY-MM-DD` and must be real calendar dates; a leave or period range cannot end before it starts.
- **Scope and identity.** One `HrmsService` is bound to one tenant, one company and one caller. The session's tenant, the store's tenant and the requested tenant must all match; the company must be permitted for the session user. None of this is cached: the live caller, both tenants and the company permission are re-read before every operation and every write, and a service whose caller, tenant or company access has changed refuses (`session_invalid`, `tenant_mismatch`, `company_not_permitted`) instead of carrying on. Roles are also re-read for each record of a configuration run. Roles, user, approver, tenant and site are never read from a payload (`caller_identity_not_accepted`); they come from the authenticated session. Unknown fields are refused.
- **Roles.** The engine's own permission and permission levels apply as well as the role table below; both must pass.

| Action | Roles |
|---|---|
| `Employee`, `Leave Policy`, `Leave Allocation`, `Salary Component`, `Salary Structure`, `Salary Structure Assignment` | `HR Manager`, `System Manager` |
| `Department`, `Designation`, `Branch`, `Leave Type`, `Leave Period` | the two above and `HR User` |
| File or edit a `Leave Application` (only while `Open`) | the three above, and `Employee` for their own record only |
| Approve or reject a `Leave Application` | `HR Manager`, `Leave Approver`, `System Manager`; **never the applicant**, whatever roles they hold. A `Leave Approver` who is not `HR Manager` or `System Manager` must be the application's designated approver: an absent, blank or non-text designation denies them. |

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

**Atomic per key.** Lookup and write run under the store's `key_lock` for (tenant, company where the doctype has one, doctype, key), so two simultaneous applies of one key give one create and one `unchanged`/`updated`, never two records. If the backend itself reports a duplicate on insert (`DuplicateKeyError`), the service looks the record up again once and takes the update path; a second duplicate is refused (`ambiguous_key`). A lock that cannot be taken refuses the write. The engine adapter uses a process lock plus a database advisory lock held until the write is committed (UNVERIFIED on the bench, Q-280).

**Employee sign-in link.** `Employee.user_id` decides who may act as that employee, so it is protected: an existing link is never changed through `upsert` (`identity_binding_protected`), and a caller can never link their own account. Linking an unlinked employee to another account is allowed for the administrator roles. A leave application records its applicant's account when it is filed (`applicant_user`, set by the service only, never accepted from a payload); a decision compares the caller with that record and with the employee's current link, and refuses (`applicant_identity_unresolved`) if either is missing, empty, not text, or they no longer agree. An application cannot be filed for an unlinked employee.

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
- `Employee` requires `gender` and `date_of_birth` (mandatory in the pinned ERPNext schema) and `Salary Structure` is created by `name`, a standard column handled at document level, not through field metadata. Both are checked against a fake that follows the pinned metadata rules, not a live bench.
- `applicant_user` on `Leave Application` is not a field the engine ships; it needs a custom field (or an equivalent store) before it works on the bench (Q-280). Until then the adapter's insert would drop it and every decision would refuse, which is the safe direction.
- The leave approver named on an application is whatever the filer entered, so a filer can name a colluding approver. Deriving the approver from the employee record's own approver (HR-set) is a follow-up, not done here.
- There is no administrator operation yet to move an employee to a different sign-in account.
- Not reviewed by a named human, so `reviewedBy` is empty. It touches payroll structure, so ADR-0031 line-by-line review and the ADR-0034 reviewer rule apply before `reviewed`.

## Tests
```
python3 -m unittest discover -s components/core/hrms_skeleton/tests -t . -v
```
Needs `jsonschema` (installed in CI). The manifest test fails if it is missing.
