"""Typed build-state errors. Codes are stable and messages fixed (no content); labels.json has the bilingual text
under `bs.error.<code>`."""

CODES = {
    "BS-001": "input is not valid", "BS-002": "time is out of range", "BS-003": "actor not verified or not allowed",
    "BS-004": "build not found", "BS-005": "transition not allowed from this state",
    "BS-006": "evidence missing, invalid or not eligible", "BS-007": "separation of duties",
    "BS-008": "content changed since the evidence", "BS-009": "confirmations incomplete",
    "BS-010": "an apply is in progress or its outcome is unknown", "BS-011": "stored record failed its integrity check",
    "BS-012": "integrity key missing or weak", "BS-013": "build already exists", "BS-014": "duplicate sign-off record",
    "BS-015": "apply failed", "BS-016": "rollback not allowed", "BS-017": "tenant mismatch",
}


class BuildStateError(Exception):
    def __init__(self, code: str, detail: str = ""):
        self.code = code if code in CODES else "BS-001"
        self.detail = detail  # an enumerated reason or an identity code, never content
        super().__init__(f"{self.code}: {CODES[self.code]}")
