"""Agent stream endpoint (OPR-020, ADR-0044): AG-UI events over HTTP POST plus Server-Sent Events.

Transport only, never authority. Stdlib core; FastAPI is imported lazily by `create_app`.
Needs `services/operate` and `services/blueprint/events` (evstream) on the import path.
"""
from .app import create_app
from .core import Dependencies, handle_request
from .events import ALLOWED_CUSTOM_NAMES, ALLOWED_EVENT_TYPES
from .ports import Approval, Principal, RuntimeContext, RuntimeUsage

__all__ = ["create_app", "Dependencies", "handle_request", "ALLOWED_CUSTOM_NAMES", "ALLOWED_EVENT_TYPES",
           "Approval", "Principal", "RuntimeContext", "RuntimeUsage"]
