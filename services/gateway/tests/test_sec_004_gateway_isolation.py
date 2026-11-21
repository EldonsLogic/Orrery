"""SEC-004: Cross-tenant isolation tests for services/gateway (ADR-0006, ADR-0007)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

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
)


def _ctx(tenant_id: str, *, session_id: str = "shared_sess_id", corr: str = "corr_01") -> GatewayContext:
    return GatewayContext(
        tenant_id=tenant_id,
        actor_kind="user",
        actor_id=f"usr_{tenant_id}",
        correlation_id=corr,
        session_id=session_id,
        role_ids=("owner",),
    )


class TestGatewayCrossTenantIsolation(unittest.TestCase):
    """Prove gateway rejects spoofed/reserved tenant IDs and isolates budgets, ledgers, sessions, and events."""

    def test_rejects_spoofed_metadata_and_reserved_or_malformed_tenants(self) -> None:
        for bad_tenant in ("", "platform", "../t_beta", "t alpha", "t-beta", "t/beta", "a" * 65):
            with self.subTest(bad_tenant=bad_tenant):
                with self.assertRaises(TenantContextError):
                    GatewayContext(
                        tenant_id=bad_tenant,
                        actor_kind="user",
                        actor_id="u1",
                        correlation_id="c1",
                    )

        for spoof_key in ("tenant_id", "tenantId", "TENANT_ID", "tenant-id", "tenant", "tenantIds"):
            with self.subTest(spoof_key=spoof_key):
                with self.assertRaises(TenantContextError):
                    CallUsage(
                        model_id="m_small",
                        tier="small",
                        purpose="chat",
                        input_tokens=100,
                        output_tokens=50,
                        metadata={spoof_key: "t_victim"},
                    )

    def test_budget_exhaustion_on_one_tenant_does_not_affect_other_tenants(self) -> None:
        events: list[dict] = []
        pb = PriceBook()
        pb.register_model_rate(
            "m_mid",
            ModelRate(tier="mid", input_micro_usd_per_mtok=1_000_000, output_micro_usd_per_mtok=1_000_000, model_id="m_mid"),
        )
        meter = GatewayMeter(
            price_book=pb,
            event_sink=events.append,
            clock=lambda: datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc),
        )
        meter.set_tenant_budget("t_alpha", BudgetPolicy(max_total_tokens=100, max_cost_micro_usd=200))
        meter.set_tenant_budget("t_beta", BudgetPolicy(max_total_tokens=1000, max_cost_micro_usd=2000))

        router = MeteredGatewayRouter(
            meter=meter,
            routes={"mid": ModelRoute(tier="mid", model_id="m_mid", provider="stub")},
            transport=lambda route, req, ctx: ProviderResponse(
                output=f"ok:{ctx.tenant_id}",
                input_tokens=req.estimated_input_tokens,
                output_tokens=req.estimated_output_tokens,
                model_id=route.model_id,
            ),
        )

        # t_alpha uses 80 tokens; second call for 50 tokens exceeds t_alpha's 100-token cap.
        r_a1 = router.execute(
            _ctx("t_alpha", session_id="sess_common"),
            ModelCallRequest(tier="mid", purpose="build", payload={}, estimated_input_tokens=50, estimated_output_tokens=30),
        )
        self.assertEqual(r_a1.output, "ok:t_alpha")

        with self.assertRaises(BudgetExceededError) as exc_ctx:
            router.execute(
                _ctx("t_alpha", session_id="sess_common"),
                ModelCallRequest(tier="mid", purpose="build", payload={}, estimated_input_tokens=30, estimated_output_tokens=20),
            )
        self.assertEqual(exc_ctx.exception.tenant_id, "t_alpha")

        # t_beta with the exact same session_id and caller profile must succeed independently.
        r_b1 = router.execute(
            _ctx("t_beta", session_id="sess_common"),
            ModelCallRequest(tier="mid", purpose="build", payload={}, estimated_input_tokens=200, estimated_output_tokens=100),
        )
        self.assertEqual(r_b1.output, "ok:t_beta")

        # Verify tenant ledgers, session summaries, and emitted events remain strictly isolated.
        sum_a = meter.tenant_summary("t_alpha")
        sum_b = meter.tenant_summary("t_beta")
        self.assertEqual(sum_a.totals.total_tokens, 80)
        self.assertEqual(sum_a.totals.call_count, 1)
        self.assertEqual(sum_b.totals.total_tokens, 300)
        self.assertEqual(sum_b.totals.call_count, 1)

        sess_a = meter.session_summary("t_alpha", "sess_common")
        sess_b = meter.session_summary("t_beta", "sess_common")
        self.assertEqual(sess_a.totals.total_tokens, 80)
        self.assertEqual(sess_b.totals.total_tokens, 300)

        self.assertEqual([ev["tenant_id"] for ev in events], ["t_alpha", "t_beta"])


if __name__ == "__main__":
    unittest.main()
