"""Typed identity errors. Messages are fixed per code and never carry secrets,
tokens, keys or personal data; callers may show the code, not the cause."""

MESSAGES = {
    "IDN-001": "token is malformed",
    "IDN-002": "token algorithm or header not allowed",
    "IDN-003": "token signature invalid",
    "IDN-004": "token expired",
    "IDN-005": "token not yet valid",
    "IDN-006": "token issuer, audience or realm not accepted here",
    "IDN-007": "token tenant does not match this tenant",
    "IDN-008": "token claims not as expected",
    "IDN-009": "membership not active or session revoked",
    "IDN-010": "person or staff identity unknown or disabled",
    "IDN-011": "tenant not active",
    "IDN-012": "roles could not be resolved",
    "IDN-013": "multi-factor authentication required",
    "IDN-014": "multi-factor enrolment required for this role",
    "IDN-015": "only the tenant owner may change this setting",
    "IDN-020": "refresh token invalid",
    "IDN-021": "refresh token reused; session family revoked",
    "IDN-030": "caller lacks invite permission",
    "IDN-031": "invite unknown or already used",
    "IDN-032": "invite expired",
    "IDN-033": "invite channel not verified for this person",
    "IDN-034": "invite request invalid",
    "IDN-040": "approver is not an owner or admin of this tenant",
    "IDN-041": "support grant cannot be self-approved",
    "IDN-042": "support grant not active",
    "IDN-043": "support grant request invalid",
    "IDN-044": "support grant does not cover this scope",
    "IDN-045": "too many pending support grant requests",
    "IDN-060": "verification failed",
    "IDN-061": "too many attempts; try again later",
    "IDN-062": "factor enrolment or removal not allowed",
    "IDN-063": "factor unknown",
    "IDN-064": "multi-factor service unavailable",
    "IDN-050": "unknown realm",
    "IDN-051": "identity configuration invalid",
}


class IdentityError(Exception):
    """Every identity failure. `code` is stable; the message is generic."""

    def __init__(self, code: str):
        if code not in MESSAGES:
            code = "IDN-051"
        self.code = code
        super().__init__(f"{code}: {MESSAGES[code]}")
