"""Error type and bilingual messages for core.hrms_skeleton (ERP-010).

Every refusal is an `HrmsError` with a stable `code`. Customer-facing text comes only from
`strings.json` (Arabic and English); nothing here names the engine (ADR-0016).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent
STRINGS_PATH = PACKAGE_DIR / "strings.json"
LOCALES = ("ar", "en")

# Every code this component can raise. tests/test_strings.py checks that strings.json covers
# exactly this set, in both languages.
ERROR_CODES = frozenset(
    {
        "doctype_not_allowed",
        "session_invalid",
        "tenant_mismatch",
        "company_missing",
        "company_not_permitted",
        "company_mismatch",
        "caller_identity_not_accepted",
        "role_not_permitted",
        "permission_denied",
        "field_permission_denied",
        "payload_invalid",
        "field_not_allowed",
        "payroll_logic_not_allowed",
        "field_required",
        "invalid_text",
        "invalid_decimal",
        "decimal_out_of_range",
        "decimal_precision_exceeded",
        "invalid_date",
        "date_range_invalid",
        "invalid_choice",
        "invalid_boolean",
        "invalid_list",
        "duplicate_row",
        "employee_not_found",
        "record_not_found",
        "ambiguous_key",
        "decision_invalid",
        "self_approval_forbidden",
        "not_designated_approver",
        "leave_application_not_open",
        "leave_application_already_decided",
        "operation_failed",
    }
)


@lru_cache(maxsize=1)
def load_strings() -> dict[str, Any]:
    return json.loads(STRINGS_PATH.read_text(encoding="utf-8"))


class HrmsError(Exception):
    """A fail-closed refusal. `str(error)` is the stable code; use `message()` for display text."""

    def __init__(self, code: str, *, field: str | None = None, doctype: str | None = None) -> None:
        if code not in ERROR_CODES:  # a typo must not silently become a new, untranslated code
            raise ValueError(f"unknown error code {code!r}")
        super().__init__(code)
        self.code = code
        self.field = field
        self.doctype = doctype

    def message(self, lang: str = "en") -> str:
        locale = lang if lang in LOCALES else "en"
        return load_strings()["errors"][self.code][locale]
