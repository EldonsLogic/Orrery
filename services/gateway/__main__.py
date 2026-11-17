"""CLI utility to summarize gateway token & micro-USD cost from synthetic JSONL call logs."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .metering import CallUsage, GatewayContext, GatewayMeter


def summarize_jsonl(lines: list[str], *, tenant_id: str | None = None, session_id: str | None = None) -> dict:
    meter = GatewayMeter()
    tenants: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        item = json.loads(line)
        ctx = GatewayContext(
            tenant_id=item["tenant_id"],
            actor_kind=item.get("actor_kind", "agent"),
            actor_id=item.get("actor_id", "builder"),
            correlation_id=item.get("correlation_id", item.get("session_id", "session")),
            session_id=item.get("session_id"),
        )
        usage = CallUsage(
            model_id=item["model_id"],
            tier=item["tier"],
            purpose=item["purpose"],
            input_tokens=item["input_tokens"],
            output_tokens=item["output_tokens"],
            cached_tokens=item.get("cached_tokens", 0),
            agent_id=item.get("agent_id"),
            prompt_version=item.get("prompt_version"),
            tool=item.get("tool"),
            audit_id=item.get("audit_id"),
            latency_ms=item.get("latency_ms"),
        )
        meter.record_call(ctx, usage, enforce_budget=False)
        if ctx.tenant_id not in tenants:
            tenants.append(ctx.tenant_id)

    if tenant_id is not None and session_id is not None:
        return asdict(meter.session_summary(tenant_id, session_id))
    if tenant_id is not None:
        return asdict(meter.tenant_summary(tenant_id))
    return {
        "tenants": {tid: asdict(meter.tenant_summary(tid)) for tid in tenants}
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize gateway token and micro-USD cost logs.")
    parser.add_argument("jsonl_file", help="Path to JSONL call usage log, or '-' for stdin")
    parser.add_argument("--tenant", default=None, help="Filter summary to a single tenant_id")
    parser.add_argument("--session", default=None, help="Filter summary to a single session_id (requires --tenant)")
    args = parser.parse_args(argv)

    if args.session and not args.tenant:
        print("--session requires --tenant", file=sys.stderr)
        return 2

    lines = (
        sys.stdin.read().splitlines()
        if args.jsonl_file == "-"
        else Path(args.jsonl_file).read_text(encoding="utf-8").splitlines()
    )
    report = summarize_jsonl(lines, tenant_id=args.tenant, session_id=args.session)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
