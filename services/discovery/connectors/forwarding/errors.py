"""Coded refusals of the forwarding intake connectors. The runner reports an extract fault as CON-010
plus the exception class name, so each code has its own class whose name carries the code.
Reasons never contain addresses, names or filenames (PII minimised in logs)."""


class ForwardRefusal(Exception):
    code = "FWD-000"

    def __init__(self, reason: str = ""):
        super().__init__(f"{self.code}: {reason}" if reason else self.code)
        self.reason = reason


class Fwd001NotAMessage(ForwardRefusal):
    """No parseable RFC822 header block, or an empty chat export."""
    code = "FWD-001"


class Fwd002ExecutableAttachment(ForwardRefusal):
    """Strict mode: an executable, script, macro or shortcut attachment refuses the whole message."""
    code = "FWD-002"


class Fwd003TooManyParts(ForwardRefusal):
    code = "FWD-003"


class Fwd004Undecodable(ForwardRefusal):
    code = "FWD-004"
