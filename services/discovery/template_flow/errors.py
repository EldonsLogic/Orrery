"""Coded refusals of the template-first flow (DSC-004). Messages never echo owner text."""
from __future__ import annotations


class FlowError(ValueError):
    """An edit or a call is refused. Nothing was applied. `code` is stable; `detail` is safe to show."""

    def __init__(self, code: str, detail: str, pointer: str | None = None):
        self.code = code
        self.detail = detail
        self.pointer = pointer
        super().__init__(f"{code}: {detail}")


# Stable codes (documented in README.md)
EDIT_SHAPE = "TFL-EDIT-001"      # edit is not a well-formed object, unknown key, bad id
EDIT_NOOP = "TFL-EDIT-002"       # value equals the current value
BATCH_LIMIT = "TFL-BATCH-001"    # too many edits in one call, or duplicate id in the call
HISTORY_LIMIT = "TFL-BATCH-002"  # history would exceed its cap
PATH_UNSAFE = "TFL-PATH-001"     # malformed or hostile pointer
PATH_NOT_EDITABLE = "TFL-PATH-002"
PATH_MISSING = "TFL-PATH-003"    # not present in this draft, or ambiguous
VALUE_TYPE = "TFL-VALUE-001"
VALUE_RANGE = "TFL-VALUE-002"    # enum, pattern, min, max, length
VALUE_SIZE = "TFL-VALUE-003"
VALUE_CHARS = "TFL-VALUE-004"    # control, bidi, zero-width, tag characters
SCHEMA = "TFL-SCHEMA-001"        # edit would add a Blueprint schema error
SEMANTIC = "TFL-SEM-001"         # edit would add an error found by the injected validator
REPLAY = "TFL-REPLAY-001"        # edit id already used
STALE = "TFL-STALE-001"          # edit was composed against another draft
STATE = "TFL-STATE-001"          # draft is not in build state draft
HISTORY_CHAIN = "TFL-HIST-001"   # history hash chain broken
