"""Stable reason codes and statuses for the component request pipeline (BPL-016). Never renumber; add at the end."""
# statuses
REQUESTED, DRAFTED, IN_REVIEW, APPROVED, REJECTED, REFUSED = "requested", "drafted", "in_review", "approved", "rejected", "refused"
STATUSES = (REQUESTED, DRAFTED, IN_REVIEW, APPROVED, REJECTED, REFUSED)
TERMINAL = {APPROVED, REJECTED, REFUSED}
TRANSITIONS = {REQUESTED: {DRAFTED, REFUSED}, DRAFTED: {IN_REVIEW}, IN_REVIEW: {APPROVED, REJECTED}}

# reasons (each has ar and en labels in labels.json under "reason.<code>")
FORBIDDEN_SCOPE = "CRQ-001"       # ledger, tax, e-invoicing, payroll maths or audit: human-built path only
PER_CLIENT = "CRQ-002"            # a need for one client only: not generalisable
MALFORMED_INTAKE = "CRQ-003"      # the gap analysis request is not the expected shape
MALFORMED_DRAFT = "CRQ-004"       # the drafted output failed the closed-shape or manifest checks
HOSTILE_DRAFT = "CRQ-005"         # control or bidi characters, injection phrases, personal data or a secret in a draft
DRAFT_RISK = "CRQ-006"            # draft asks for a ledger, tax, stock or permission effect, or a verb agents may not own
IN_LIBRARY = "CRQ-007"            # the library already provides it
DUPLICATE = "CRQ-008"             # same stable key: the existing request is returned
NOT_GENERALISABLE = "CRQ-009"     # draft has no generalisation rationale or says tenant specific
BAD_TRANSITION = "CRQ-010"        # status machine violation
NOT_HUMAN = "CRQ-011"             # approval or rejection by something that is not a verified human reviewer
SELF_APPROVAL = "CRQ-012"         # the requester may not approve
DRAFT_TAMPERED = "CRQ-013"        # stored draft no longer matches its digest or no longer validates
BAD_CLOCK = "CRQ-014"             # timestamp is not a UTC ISO-8601 string
NOT_FOUND = "CRQ-015"
DRAFTER_FAILED = "CRQ-016"        # the drafting port raised or returned nothing
UNTRUSTED_TEXT = "CRQ-017"        # warning only: untrusted text was flagged and replaced by a slug


class RequestError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message
