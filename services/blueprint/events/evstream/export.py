"""Tenant export and chain verification."""
from __future__ import annotations

import json
from typing import Iterable

from .errors import EventError, Issue
from .store import EventStore, find_gaps

PAGE = 500


def export_tenant_jsonl(store: EventStore, tenant_id: str) -> str:
    """All events of one tenant, ascending by sequence, one canonical JSON object per line.

    Deterministic: sorted keys, compact separators, UTF-8 text, trailing newline per line.
    Refuses to emit an event of any other tenant."""
    lines: list[str] = []
    after = 0
    while True:
        page = store.read(tenant_id, after, PAGE)
        if not page:
            break
        for ev in page:
            if ev.get("tenant_id") != tenant_id:
                raise EventError("EVS-TENANT-003", "store returned an event of another tenant")
            lines.append(json.dumps(ev, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        after = page[-1]["sequence"]
    return "".join(line + "\n" for line in lines)


def verify_chain(events: Iterable[dict], start: int = 1) -> list[Issue]:
    """Check one tenant's events in the order given: one tenant, strictly +1 from `start`.

    Detects missing sequences (EVS-SEQ-002), repeats and reordering (EVS-SEQ-003) and mixed
    tenants (EVS-TENANT-003). No hashes: tamper-evidence by hash chain is an extension, off here."""
    issues: list[Issue] = []
    tenant, expect = None, start
    for i, ev in enumerate(events):
        if not isinstance(ev, dict) or isinstance(ev.get("sequence"), bool) or not isinstance(ev.get("sequence"), int):
            issues.append(Issue("EVS-SEQ-003", f"[{i}]", "event without integer sequence"))
            continue
        if tenant is None:
            tenant = ev.get("tenant_id")
        elif ev.get("tenant_id") != tenant:
            issues.append(Issue("EVS-TENANT-003", f"[{i}]", "event of another tenant"))
            continue
        seq = ev["sequence"]
        if seq > expect:
            issues.append(Issue("EVS-SEQ-002", f"[{i}]", f"missing {expect}..{seq - 1}"))
        elif seq < expect:
            issues.append(Issue("EVS-SEQ-003", f"[{i}]", f"sequence {seq} repeated or out of order (expected {expect})"))
            continue
        expect = seq + 1
    return issues


__all__ = ["export_tenant_jsonl", "verify_chain", "find_gaps"]
