"""evstream: reference implementation of contract 4 (event stream). See ../README.md."""
from .build import Context, build_event
from .errors import CODES, EventError, Issue
from .export import export_tenant_jsonl, verify_chain
from .redact import DEFAULT_POLICY, RedactionPolicy, redact_for_model
from .registry import Registry, TypeInfo, default_registry
from .store import EventStore, MemoryStore, find_gaps
from .ulid import UlidGenerator, is_valid_ulid, new_ulid
from .validate import ValidationResult, validate_event

__all__ = [
    "Context", "build_event", "CODES", "EventError", "Issue", "export_tenant_jsonl", "verify_chain",
    "DEFAULT_POLICY", "RedactionPolicy", "redact_for_model", "Registry", "TypeInfo", "default_registry",
    "EventStore", "MemoryStore", "find_gaps", "UlidGenerator", "is_valid_ulid", "new_ulid",
    "ValidationResult", "validate_event",
]
