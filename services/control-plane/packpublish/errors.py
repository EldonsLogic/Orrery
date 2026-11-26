"""Pack publishing errors. Codes are stable, messages are fixed and carry no content or caller input."""

CODES = {
    "PP-001": "input is not valid",
    "PP-002": "pack content is not valid",
    "PP-003": "edit is not allowed",
    "PP-010": "signer is not on the roster for this role",
    "PP-011": "the two sign-offs are the same person",
    "PP-012": "exactly one market accountant and one founder sign-off are required",
    "PP-013": "sign-off authentication is missing, stale or not bound",
    "PP-014": "signer signature is missing or does not verify",
    "PP-015": "sign-off does not cover this draft",
    "PP-020": "draft was altered since it was made",
    "PP-021": "version or base does not follow the published chain",
    "PP-022": "change kind and follow-up review do not match",
    "PP-030": "audit write failed, nothing was published",
    "PP-031": "store error, nothing was published",
    "PP-040": "request id was already used for a different request",
    "PP-050": "rollback target is not allowed",
    "PP-051": "rollback approval is missing, not a founder or stale",
}


class PublishError(Exception):
    def __init__(self, code: str):
        self.code = code if code in CODES else "PP-001"
        super().__init__(f"{self.code}: {CODES[self.code]}")
