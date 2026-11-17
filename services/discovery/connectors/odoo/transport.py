"""The only I/O seam: an injected Transport, wrapped by a read-only gateway (PI-006).

No network code lives in this package. The platform vault supplies a ready Transport; the
connector never sees, stores or prints credentials."""
from __future__ import annotations

import re
from typing import Any, Mapping, Protocol, runtime_checkable

from .errors import (ModelUnavailable, Odo001MethodNotAllowed, Odo002WriteRefused, Odo003ModelNotAllowed,
                     Odo004BadCall, Odo005SecretLike, Odo008TransportFailure, Odo009MalformedResponse)

READ_METHODS = frozenset({"search_read", "read", "search_count", "fields_get", "name_get", "version"})
VERSION_MODEL = "common"  # the metadata call is `common.version`
ALLOWED_KWARGS = frozenset({"fields", "limit", "offset", "order", "context", "attributes", "allfields"})
MAX_PAGE_SIZE = 500  # hard ceiling on any page, whatever the configuration says
WRITE_NAMES = frozenset({"write", "create", "unlink", "copy", "execute", "execute_kw", "execute_workflow",
                         "call_kw", "call", "exec", "import_data", "load", "message_post", "toggle_active",
                         "onchange", "default_get", "set", "authenticate", "login", "check_access_rights"})
WRITE_PREFIXES = ("_", "action_", "button_", "write", "create", "unlink", "set_", "do_", "post", "cancel",
                  "confirm", "unreconcile", "reconcile", "execute", "exec", "import", "copy")
SECRET_KEY = re.compile(r"(pass(word|wd)?|secret|token|api[_\-]?key|credential|authoriz|private[_\-]?key|cookie"
                        r"|session[_\-]?id)", re.I)


@runtime_checkable
class Transport(Protocol):
    def call(self, model: str, method: str, args: list, kwargs: dict) -> Any: ...


def secret_like(key: Any) -> bool:
    return isinstance(key, str) and bool(SECRET_KEY.search(key))


def scan_secrets(v: Any, where: str, depth: int = 0) -> None:
    """Refuse any secret-like key in connector input (values are never echoed)."""
    if depth > 8:
        raise Odo004BadCall(f"{where} nested too deep")
    if isinstance(v, dict):
        for k, x in v.items():
            if secret_like(k):
                raise Odo005SecretLike(f"secret-like key in {where}")
            scan_secrets(x, where, depth + 1)
    elif isinstance(v, (list, tuple)):
        for x in v:
            scan_secrets(x, where, depth + 1)


def _jsonlike(v: Any, depth: int = 0) -> None:
    if depth > 8:
        raise Odo009MalformedResponse("response nested too deep")
    if v is None or isinstance(v, (str, bool, int, float)):
        return
    if isinstance(v, (list, tuple)):
        for x in v:
            _jsonlike(x, depth + 1)
    elif isinstance(v, dict):
        for k, x in v.items():
            if not isinstance(k, str):
                raise Odo009MalformedResponse("non-string key in response")
            _jsonlike(x, depth + 1)
    else:
        raise Odo009MalformedResponse(f"non-JSON value of type {type(v).__name__} in response")


class ReadOnlyGateway:
    """Every call passes here. Refuses non-read methods, models off the allow-list and secrets."""

    def __init__(self, transport: Transport, allowed_models: frozenset):
        if not callable(getattr(transport, "call", None)):
            raise Odo004BadCall("transport has no call()")
        self._t = transport
        self.allowed_models = frozenset(allowed_models)
        self.calls = 0

    def __repr__(self) -> str:  # never reveal the transport
        return "ReadOnlyGateway(models=%d)" % len(self.allowed_models)

    def call(self, model: Any, method: Any, args: Any = None, kwargs: Any = None) -> Any:
        args = [] if args is None else args
        kwargs = {} if kwargs is None else kwargs
        if not isinstance(method, str) or not method:
            raise Odo001MethodNotAllowed("method must be a string")
        if method not in READ_METHODS:
            low = method.lower()
            if low in WRITE_NAMES or low.startswith(WRITE_PREFIXES):
                raise Odo002WriteRefused("write-style method refused (read-only connector)")
            raise Odo001MethodNotAllowed("method is not on the read allow-list")
        if method == "version":
            if model != VERSION_MODEL:
                raise Odo003ModelNotAllowed("version is only served by the common service")
        elif not isinstance(model, str) or model not in self.allowed_models:
            raise Odo003ModelNotAllowed("model is not on the allow-list")
        if not isinstance(args, list) or not isinstance(kwargs, dict):
            raise Odo004BadCall("args must be a list and kwargs an object")
        bad = sorted(str(k) for k in kwargs if k not in ALLOWED_KWARGS)
        if bad:
            raise Odo004BadCall(f"keyword not allowed: {', '.join(bad)}")
        scan_secrets(args, "call args")
        scan_secrets(kwargs, "call kwargs")
        if method == "search_read":
            lim = kwargs.get("limit")
            if isinstance(lim, bool) or not isinstance(lim, int) or not 1 <= lim <= MAX_PAGE_SIZE:
                raise Odo004BadCall(f"search_read needs an integer limit 1..{MAX_PAGE_SIZE}")
        if method in ("read", "name_get"):
            ids = args[0] if args else None
            if not isinstance(ids, list) or len(ids) > MAX_PAGE_SIZE or not all(
                    isinstance(i, int) and not isinstance(i, bool) for i in ids):
                raise Odo004BadCall("read needs a list of integer ids within the page ceiling")
        self.calls += 1
        try:
            out = self._t.call(model, method, args, kwargs)
        except ModelUnavailable:
            raise
        except Exception:
            raise Odo008TransportFailure("transport call failed") from None
        _jsonlike(out)
        return out
