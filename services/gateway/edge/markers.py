"""Engine-identifying markers (ADR-0016). Internal code may name the engine; responses never may."""
from __future__ import annotations

import re

# Bytes-level, case-insensitive. `desk` is matched as a whole word so "desktop" is not a false positive.
ENGINE_MARKER_RE = re.compile(
    rb"frappe|erpnext|\bdesk\b|/api/method|/api/resource|/assets/|socket\.io|"
    rb"x-page-name|csrf_token|_server_messages|exc_type|traceback \(most recent call",
    re.IGNORECASE,
)


def contains_engine_marker(data: bytes | str) -> bool:
    if isinstance(data, str):
        data = data.encode("utf-8", "surrogatepass")
    return ENGINE_MARKER_RE.search(data) is not None
