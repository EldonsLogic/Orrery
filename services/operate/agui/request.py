"""RunAgentInput validation (ADR-0044 item 5). Client input is data: ids and the last user text are
read; state, context, forwardedProps and tools are size-checked and then ignored; a resume keeps only
interrupt ids (never `status` or `payload`)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .errors import InputRejected

MAX_BODY_BYTES = 256 * 1024
MAX_STATE_BYTES = 16 * 1024
MAX_MESSAGES = 100
MAX_TEXT_CHARS = 20_000
MAX_RESUME = 20
_ID = re.compile(r"^[A-Za-z0-9_\-:.]{1,128}$")


@dataclass(frozen=True)
class RunRequest:
    thread_id: str
    run_id: str
    user_text: str
    resume_ids: tuple = ()


def _size(v) -> int:
    return len(json.dumps(v, ensure_ascii=False))


def parse_run_input(body: bytes) -> RunRequest:
    if not isinstance(body, (bytes, bytearray)) or len(body) > MAX_BODY_BYTES:
        raise InputRejected(413)
    try:
        data = json.loads(body.decode("utf-8"))
    except (ValueError, RecursionError):
        raise InputRejected(400)
    if not isinstance(data, dict):
        raise InputRejected(400)
    thread, run = data.get("threadId"), data.get("runId")
    if not (isinstance(thread, str) and _ID.match(thread) and isinstance(run, str) and _ID.match(run)):
        raise InputRejected(400)
    # Client-side tools are not offered (ADR-0044 item 1).
    if data.get("tools") not in (None, []):
        raise InputRejected(400)
    for key in ("state", "context", "forwardedProps"):
        if key in data and _size(data[key]) > MAX_STATE_BYTES:
            raise InputRejected(413)
    messages = data.get("messages", [])
    if not isinstance(messages, list) or len(messages) > MAX_MESSAGES:
        raise InputRejected(400)
    text = ""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            c = m.get("content")
            if not isinstance(c, str) or len(c) > MAX_TEXT_CHARS:
                raise InputRejected(400)
            text = c
            break
    resume = data.get("resume", [])
    if resume is None:
        resume = []
    if not isinstance(resume, list) or len(resume) > MAX_RESUME:
        raise InputRejected(400)
    ids = []
    for r in resume:
        if not isinstance(r, dict) or not isinstance(r.get("interruptId"), str) or not _ID.match(r["interruptId"]):
            raise InputRejected(400)
        ids.append(r["interruptId"])  # status and payload are deliberately not read
    return RunRequest(thread, run, text, tuple(ids))
