"""Metered tier-routing gateway wrapper (PLT-025).

Routes requests by logical tier (`frontier`, `mid`, `small`, `code`) without
exposing provider/model selection to tenants, enforces pre-flight budgets,
measures latency, and records per-call and per-tenant token usage.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable

from .metering import CallUsage, GatewayContext, GatewayMeter, MeteredCallRecord
from .pricing import compute_call_cost, require_non_negative_int


@dataclass(frozen=True)
class ModelRoute:
    """Internal mapping from platform tier to a configured provider/model target."""

    tier: str
    model_id: str
    provider: str = "unconfigured"


@dataclass(frozen=True)
class ModelCallRequest:
    """Internal gateway call envelope routed by tier and purpose."""

    tier: str
    purpose: str
    payload: Any
    agent_id: str | None = None
    prompt_version: str | None = None
    tool: str | None = None
    audit_id: str | None = None
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0

    def __post_init__(self) -> None:
        require_non_negative_int("estimated_input_tokens", self.estimated_input_tokens)
        require_non_negative_int("estimated_output_tokens", self.estimated_output_tokens)


@dataclass(frozen=True)
class ProviderResponse:
    """Normalized provider response returned by a pluggable transport callable."""

    output: Any
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    model_id: str | None = None


@dataclass(frozen=True)
class ModelCallResult:
    """Gateway response paired with its immutable metering record."""

    output: Any
    tier: str
    model_id: str
    metering: MeteredCallRecord


class MeteredGatewayRouter:
    """Thin metered gateway dispatcher enforcing tier routing and budgets."""

    def __init__(
        self,
        *,
        meter: GatewayMeter,
        routes: dict[str, ModelRoute],
        transport: Callable[[ModelRoute, ModelCallRequest, GatewayContext], ProviderResponse],
    ) -> None:
        self._meter = meter
        self._routes = dict(routes)
        self._transport = transport

    def route_for(self, tier: str) -> ModelRoute:
        if tier not in self._routes:
            raise KeyError(f"No route configured for tier {tier!r}")
        return self._routes[tier]

    def execute(
        self,
        ctx: GatewayContext,
        request: ModelCallRequest,
        *,
        call_id: str | None = None,
    ) -> ModelCallResult:
        route = self.route_for(request.tier)
        rate = self._meter.price_book.resolve(route.model_id, route.tier)
        est_cost = compute_call_cost(
            rate,
            input_tokens=request.estimated_input_tokens,
            output_tokens=request.estimated_output_tokens,
            cached_tokens=0,
        )
        est_tokens = request.estimated_input_tokens + request.estimated_output_tokens
        self._meter.precheck_budget(
            ctx,
            estimated_cost_micro_usd=est_cost.cost_micro_usd,
            estimated_tokens=est_tokens,
            tier=route.tier,
        )

        t0 = time.monotonic()
        resp = self._transport(route, request, ctx)
        latency_ms = max(0, int(round((time.monotonic() - t0) * 1000)))

        actual_model = resp.model_id or route.model_id
        usage = CallUsage(
            model_id=actual_model,
            tier=route.tier,
            purpose=request.purpose,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cached_tokens=resp.cached_tokens,
            agent_id=request.agent_id,
            prompt_version=request.prompt_version,
            tool=request.tool,
            audit_id=request.audit_id,
            latency_ms=latency_ms,
        )
        # Pre-flight admission already passed; always commit actual post-transport
        # token spend so the tenant ledger cannot drift below real provider usage.
        record = self._meter.record_call(ctx, usage, call_id=call_id, enforce_budget=False)
        return ModelCallResult(
            output=resp.output,
            tier=route.tier,
            model_id=actual_model,
            metering=record,
        )
