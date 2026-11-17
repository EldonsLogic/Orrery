"""Coded refusals of the Odoo connector. The runner reports an extract fault as CON-010 plus the
exception class name, so each code has its own class whose name carries the code. Messages never
carry transport text, request values or credentials."""


class OdooRefusal(Exception):
    code = "ODO-000"

    def __init__(self, reason: str = ""):
        super().__init__(f"{self.code}: {reason}" if reason else self.code)
        self.reason = reason


class Odo001MethodNotAllowed(OdooRefusal):
    """Method is not on the read allow-list (PI-006)."""
    code = "ODO-001"


class Odo002WriteRefused(OdooRefusal):
    """Write, unlink, create, execute or action style call (PI-006)."""
    code = "ODO-002"


class Odo003ModelNotAllowed(OdooRefusal):
    code = "ODO-003"


class Odo004BadCall(OdooRefusal):
    """Malformed arguments, unknown keyword, missing or oversize page limit."""
    code = "ODO-004"


class Odo005SecretLike(OdooRefusal):
    """A secret-like key in connector input; credentials come only from the vault transport."""
    code = "ODO-005"


class Odo006BadRequest(OdooRefusal):
    code = "ODO-006"


class Odo007BadConfig(OdooRefusal):
    code = "ODO-007"


class Odo008TransportFailure(OdooRefusal):
    """The transport raised; its message is dropped (it may carry connection details)."""
    code = "ODO-008"


class Odo009MalformedResponse(OdooRefusal):
    code = "ODO-009"


class ModelUnavailable(Exception):
    """Raised by a transport when a model is not installed or not visible; reported, not fatal."""
