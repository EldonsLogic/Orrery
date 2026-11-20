"""Feature-flag errors. Codes only, no secrets, no caller input in messages."""

MESSAGES = {
    "FLG-001": "invalid flag definition",
    "FLG-002": "unknown flag",
    "FLG-003": "invalid input",
    "FLG-010": "caller is not a verified staff human",
    "FLG-011": "fresh MFA step-up required",
    "FLG-012": "second staff approver required",
    "FLG-013": "staff role for restricted flags missing or not configured",
    "FLG-014": "this change needs a proposal and a second staff approver",
    "FLG-015": "proposal missing, expired, used or not for this approver",
    "FLG-020": "evaluation context is not from verified claims",
    "FLG-030": "clock is invalid or went backwards",
    "FLG-040": "concurrent change, retry",
    "FLG-050": "store error",
}


class FlagError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(f"{code}: {MESSAGES.get(code, 'flag error')}")
