"""ModelPort over the metered gateway router (PLT-025). The router does the tier routing, the budget precheck
(tenant and session caps) and the metering; live provider transports are PLT-009 and are not here.

A port is bound to one verified caller's `GatewayContext`, so it is built per request: `gateway_model_for(router)`
returns the `model_for(principal, run_id)` factory the AG-UI adapter takes (H2). The precheck estimate grows with the
real request size, so the gateway projects the next call's cost from the route's price before it dispatches (M6).
The router's transport must return a `ModelReply` as `ProviderResponse.output`. Anything else fails the run closed."""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass

from .models import ModelReply, ModelRequest, Usage
from .ports import BudgetStop

CHARS_PER_TOKEN = 3  # conservative for mixed Arabic and English text


def estimate_input_tokens(request: ModelRequest, floor: int = 0) -> int:
    try:
        body = asdict(request) if is_dataclass(request) else request
        n = len(json.dumps(body, ensure_ascii=False, default=str))
    except Exception:
        n = 0
    return max(int(floor), -(-n // CHARS_PER_TOKEN))


class GatewayModelPort:
    def __init__(self, router, ctx, *, tier: str = "mid", agent_id: str | None = None,
                 prompt_version: str = "unversioned", est_input_tokens: int = 2000, est_output_tokens: int = 1000):
        from gateway import ModelCallRequest  # lazy: the host puts services/ on the path
        self._router, self._ctx, self._req = router, ctx, ModelCallRequest
        self._tier, self._agent, self.prompt_version = tier, agent_id, prompt_version
        self._est = (est_input_tokens, est_output_tokens)
        self.model_id = f"tier:{tier}"

    @property
    def tenant_id(self) -> str:
        return self._ctx.tenant_id

    def complete(self, request: ModelRequest) -> ModelReply:
        from gateway import BudgetExceededError
        call = self._req(tier=self._tier, purpose="agent", payload=request, agent_id=self._agent,
                         prompt_version=self.prompt_version,
                         estimated_input_tokens=estimate_input_tokens(request, self._est[0]),
                         estimated_output_tokens=self._est[1])
        try:
            res = self._router.execute(self._ctx, call)
        except BudgetExceededError as e:
            kind = getattr(e, "limit_kind", None)
            raise BudgetStop(str(kind)[:64] if kind else "cost")
        out = res.output
        if not isinstance(out, ModelReply):
            raise TypeError("gateway transport did not return a ModelReply")
        m = res.metering
        usage = Usage(m.input_tokens, m.output_tokens, m.cached_tokens, m.cost_micro_usd, res.model_id, res.tier,
                      metered=True)
        return ModelReply(out.text, out.tool_calls, usage)


def gateway_context(principal, run_id: str):
    """GatewayContext from the verified principal for one run; the correlation id is the run id."""
    from gateway import GatewayContext
    return GatewayContext(tenant_id=principal.tenant_id, actor_kind="user", actor_id=principal.subject,
                          correlation_id=run_id, role_ids=tuple(principal.role_ids),
                          session_id=principal.session_id or None)


def gateway_model_for(router, **port_kw):
    """Factory for `AguiRuntimeAdapter(model_for=...)`: a fresh port bound to this principal and run."""
    def model_for(principal, run_id: str) -> GatewayModelPort:
        return GatewayModelPort(router, gateway_context(principal, run_id), **port_kw)
    return model_for
