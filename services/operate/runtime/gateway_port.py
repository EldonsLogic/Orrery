"""ModelPort over the metered gateway router (PLT-025). The router does the tier routing, the budget precheck
(tenant and session caps) and the metering; live provider transports are PLT-009 and are not here.

The router's transport must return a `ModelReply` as `ProviderResponse.output`. Anything else fails the run closed."""
from __future__ import annotations

from .models import ModelReply, ModelRequest, Usage
from .ports import BudgetStop


class GatewayModelPort:
    def __init__(self, router, ctx, *, tier: str = "mid", agent_id: str | None = None,
                 prompt_version: str = "unversioned", est_input_tokens: int = 2000, est_output_tokens: int = 1000):
        from gateway import ModelCallRequest  # lazy: the host puts services/ on the path
        self._router, self._ctx, self._req = router, ctx, ModelCallRequest
        self._tier, self._agent, self.prompt_version = tier, agent_id, prompt_version
        self._est = (est_input_tokens, est_output_tokens)
        self.model_id = f"tier:{tier}"

    def complete(self, request: ModelRequest) -> ModelReply:
        from gateway import BudgetExceededError
        call = self._req(tier=self._tier, purpose="agent", payload=request, agent_id=self._agent,
                         prompt_version=self.prompt_version, estimated_input_tokens=self._est[0],
                         estimated_output_tokens=self._est[1])
        try:
            res = self._router.execute(self._ctx, call)
        except BudgetExceededError as e:
            raise BudgetStop(str(e.limit_kind)[:64] or "cost")
        out = res.output
        if not isinstance(out, ModelReply):
            raise TypeError("gateway transport did not return a ModelReply")
        m = res.metering
        usage = Usage(m.input_tokens, m.output_tokens, m.cached_tokens, m.cost_micro_usd, res.model_id, res.tier,
                      metered=True)
        return ModelReply(out.text, out.tool_calls, usage)
