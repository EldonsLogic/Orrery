"""Conformance harness entrypoint for ChangeEngineAdapter (BPL-012 / contracts/engine-adapter.md section 15.1)."""
from __future__ import annotations

from typing import Any, Callable

from change_engine.adapter.engine import ChangeEngineAdapter, HooksDisabled

try:
    from adapter.harness import AdapterHarness as _BaseHarness
except ImportError:  # pragma: no cover - standalone apps/engine runtime without services/blueprint on sys.path
    class _BaseHarness:  # type: ignore[no-redef]
        pass


class ChangeEngineHarness(_BaseHarness):
    """AdapterHarness subclass exposing ChangeEngineAdapter for ADAPTER_HARNESS=change_engine.adapter.harness:make_harness."""

    def __init__(
        self,
        adapter: ChangeEngineAdapter | None = None,
        default_tenant: str = "t_alpha",
        db_path: str = ":memory:",
    ) -> None:
        self.db_path = db_path
        self.adapter = adapter or ChangeEngineAdapter(test_hooks=True, db_path=db_path)
        self.default_tenant = default_tenant

    def call(self, operation: str, context: dict[str, Any], input: dict[str, Any]) -> dict[str, Any]:  # noqa: A002
        return self.adapter.call(operation, context, input)

    def fault(
        self,
        stage: str,
        step_seq: int | None = None,
        post_condition_id: str | None = None,
        during_compensation: bool = False,
    ) -> None:
        self.adapter.fault(stage, step_seq, post_condition_id, during_compensation)

    def data_probe(self, pointer: str, value: Any = None, tenant_id: str | None = None) -> Any:
        return self.adapter.data_probe(tenant_id or self.default_tenant, pointer, value)

    def auth_probe(self, member_ref: str, tenant_id: str | None = None) -> dict[str, Any]:
        return self.adapter.auth_probe(tenant_id or self.default_tenant, member_ref)

    def action_probe(self, member_ref: str, tenant_id: str | None = None) -> dict[str, Any]:
        return self.adapter.action_probe(tenant_id or self.default_tenant, member_ref)

    def events(self) -> list[dict[str, Any]]:
        return self.adapter.events()

    def reset(self) -> None:
        self.adapter.reset()

    def on_lock_held(self, callback: Callable[[], None]) -> None:
        self.adapter.on_lock_held(callback)

    def advance_time(self, seconds: int) -> None:
        self.adapter.advance_time(seconds)

    def set_site_state(self, tenant_id: str, state: str) -> None:
        self.adapter.set_site_state(tenant_id, state)

    def audit_log(self) -> list[dict[str, Any]]:
        return self.adapter.audit_log()

    def dropped_data(self) -> list[str]:
        return self.adapter.dropped_data()

    def plan_evidence(self, evidence_ref: str, tenant_id: str | None = None) -> list[str]:
        return self.adapter.plan_evidence(tenant_id or self.default_tenant, evidence_ref)

    def execution_journal(self) -> list[dict[str, Any]]:
        return self.adapter.execution_journal()

    def without_test_hooks(self) -> "ChangeEngineHarness":
        return ChangeEngineHarness(
            ChangeEngineAdapter(test_hooks=False, db_path=self.db_path),
            default_tenant=self.default_tenant,
            db_path=self.db_path,
        )


def make_harness() -> ChangeEngineHarness:
    """Factory referenced by ADAPTER_HARNESS=change_engine.adapter.harness:make_harness."""
    return ChangeEngineHarness()


__all__ = ["ChangeEngineHarness", "HooksDisabled", "make_harness"]
