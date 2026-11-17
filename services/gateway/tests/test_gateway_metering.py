"""Tests for AI gateway per-tenant and per-call token/cost metering (PLT-025)."""
from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

GATEWAY_PARENT = Path(__file__).resolve().parents[2]
if str(GATEWAY_PARENT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_PARENT))

EVENTS_PARENT = GATEWAY_PARENT / "blueprint" / "events"
if EVENTS_PARENT.is_dir() and str(EVENTS_PARENT) not in sys.path:
    sys.path.insert(0, str(EVENTS_PARENT))

from gateway import (  # noqa: E402
    BudgetExceededError,
    BudgetPolicy,
    CallUsage,
    DEFAULT_ASSUMED_RATES,
    GatewayContext,
    GatewayMeter,
    MeteredGatewayRouter,
    ModelCallRequest,
    ModelRate,
    ModelRoute,
    PriceBook,
    ProviderResponse,
    TenantContextError,
    UlidGenerator,
    compute_call_cost,
    is_valid_ulid,
)
from gateway.__main__ import main as cli_main, summarize_jsonl  # noqa: E402

try:
    import evstream  # noqa: E402

    HAS_EVSTREAM = True
except ImportError:  # pragma: no cover - optional unless jsonschema installed
    evstream = None
    HAS_EVSTREAM = False


def _ctx(
    tenant_id: str = "t_alpha",
    *,
    actor_kind: str = "agent",
    actor_id: str = "builder_agent",
    correlation_id: str = "corr_build_01",
    session_id: str | None = "build_session_01",
) -> GatewayContext:
    return GatewayContext(
        tenant_id=tenant_id,
        actor_kind=actor_kind,
        actor_id=actor_id,
        correlation_id=correlation_id,
        session_id=session_id,
        role_ids=("builder",),
    )


class PricingTests(unittest.TestCase):
    def test_exact_integer_micro_usd_math_and_cached_discount(self) -> None:
        rate = DEFAULT_ASSUMED_RATES["frontier"]  # $5 in / $25 out / $0.50 cached per Mtok
        # 1M total input (200k cached -> 800k uncached), 100k output:
        # 0.8 * $5 ($4.00) + 0.2 * $0.50 ($0.10) + 0.1 * $25 ($2.50) = $6.60 = 6_600_000 micro_usd
        cost = compute_call_cost(
            rate,
            input_tokens=1_000_000,
            cached_tokens=200_000,
            output_tokens=100_000,
        )
        self.assertEqual(cost.uncached_input_tokens, 800_000)
        self.assertEqual(cost.cached_tokens, 200_000)
        self.assertEqual(cost.output_tokens, 100_000)
        self.assertEqual(cost.total_tokens, 1_100_000)
        self.assertEqual(cost.cost_micro_usd, 6_600_000)

    def test_half_away_from_zero_micro_usd_rounding(self) -> None:
        # $0.80 / Mtok input -> 0.8 micro_usd per token -> 1 token = 800_000 pico_usd -> rounds to 1 micro_usd
        small = DEFAULT_ASSUMED_RATES["small"]
        c1 = compute_call_cost(small, input_tokens=1, output_tokens=0, cached_tokens=0)
        self.assertEqual(c1.cost_micro_usd, 1)

        # $0.08 / Mtok cached -> 80_000 pico_usd per cached token -> 6 tokens = 480_000 (< 500_000 -> 0),
        # 7 tokens = 560_000 (>= 500_000 -> 1)
        c6 = compute_call_cost(small, input_tokens=6, cached_tokens=6, output_tokens=0)
        c7 = compute_call_cost(small, input_tokens=7, cached_tokens=7, output_tokens=0)
        self.assertEqual(c6.cost_micro_usd, 0)
        self.assertEqual(c7.cost_micro_usd, 1)

    def test_rejects_invalid_token_counts_and_tier_mismatch(self) -> None:
        rate = DEFAULT_ASSUMED_RATES["mid"]
        with self.assertRaises(ValueError):
            compute_call_cost(rate, input_tokens=-1, output_tokens=0)
        with self.assertRaises(ValueError):
            compute_call_cost(rate, input_tokens=True, output_tokens=0)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            compute_call_cost(rate, input_tokens=10, output_tokens=0, cached_tokens=11)
        with self.assertRaises(ValueError):
            compute_call_cost(rate, input_tokens=1.5, output_tokens=0)  # type: ignore[arg-type]

        pb = PriceBook()
        pb.register_model_rate(
            "m_custom_frontier",
            ModelRate(tier="frontier", input_micro_usd_per_mtok=1, output_micro_usd_per_mtok=2, model_id="m_custom_frontier"),
        )
        with self.assertRaises(ValueError):
            pb.resolve("m_custom_frontier", "small")
        with self.assertRaises(KeyError):
            pb.resolve("unknown_model", "nonexistent_tier")


class ContextAndUlidTests(unittest.TestCase):
    def test_monotonic_ulid_matches_contract_pattern(self) -> None:
        gen = UlidGenerator(time_ms=lambda: 1_760_000_000_123)
        ids = [gen.generate() for _ in range(10)]
        for eid in ids:
            self.assertTrue(is_valid_ulid(eid), f"Invalid ULID: {eid}")
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(set(ids)), 10)

    def test_rejects_invalid_or_spoofed_tenant_context(self) -> None:
        with self.assertRaises(TenantContextError):
            GatewayContext(tenant_id="platform", actor_kind="system", actor_id="sys", correlation_id="c1")
        with self.assertRaises(TenantContextError):
            GatewayContext(tenant_id="bad-hyphen", actor_kind="user", actor_id="u1", correlation_id="c1")
        with self.assertRaises(TenantContextError):
            GatewayContext(tenant_id="t_ok", actor_kind="root", actor_id="u1", correlation_id="c1")
        with self.assertRaises(TenantContextError):
            CallUsage(
                model_id="m1",
                tier="small",
                purpose="chat",
                input_tokens=10,
                output_tokens=5,
                metadata={"tenant_id": "t_other"},
            )


class MeteringAndIsolationTests(unittest.TestCase):
    def test_per_call_per_tenant_and_builder_session_isolation(self) -> None:
        meter = GatewayMeter(
            clock=lambda: datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc),
        )
        ctx_a1 = _ctx("t_alpha", session_id="build_alpha_1", correlation_id="corr_1")
        ctx_a2 = _ctx("t_alpha", session_id="chat_alpha_1", actor_kind="user", actor_id="u_1", correlation_id="corr_2")
        ctx_b = _ctx("t_beta", session_id="build_beta_1", correlation_id="corr_3")

        r1 = meter.record_call(
            ctx_a1,
            CallUsage(
                model_id="gpt-frontier-synth",
                tier="frontier",
                purpose="build",
                input_tokens=200_000,
                cached_tokens=50_000,
                output_tokens=40_000,
                agent_id="discovery_builder",
                prompt_version="v3",
            ),
        )
        # frontier: 150k * $5/M + 50k * $0.50/M + 40k * $25/M
        # = 750_000 + 25_000 + 1_000_000 = 1_775_000 micro_usd
        self.assertEqual(r1.cost_micro_usd, 1_775_000)

        r2 = meter.record_call(
            ctx_a1,
            CallUsage(
                model_id="haiku-small-synth",
                tier="small",
                purpose="build",
                input_tokens=500_000,
                cached_tokens=0,
                output_tokens=100_000,
                agent_id="discovery_builder",
            ),
        )
        # small: 500k * $0.80/M + 100k * $4/M = 400_000 + 400_000 = 800_000 micro_usd
        self.assertEqual(r2.cost_micro_usd, 800_000)

        meter.record_call(
            ctx_a2,
            CallUsage(
                model_id="haiku-small-synth",
                tier="small",
                purpose="chat",
                input_tokens=100_000,
                output_tokens=25_000,
            ),
        )
        # small: 100k * $0.80/M + 25k * $4/M = 80_000 + 100_000 = 180_000 micro_usd

        meter.record_call(
            ctx_b,
            CallUsage(
                model_id="sonnet-mid-synth",
                tier="mid",
                purpose="build",
                input_tokens=100_000,
                output_tokens=10_000,
            ),
        )
        # mid: 100k * $3/M + 10k * $15/M = 300_000 + 150_000 = 450_000 micro_usd

        alpha_session = meter.session_summary("t_alpha", "build_alpha_1")
        self.assertEqual(alpha_session.totals.call_count, 2)
        self.assertEqual(alpha_session.totals.total_tokens, 840_000)
        self.assertEqual(alpha_session.totals.cost_micro_usd, 2_575_000)
        self.assertEqual(alpha_session.by_purpose["build"].cost_micro_usd, 2_575_000)
        self.assertEqual(alpha_session.by_tier["frontier"].cost_micro_usd, 1_775_000)
        self.assertEqual(alpha_session.by_tier["small"].cost_micro_usd, 800_000)

        alpha_total = meter.tenant_summary("t_alpha")
        self.assertEqual(alpha_total.totals.call_count, 3)
        self.assertEqual(alpha_total.totals.cost_micro_usd, 2_755_000)
        self.assertEqual(alpha_total.by_purpose["build"].cost_micro_usd, 2_575_000)
        self.assertEqual(alpha_total.by_purpose["chat"].cost_micro_usd, 180_000)

        beta_total = meter.tenant_summary("t_beta")
        self.assertEqual(beta_total.totals.call_count, 1)
        self.assertEqual(beta_total.totals.cost_micro_usd, 450_000)
        self.assertEqual(len(meter.calls_for_tenant("t_beta")), 1)
        self.assertEqual(len(meter.calls_for_tenant("t_alpha")), 3)
        self.assertEqual(len(meter.calls_for_session("t_alpha", "build_alpha_1")), 2)

        # Ensure tenant B never inherits or sees tenant A events
        for ev in meter.events_for_tenant("t_beta"):
            self.assertEqual(ev["tenant_id"], "t_beta")

    def test_budget_fail_closed_and_alert_thresholds(self) -> None:
        emitted: list[dict] = []
        meter = GatewayMeter(event_sink=emitted.append)
        meter.set_tenant_budget(
            "t_capped",
            BudgetPolicy(max_cost_micro_usd=1_000_000, max_total_tokens=200_000, alert_threshold_pct=80),
        )
        ctx = _ctx("t_capped", session_id="s_1")

        # 500_000 tokens? No: 100k input + 20k output on mid -> 300k + 300k = 600_000 micro_usd (60%, no alert yet)
        meter.record_call(
            ctx,
            CallUsage(model_id="m-mid", tier="mid", purpose="agent", input_tokens=100_000, output_tokens=20_000),
        )
        self.assertEqual(len(meter.tenant_summary("t_capped").alerts), 0)

        # + 50k input + 10k output on mid -> +300_000 = 900_000 micro_usd (90% >= 80% threshold -> alert!)
        meter.record_call(
            ctx,
            CallUsage(model_id="m-mid", tier="mid", purpose="agent", input_tokens=50_000, output_tokens=10_000),
        )
        alerts = meter.tenant_summary("t_capped").alerts
        self.assertEqual(len(alerts), 2)  # both cost (900k/1M) and tokens (180k/200k) crossed 80%!
        self.assertEqual({a.metric for a in alerts}, {"cost_micro_usd", "total_tokens"})

        # Next call exceeding 1_000_000 micro_usd fails closed and emits no event
        before_events = len(emitted)
        with self.assertRaises(BudgetExceededError) as err:
            meter.record_call(
                ctx,
                CallUsage(model_id="m-mid", tier="mid", purpose="agent", input_tokens=50_000, output_tokens=0),
            )
        self.assertEqual(err.exception.limit_kind, "cost_micro_usd")
        self.assertEqual(len(emitted), before_events)
        self.assertEqual(meter.tenant_summary("t_capped").totals.cost_micro_usd, 900_000)

        # Deterministic code path continues working even when model budget is nearly/fully spent
        meter.set_tenant_budget("t_exhausted", BudgetPolicy(max_cost_micro_usd=0))
        ctx_ex = _ctx("t_exhausted", session_id="s_det")
        with self.assertRaises(BudgetExceededError):
            meter.precheck_budget(ctx_ex, estimated_cost_micro_usd=1, estimated_tokens=10, tier="small")
        meter.precheck_budget(ctx_ex, estimated_cost_micro_usd=0, estimated_tokens=0, tier="code")
        code_rec = meter.record_call(
            ctx_ex,
            CallUsage(model_id="deterministic-vat-v1", tier="code", purpose="build", input_tokens=0, output_tokens=0),
        )
        self.assertEqual(code_rec.cost_micro_usd, 0)

    def test_router_precheck_blocks_transport_and_commits_actual_spend(self) -> None:
        meter = GatewayMeter()
        meter.set_tenant_budget("t_routed", BudgetPolicy(max_cost_micro_usd=500_000))
        transport_calls = 0

        def fake_transport(route: ModelRoute, req: ModelCallRequest, ctx: GatewayContext) -> ProviderResponse:
            nonlocal transport_calls
            transport_calls += 1
            # Return 100k input + 100k output on small -> 80k + 400k = 480k micro_usd
            return ProviderResponse(output={"ok": True}, input_tokens=100_000, output_tokens=100_000, cached_tokens=0)

        router = MeteredGatewayRouter(
            meter=meter,
            routes={
                "small": ModelRoute(tier="small", model_id="synth-small", provider="synthetic"),
                "frontier": ModelRoute(tier="frontier", model_id="synth-frontier", provider="synthetic"),
            },
            transport=fake_transport,
        )
        ctx = _ctx("t_routed", session_id="build_r1")

        # Precheck blocks oversized estimate BEFORE calling transport
        with self.assertRaises(BudgetExceededError):
            router.execute(
                ctx,
                ModelCallRequest(
                    tier="frontier",
                    purpose="build",
                    payload={"prompt": "compile"},
                    estimated_input_tokens=200_000,
                    estimated_output_tokens=50_000,
                ),
            )
        self.assertEqual(transport_calls, 0)

        # Admitted call runs transport and commits exact actual cost (480k <= 500k)
        res = router.execute(
            ctx,
            ModelCallRequest(
                tier="small",
                purpose="build",
                payload={"prompt": "classify"},
                agent_id="router_agent",
                prompt_version="p1",
                estimated_input_tokens=10_000,
                estimated_output_tokens=1_000,
            ),
        )
        self.assertEqual(transport_calls, 1)
        self.assertEqual(res.metering.cost_micro_usd, 480_000)

        # Next call that overshoots remaining 20k budget is committed (say 60k) -> ledger hits 540k
        # Wait: precheck passes since est=0 and 480k < 500k; then subsequent call MUST be rejected
        router.execute(
            ctx,
            ModelCallRequest(tier="small", purpose="build", payload={"prompt": "overflow"}),
        )
        self.assertEqual(meter.tenant_summary("t_routed").totals.cost_micro_usd, 960_000)
        with self.assertRaises(BudgetExceededError):
            router.execute(
                ctx,
                ModelCallRequest(tier="small", purpose="build", payload={"prompt": "blocked"}),
            )
        self.assertEqual(transport_calls, 2)


class CliAndContractConformanceTests(unittest.TestCase):
    def test_cli_summarizes_jsonl_builder_session(self) -> None:
        rows = [
            {
                "tenant_id": "t_cli",
                "session_id": "build_99",
                "model_id": "synth-frontier",
                "tier": "frontier",
                "purpose": "build",
                "input_tokens": 100_000,
                "output_tokens": 20_000,
                "cached_tokens": 10_000,
                "agent_id": "interview_agent",
            },
            {
                "tenant_id": "t_cli",
                "session_id": "build_99",
                "model_id": "synth-small",
                "tier": "small",
                "purpose": "build",
                "input_tokens": 50_000,
                "output_tokens": 10_000,
            },
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as tmp:
            for row in rows:
                tmp.write(json.dumps(row) + "\n")
            tmp_path = Path(tmp.name)
        try:
            stdout_buf = io.StringIO()
            with mock.patch("sys.stdout", stdout_buf):
                rc = cli_main([str(tmp_path), "--tenant", "t_cli", "--session", "build_99"])
            self.assertEqual(rc, 0)
            summary = json.loads(stdout_buf.getvalue())
            # Call 1: 90k*5 + 10k*0.5 + 20k*25 = 450_000 + 5_000 + 500_000 = 955_000
            # Call 2: 50k*0.8 + 10k*4 = 40_000 + 40_000 = 80_000
            # Total = 1_035_000 micro_usd
            self.assertEqual(summary["totals"]["cost_micro_usd"], 1_035_000)
            self.assertEqual(summary["totals"]["call_count"], 2)
        finally:
            tmp_path.unlink(missing_ok=True)

    @unittest.skipIf(
        not HAS_EVSTREAM and os.environ.get("REQUIRE_EVSTREAM_TESTS") != "1",
        "Requires jsonschema and services/blueprint/events on PYTHONPATH",
    )
    def test_emitted_meter_ai_usage_events_validate_and_append_to_evstream(self) -> None:
        self.assertTrue(HAS_EVSTREAM, "evstream/jsonschema required when REQUIRE_EVSTREAM_TESTS=1")
        store = evstream.MemoryStore()
        meter = GatewayMeter(event_sink=store.append)

        ctx_a = _ctx("t_ev_alpha", session_id="build_ev_1")
        ctx_b = _ctx("t_ev_beta", session_id="chat_ev_1", actor_kind="user", actor_id="u_99")

        meter.record_call(
            ctx_a,
            CallUsage(
                model_id="synth-frontier",
                tier="frontier",
                purpose="build",
                input_tokens=10_000,
                output_tokens=2_000,
                cached_tokens=2_000,
                agent_id="blueprint_compiler",
                prompt_version="v1",
                tool="blueprint.compile",
                audit_id="aud_001",
            ),
        )
        meter.record_call(
            ctx_a,
            CallUsage(
                model_id="synth-small",
                tier="small",
                purpose="build",
                input_tokens=5_000,
                output_tokens=1_000,
                cached_tokens=0,
                agent_id=None,
            ),
        )
        meter.record_call(
            ctx_b,
            CallUsage(
                model_id="synth-small",
                tier="small",
                purpose="chat",
                input_tokens=1_000,
                output_tokens=500,
            ),
        )

        # Verify raw unstamped events pass evstream validator before store stamping
        for ev in meter.events_for_tenant("t_ev_alpha"):
            res = evstream.validate_event(ev, stamped=False)
            self.assertTrue(res.ok, f"Validation failed: {res.as_dict()}")
            self.assertEqual(ev["type"], "meter.ai_usage")
            self.assertEqual(ev["source"]["service"], "gateway")
            self.assertEqual(ev["data_class"], "operational")

        stored_a = store.read("t_ev_alpha")
        self.assertEqual([e["sequence"] for e in stored_a], [1, 2])
        self.assertEqual(store.gaps("t_ev_alpha"), [])
        self.assertEqual(len(store.read("t_ev_beta")), 1)
        for ev in stored_a:
            res = evstream.validate_event(ev, stamped=True)
            self.assertTrue(res.ok, f"Stamped validation failed: {res.as_dict()}")


if __name__ == "__main__":
    unittest.main()
