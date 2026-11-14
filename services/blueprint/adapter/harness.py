"""AdapterHarness (contracts/engine-adapter.md section 15.1): the only door the conformance suite uses.

The real adapter (apps/engine, BPL-012) provides its own subclass and points `ADAPTER_HARNESS=module:factory` at it.
Methods marked "optional" may raise NotImplementedError; the tests that need them are then skipped, and the skip is
reported, not hidden.
"""
from __future__ import annotations

import abc
import importlib
import os
from typing import Any, Callable

from .fake import FakeAdapter, HooksDisabled


class AdapterHarness(abc.ABC):
    # --- section 15.1
    @abc.abstractmethod
    def call(self, operation: str, context: dict, input: dict) -> dict: ...  # noqa: A002

    @abc.abstractmethod
    def fault(self, stage: str, step_seq: int | None = None, post_condition_id: str | None = None,
              during_compensation: bool = False) -> None:
        """Arm one fault, consumed by the next matching call. stage: prepare, execute, reconcile, finalize, deadline.
        during_compensation=True also makes the compensation that follows this fault fail."""

    @abc.abstractmethod
    def data_probe(self, pointer: str, value: Any = None, tenant_id: str | None = None) -> Any:
        """Write `value` (when not None) to the stored data of the field at pointer; return what is stored."""

    @abc.abstractmethod
    def auth_probe(self, member_ref: str, tenant_id: str | None = None) -> dict:
        """{"exists", "canAuthenticate", "emailSent"} for a shadow user."""

    @abc.abstractmethod
    def action_probe(self, member_ref: str, tenant_id: str | None = None) -> dict:
        """{"allowed"}: whether the shadow user can act on the tenant's behalf."""

    @abc.abstractmethod
    def events(self) -> list[dict]: ...

    @abc.abstractmethod
    def reset(self) -> None: ...

    # --- extensions needed by specific ADP-C items (documented in README.md; optional)
    def on_lock_held(self, callback: Callable[[], None]) -> None:
        """Run callback once while the next apply or rollback holds the site lock (ADP-C-042)."""
        raise NotImplementedError

    def advance_time(self, seconds: int) -> None:
        """Move the adapter clock forward (plan token expiry, ADP-C-034)."""
        raise NotImplementedError

    def set_site_state(self, tenant_id: str, state: str) -> None:
        """Put an existing site in provisioning or failed (ADP-C-017)."""
        raise NotImplementedError

    def audit_log(self) -> list[dict]:
        """Audit records with at least auditId (ADP-C-070)."""
        raise NotImplementedError

    def dropped_data(self) -> list[str]:
        """Pointers whose stored data an operation removed. Must stay empty (ADP-C-050)."""
        raise NotImplementedError

    def without_test_hooks(self) -> "AdapterHarness":
        """A fresh instance built like production, with no fault hooks (ADP-C-069)."""
        raise NotImplementedError


class FakeHarness(AdapterHarness):
    def __init__(self, adapter: FakeAdapter | None = None, default_tenant: str = "t_alpha"):
        self.adapter = adapter or FakeAdapter()
        self.default_tenant = default_tenant

    def call(self, operation, context, input):  # noqa: A002
        return self.adapter.call(operation, context, input)

    def fault(self, stage, step_seq=None, post_condition_id=None, during_compensation=False):
        self.adapter.fault(stage, step_seq, post_condition_id, during_compensation)

    def data_probe(self, pointer, value=None, tenant_id=None):
        return self.adapter.data_probe(tenant_id or self.default_tenant, pointer, value)

    def auth_probe(self, member_ref, tenant_id=None):
        return self.adapter.auth_probe(tenant_id or self.default_tenant, member_ref)

    def action_probe(self, member_ref, tenant_id=None):
        return self.adapter.action_probe(tenant_id or self.default_tenant, member_ref)

    def events(self):
        return self.adapter.events()

    def reset(self):
        self.adapter.reset()

    def on_lock_held(self, callback):
        self.adapter.on_lock_held(callback)

    def advance_time(self, seconds):
        self.adapter.advance_time(seconds)

    def set_site_state(self, tenant_id, state):
        self.adapter.set_site_state(tenant_id, state)

    def audit_log(self):
        return self.adapter.audit_log()

    def dropped_data(self):
        return list(self.adapter.dropped_data)

    def without_test_hooks(self):
        return FakeHarness(FakeAdapter(test_hooks=False), self.default_tenant)


def make_harness() -> AdapterHarness:
    """The fake, or the adapter named by ADAPTER_HARNESS=module:factory (a zero-argument callable)."""
    spec = os.environ.get("ADAPTER_HARNESS")
    if not spec:
        return FakeHarness()
    module, _, name = spec.partition(":")
    return getattr(importlib.import_module(module), name)()


__all__ = ["AdapterHarness", "FakeHarness", "HooksDisabled", "make_harness"]
