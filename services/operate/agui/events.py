"""AG-UI wire events: constructors, the allow-list and SSE framing (ADR-0044 items 3, 7).

We emit the 1.0 wire shape (camelCase fields, SCREAMING_SNAKE type) ourselves, the fallback of ADR-0044
item 8; a conformance test checks it against the pinned `ag-ui-protocol` types when that is installed.
`sanitize` is the single gate every event passes before it is framed: unknown types, Raw and Reasoning
events, unknown Custom names, malformed shapes and anything naming the engine are dropped (fail closed)."""
from __future__ import annotations

import json
import re

ALLOWED_EVENT_TYPES = frozenset({
    "RUN_STARTED", "RUN_FINISHED", "RUN_ERROR",
    "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END",
    "STATE_SNAPSHOT", "STATE_DELTA",
    "TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END", "TOOL_CALL_RESULT",
    "CUSTOM",
})
# Never sent, even if a runtime produces them (ADR-0044 item 3).
NEVER_SENT = frozenset({"RAW", "REASONING_START", "REASONING_MESSAGE_START", "REASONING_MESSAGE_CONTENT",
                        "REASONING_MESSAGE_END", "REASONING_END", "REASONING_ENCRYPTED_VALUE",
                        "THINKING_START", "THINKING_END", "THINKING_TEXT_MESSAGE_START",
                        "THINKING_TEXT_MESSAGE_CONTENT", "THINKING_TEXT_MESSAGE_END"})
ALLOWED_CUSTOM_NAMES = frozenset({"approval.pending", "approval.status", "blueprint.summary", "tool.progress"})

MAX_FIELD_CHARS = 20_000
MAX_JSON_BYTES = 64 * 1024
_ID = re.compile(r"^[A-Za-z0-9_\-:.]{1,128}$")
_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,47}(\.[a-z][a-z0-9_]{0,47}){1,3}$")
_PATCH_OPS = frozenset({"add", "remove", "replace", "move", "copy", "test"})
# Engine names, class names, SQL and traces must never be on the wire (ADR-0016).
ENGINE_MARKERS = re.compile(r"frappe|erpnext|doctype|\btab[A-Z]|traceback|\bsql\b|\.py\b|site_config|/apps/",
                            re.IGNORECASE)


def _s(v, n=MAX_FIELD_CHARS) -> bool:
    return isinstance(v, str) and len(v) <= n


def _id(v) -> bool:
    return isinstance(v, str) and bool(_ID.match(v))


def _size_ok(v) -> bool:
    try:
        return len(json.dumps(v, ensure_ascii=False)) <= MAX_JSON_BYTES
    except (TypeError, ValueError):
        return False


def _valid(ev: dict) -> bool:
    t = ev["type"]
    if t == "RUN_STARTED" or t == "RUN_FINISHED":
        return _id(ev.get("threadId")) and _id(ev.get("runId")) and _size_ok(ev)
    if t == "RUN_ERROR":
        return _s(ev.get("message"), 1000) and (ev.get("code") is None or _s(ev.get("code"), 64))
    if t == "TEXT_MESSAGE_START":
        return _id(ev.get("messageId")) and ev.get("role", "assistant") == "assistant"
    if t == "TEXT_MESSAGE_CONTENT":
        return _id(ev.get("messageId")) and _s(ev.get("delta")) and ev.get("delta") != ""
    if t == "TEXT_MESSAGE_END":
        return _id(ev.get("messageId"))
    if t == "STATE_SNAPSHOT":
        return isinstance(ev.get("snapshot"), dict) and _size_ok(ev["snapshot"])
    if t == "STATE_DELTA":
        d = ev.get("delta")
        return (isinstance(d, list) and _size_ok(d)
                and all(isinstance(o, dict) and o.get("op") in _PATCH_OPS and _s(o.get("path"), 512) for o in d))
    if t == "TOOL_CALL_START":
        return _id(ev.get("toolCallId")) and isinstance(ev.get("toolCallName"), str) \
            and bool(_TOOL_NAME.match(ev["toolCallName"]))
    if t == "TOOL_CALL_ARGS":
        return _id(ev.get("toolCallId")) and _s(ev.get("delta"))
    if t == "TOOL_CALL_END":
        return _id(ev.get("toolCallId"))
    if t == "TOOL_CALL_RESULT":
        return _id(ev.get("toolCallId")) and _id(ev.get("messageId")) and _s(ev.get("content"))
    if t == "CUSTOM":
        return ev.get("name") in ALLOWED_CUSTOM_NAMES and isinstance(ev.get("value"), dict) and _size_ok(ev["value"])
    return False


def sanitize(ev) -> dict | None:
    """Return a clean copy of an allow-listed event, or None when it must be dropped."""
    if not isinstance(ev, dict) or ev.get("type") in NEVER_SENT or ev.get("type") not in ALLOWED_EVENT_TYPES:
        return None
    # Only the fields the spec defines for the type travel; rawEvent and unknown keys never do.
    try:
        if not _valid(ev):
            return None
        out = {k: v for k, v in ev.items() if k not in ("rawEvent", "timestamp")}
        if ENGINE_MARKERS.search(json.dumps(out, ensure_ascii=False)):
            return None
        return out
    except (TypeError, ValueError, RecursionError):
        return None


def sse_frame(ev: dict) -> bytes:
    """One SSE data frame (as the SDK encoder frames it). No comments, ids or custom headers."""
    return b"data: " + json.dumps(ev, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n\n"


# -- constructors (used by the core; runtimes may build their own dicts, which `sanitize` checks) ----
def run_started(thread_id, run_id) -> dict:
    return {"type": "RUN_STARTED", "threadId": thread_id, "runId": run_id}


def run_finished(thread_id, run_id, interrupts=()) -> dict:
    ev = {"type": "RUN_FINISHED", "threadId": thread_id, "runId": run_id}
    ev["outcome"] = ({"type": "interrupt", "interrupts": list(interrupts)} if interrupts
                     else {"type": "success"})
    return ev


def run_error(message: str, code: str) -> dict:
    return {"type": "RUN_ERROR", "message": message, "code": code}


def custom(name: str, value: dict) -> dict:
    return {"type": "CUSTOM", "name": name, "value": value}


def interrupt(approval_id: str, reason: str = "approval_required", message: str | None = None) -> dict:
    """Display-only: it names a pending approval the Tool API already created (ADR-0044 item 2)."""
    it = {"id": approval_id, "reason": reason, "metadata": {"approvalId": approval_id}}
    if message:
        it["message"] = message
    return it
