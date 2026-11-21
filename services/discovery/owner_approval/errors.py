"""Typed owner-approval errors. Codes are stable; messages are fixed text (never owner or Blueprint text)."""

CODES = {
    "OA-001": "input is not valid", "OA-002": "time is out of range", "OA-003": "actor not verified or not allowed",
    "OA-004": "a source answered wrongly or is missing", "OA-005": "the build is not in a state that allows this",
    "OA-006": "the draft or the quote changed since it was shown", "OA-007": "this owner already decided on this version",
    "OA-008": "the draft was rejected for this version", "OA-009": "stored approval records failed their integrity check",
    "OA-010": "integrity key missing or weak", "OA-011": "tenant mismatch", "OA-012": "the quote is not usable",
    "OA-013": "the draft is on hold", "OA-014": "confirmations incomplete", "OA-015": "the build gate refused",
}


class OwnerApprovalError(Exception):
    def __init__(self, code: str, detail: str = ""):
        self.code = code if code in CODES else "OA-001"
        self.detail = detail  # an enumerated reason or a gate code, never content
        super().__init__(f"{self.code}: {CODES[self.code]}")
