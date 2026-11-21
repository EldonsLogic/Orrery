"""Quote errors: a stable code and a short detail. Fail closed: a refused input never yields a partial quote."""
from __future__ import annotations


class QuoteError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
