"""Audit and metering through the Event stream (ADR-0044 item 4). The server writes these as they happen;
a wire event is never the source of an audit or billing fact. Failures here are logged, never sent."""
from __future__ import annotations

import logging
import uuid

from evstream import Context, build_event

from .ports import Principal, RuntimeUsage

log = logging.getLogger("agui")


class Auditor:
    def __init__(self, store, runtime=None):
        self.store, self.runtime = store, runtime

    def _ctx(self, p: Principal, run_id: str) -> Context:
        return Context(tenant_id=p.tenant_id, actor_kind="user", actor_id=p.subject, service="operate.agui",
                       role_ids=tuple(p.role_ids), correlation_id=run_id)

    def _trace(self) -> dict | None:
        mid = getattr(self.runtime, "model_id", None)
        return {"model_id": mid, "prompt_version": getattr(self.runtime, "prompt_version", None)} if mid else None

    def _write(self, ctx: Context, type: str, data: dict, trace=None) -> bool:
        try:
            self.store.append(build_event(ctx, type, data, trace=trace))
            return True
        except Exception:  # never let an audit fault leak to the caller; the run itself fails closed elsewhere
            log.exception("agui audit write failed type=%s", type)
            return False

    def run_event(self, p: Principal, run_id: str, kind: str, error_code: str | None = None) -> bool:
        data = {"run_id": run_id}
        if error_code:
            data["error_code"] = error_code
        return self._write(self._ctx(p, run_id), f"agent.run_{kind}", data, self._trace())

    def usage(self, p: Principal, run_id: str, u: RuntimeUsage) -> bool:
        data = {"model_id": u.model_id, "tier": u.tier, "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens, "cached_tokens": u.cached_tokens,
                "cost_micro_usd": u.cost_micro_usd, "purpose": "chat"}
        return self._write(self._ctx(p, run_id), "meter.ai_usage", data, {"model_id": u.model_id})

    def denied(self, tenant_id: str, reason_code: str) -> bool:
        ctx = Context(tenant_id=tenant_id, actor_kind="system", actor_id="agui", service="operate.agui",
                      correlation_id=uuid.uuid4().hex)
        return self._write(ctx, "permission.denied",
                           {"action": "agent.stream", "resource": "agui", "reason_code": reason_code})
