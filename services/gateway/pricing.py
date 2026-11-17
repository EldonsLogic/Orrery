"""Deterministic integer micro-USD token pricing for the AI gateway (PLT-025).

Default tier rates reflect UNVERIFIED strategy assumptions from
docs/strategy/06-model-strategy.md and must be replaced with verified vendor
rate cards before customer billing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

MICRO_USD_PER_USD = 1_000_000
TOKENS_PER_MTOK = 1_000_000

VALID_TIERS = frozenset({"frontier", "mid", "small", "code"})


def require_non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer, got {value!r}")
    return value


@dataclass(frozen=True)
class ModelRate:
    """Per-1M-token pricing expressed in integer micro-USD (1 USD = 1,000,000)."""

    tier: str
    input_micro_usd_per_mtok: int
    output_micro_usd_per_mtok: int
    cached_input_micro_usd_per_mtok: int = 0
    model_id: str | None = None
    verified: bool = False
    rate_source: str = "UNVERIFIED (docs/strategy/06-model-strategy.md)"

    def __post_init__(self) -> None:
        if not isinstance(self.tier, str) or not self.tier or len(self.tier) > 256:
            raise ValueError("tier must be a non-empty string up to 256 chars")
        if self.model_id is not None and (
            not isinstance(self.model_id, str) or not self.model_id or len(self.model_id) > 256
        ):
            raise ValueError("model_id must be a non-empty string up to 256 chars")
        require_non_negative_int("input_micro_usd_per_mtok", self.input_micro_usd_per_mtok)
        require_non_negative_int("output_micro_usd_per_mtok", self.output_micro_usd_per_mtok)
        require_non_negative_int("cached_input_micro_usd_per_mtok", self.cached_input_micro_usd_per_mtok)


# Default tier assumptions from docs/strategy/06-model-strategy.md:
# frontier: $5 in / $25 out per Mtok; mid: $3 / $15; small: $0.80 / $4;
# cached input assumed at 10% of uncached input (all UNVERIFIED).
DEFAULT_ASSUMED_RATES: dict[str, ModelRate] = {
    "frontier": ModelRate(
        tier="frontier",
        input_micro_usd_per_mtok=5_000_000,
        output_micro_usd_per_mtok=25_000_000,
        cached_input_micro_usd_per_mtok=500_000,
        verified=False,
        rate_source="UNVERIFIED assumption (docs/strategy/06-model-strategy.md)",
    ),
    "mid": ModelRate(
        tier="mid",
        input_micro_usd_per_mtok=3_000_000,
        output_micro_usd_per_mtok=15_000_000,
        cached_input_micro_usd_per_mtok=300_000,
        verified=False,
        rate_source="UNVERIFIED assumption (docs/strategy/06-model-strategy.md)",
    ),
    "small": ModelRate(
        tier="small",
        input_micro_usd_per_mtok=800_000,
        output_micro_usd_per_mtok=4_000_000,
        cached_input_micro_usd_per_mtok=80_000,
        verified=False,
        rate_source="UNVERIFIED assumption (docs/strategy/06-model-strategy.md)",
    ),
    "code": ModelRate(
        tier="code",
        input_micro_usd_per_mtok=0,
        output_micro_usd_per_mtok=0,
        cached_input_micro_usd_per_mtok=0,
        verified=True,
        rate_source="Deterministic code path (no model inference)",
    ),
}


@dataclass(frozen=True)
class CostBreakdown:
    """Exact integer token cost calculation for one call."""

    uncached_input_tokens: int
    cached_tokens: int
    output_tokens: int
    total_tokens: int
    cost_micro_usd: int
    pico_usd: int
    rate: ModelRate


def compute_call_cost(
    rate: ModelRate,
    *,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
) -> CostBreakdown:
    """Compute deterministic call cost in integer micro-USD (half-away-from-zero).

    `input_tokens` is total prompt tokens; `cached_tokens` is the cached subset of
    `input_tokens` (so `cached_tokens <= input_tokens`).
    """
    inp = require_non_negative_int("input_tokens", input_tokens)
    out = require_non_negative_int("output_tokens", output_tokens)
    cached = require_non_negative_int("cached_tokens", cached_tokens)
    if cached > inp:
        raise ValueError(f"cached_tokens ({cached}) cannot exceed input_tokens ({inp})")

    uncached_input = inp - cached
    pico_usd = (
        uncached_input * rate.input_micro_usd_per_mtok
        + cached * rate.cached_input_micro_usd_per_mtok
        + out * rate.output_micro_usd_per_mtok
    )
    # 1 Mtok = 1_000_000 tokens -> exact division from pico-USD (1e-12 USD) to micro-USD (1e-6 USD)
    cost_micro_usd = (pico_usd + (TOKENS_PER_MTOK // 2)) // TOKENS_PER_MTOK
    return CostBreakdown(
        uncached_input_tokens=uncached_input,
        cached_tokens=cached,
        output_tokens=out,
        total_tokens=inp + out,
        cost_micro_usd=cost_micro_usd,
        pico_usd=pico_usd,
        rate=rate,
    )


class PriceBook:
    """Lookup table mapping `(model_id, tier)` -> `ModelRate` cleanly and fail-closed."""

    def __init__(
        self,
        *,
        tier_rates: Mapping[str, ModelRate] | None = None,
        model_rates: Mapping[str, ModelRate] | None = None,
    ) -> None:
        self._tier_rates = dict(DEFAULT_ASSUMED_RATES if tier_rates is None else tier_rates)
        self._model_rates = dict(model_rates or {})

    def register_model_rate(self, model_id: str, rate: ModelRate) -> None:
        if not isinstance(model_id, str) or not model_id or len(model_id) > 256:
            raise ValueError("model_id must be a non-empty string up to 256 chars")
        self._model_rates[model_id] = rate

    def resolve(self, model_id: str, tier: str) -> ModelRate:
        if not isinstance(model_id, str) or not model_id or len(model_id) > 256:
            raise ValueError("model_id must be a non-empty string up to 256 chars")
        if model_id in self._model_rates:
            rate = self._model_rates[model_id]
            if rate.tier != tier:
                raise ValueError(
                    f"model_id {model_id!r} belongs to tier {rate.tier!r}, cannot bill under tier {tier!r}"
                )
            return rate
        if tier in self._tier_rates:
            return self._tier_rates[tier]
        raise KeyError(f"Unknown model rate for model_id={model_id!r}, tier={tier!r}")
