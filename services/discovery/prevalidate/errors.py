"""Coded refusals (fail closed). Messages carry the code and a key, never customer data."""
from __future__ import annotations

ERRORS = {
    "PRE-E01": "pre.err.dataset_shape",
    "PRE-E02": "pre.err.row_shape",
    "PRE-E03": "pre.err.config_invalid",
    "PRE-E04": "pre.err.too_large",
    "PRE-E05": "pre.err.names_shape",
}


class PrevalidationError(Exception):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.key = ERRORS[code]
        self.detail = detail  # a field name or limit, never row content
        super().__init__(f"{code} {self.key}" + (f" ({detail})" if detail else ""))
