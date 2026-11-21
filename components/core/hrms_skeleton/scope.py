"""Scope guard: the twelve doctypes ERP-010 may touch, and nothing else (default deny).

Source: docs/specs/core-module-scope-trading.md section 4. The allow-list is the guard. A name
that is not in it is refused, whether or not it appears in `KNOWN_OUT_OF_SCOPE_DOCTYPES`; that
list only documents the HR and payroll doctypes the founders named as excluded, and the tests
use it. It is not exhaustive and the guard never consults it.
"""

from __future__ import annotations

from .errors import HrmsError
from .specs import SPECS

ALLOWED_DOCTYPES = frozenset(SPECS)

KNOWN_OUT_OF_SCOPE_DOCTYPES = frozenset(
    {
        # Recruitment, onboarding and offboarding
        "Job Opening", "Job Applicant", "Job Offer", "Interview", "Staffing Plan",
        "Employee Onboarding", "Employee Separation", "Employee Promotion", "Employee Transfer",
        "Full and Final Statement",
        # Appraisal and training
        "Appraisal", "Appraisal Cycle", "Employee Performance Feedback", "Training Program",
        "Training Event", "Training Result",
        # Expenses, advances, travel
        "Expense Claim", "Employee Advance", "Travel Request",
        # Time and attendance, shifts, fleet
        "Attendance", "Attendance Request", "Employee Checkin", "Shift Type", "Shift Assignment",
        "Shift Request", "Vehicle Log", "Daily Work Summary",
        # Payroll runs and calculation outputs
        "Payroll Entry", "Salary Slip", "Additional Salary", "Employee Incentive",
        "Retention Bonus", "Payroll Period", "Income Tax Slab", "Payroll Settings",
        "Salary Withholding", "Employee Tax Exemption Declaration", "Employee Benefit Application",
        # End of service and gratuity
        "Gratuity", "Gratuity Rule", "End of Service",
        # Other leave machinery (balances are engine-computed, not ours)
        "Leave Encashment", "Compensatory Leave Request", "Leave Ledger Entry", "Leave Block List",
        "HR Settings",
        # Child rows are reached only through their parent, never directly
        "Leave Policy Detail", "Salary Detail",
    }
)


def is_allowed_doctype(doctype: object) -> bool:
    """True only for an exact, case-sensitive match of one of the twelve doctypes."""
    return isinstance(doctype, str) and doctype in ALLOWED_DOCTYPES


def assert_allowed_doctype(doctype: object) -> str:
    """Return the doctype if it is in scope, otherwise raise `doctype_not_allowed` (fail closed)."""
    if not is_allowed_doctype(doctype):
        raise HrmsError("doctype_not_allowed", doctype=doctype if isinstance(doctype, str) else None)
    return doctype  # type: ignore[return-value]
