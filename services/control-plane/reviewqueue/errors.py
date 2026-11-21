"""Typed review-queue errors. Codes are stable, messages are fixed and carry no content (labels.json has the
bilingual text under `review.error.<code>`)."""

CODES = {
    "RQ-001": "input is not valid", "RQ-002": "time is out of range", "RQ-003": "reviewer not verified or not allowed",
    "RQ-004": "item not found", "RQ-005": "item state does not allow this", "RQ-006": "no live claim on this item",
    "RQ-007": "separation of duties", "RQ-008": "content changed since the decision", "RQ-009": "checklist incomplete or failed",
    "RQ-010": "item is on hold", "RQ-011": "stored record failed its integrity check", "RQ-012": "integrity key missing or weak",
    "RQ-013": "an open review already exists", "RQ-014": "note is not valid",
}


class ReviewError(Exception):
    def __init__(self, code: str, detail: str = ""):
        self.code = code if code in CODES else "RQ-001"
        self.detail = detail  # an enumerated reason or an identity code, never content
        super().__init__(f"{self.code}: {CODES[self.code]}")
