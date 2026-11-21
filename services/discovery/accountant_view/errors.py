"""Error type: a stable code, never owner or accountant text."""
from __future__ import annotations


class AccountantViewError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
