"""Error firewall (ADR-0044 item 6, ADR-0036): every failure becomes a catalog or generic error before RunError.

Customer text comes only from the bilingual catalog or an i18n key. Raw exception text, class names,
tracebacks and paths never leave; the caller logs them internally against a correlation id."""
from __future__ import annotations

import logging
import uuid

from toolapi.errors import build_error, internal_error, load_catalog, render_message

log = logging.getLogger("agui")
_CATALOG = None


class DomainFailure(Exception):
    """A failure already expressed as a catalog code plus params (ADR-0036)."""

    def __init__(self, code: str, params: dict | None = None):
        super().__init__(code)
        self.code, self.params = code, params or {}


class AuthFailure(Exception):
    """Authentication or tenant failure; `status` is 401 or 403. Carries no detail by design."""

    def __init__(self, status: int = 401):
        super().__init__("auth")
        self.status = status


class InputRejected(Exception):
    """The request body is invalid or too large; `status` is 400 or 413."""

    def __init__(self, status: int = 400):
        super().__init__("input")
        self.status = status


def catalog() -> dict:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = load_catalog()
    return _CATALOG


def to_error(exc: BaseException, locale: str = "en", correlation_id: str | None = None) -> dict:
    """Return {"code", "message", "message_key", "correlation_id"?} safe for the wire."""
    cid = correlation_id or uuid.uuid4().hex
    if isinstance(exc, AuthFailure):
        return {"code": "permission_denied", "message": "errors.permission_denied",
                "message_key": "errors.permission_denied"}
    if isinstance(exc, InputRejected):
        return {"code": "invalid_arguments", "message": "errors.invalid_arguments",
                "message_key": "errors.invalid_arguments"}
    if isinstance(exc, DomainFailure):
        err = build_error(exc.code, exc.params, catalog(), cid)
        domain = err.get("domain")
        if domain:
            text = render_message(err, locale, catalog())
            if text:
                return {"code": domain["code"], "message": text, "message_key": err["message_key"]}
    log.error("agui internal failure correlation_id=%s type=%s", cid, type(exc).__name__, exc_info=exc)
    err = internal_error(cid)
    return {"code": "internal_error", "message": err["message_key"], "message_key": err["message_key"],
            "correlation_id": cid}
