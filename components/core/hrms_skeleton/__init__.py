"""HR skeleton: employees, leave and payroll structure, only what v1 needs (ERP-010).

Twelve doctypes, default deny for the rest. Keyed idempotent configuration, backend roles and
tenant scope, exact decimal and date validation. It computes no pay, tax or leave balance.
"""

from .errors import ERROR_CODES, HrmsError
from .scope import (
    ALLOWED_DOCTYPES,
    KNOWN_OUT_OF_SCOPE_DOCTYPES,
    assert_allowed_doctype,
    is_allowed_doctype,
)
from .service import ApplyResult, HrmsService

__all__ = [
    "ALLOWED_DOCTYPES",
    "ERROR_CODES",
    "KNOWN_OUT_OF_SCOPE_DOCTYPES",
    "ApplyResult",
    "HrmsError",
    "HrmsService",
    "assert_allowed_doctype",
    "is_allowed_doctype",
]
