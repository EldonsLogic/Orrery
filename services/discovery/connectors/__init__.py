"""Connector runtime boundary (DSC-010). Offline, deterministic, stdlib only.

Not a connector: the framework every connector runs behind. See
contracts/connector-interface.md and docs/security/prompt-injection-defence.md.
"""
from .model import (Budget, BudgetExceeded, ConnectorRefusal, Limits, Registry, RunContext,
                    check_connector, ALLOWED_CAPABILITIES, TIERS)
from .runner import RecordingSink, iter_envelopes, run_connector

__all__ = ["Budget", "BudgetExceeded", "ConnectorRefusal", "Limits", "Registry", "RunContext",
           "check_connector", "run_connector", "iter_envelopes", "RecordingSink", "ALLOWED_CAPABILITIES", "TIERS"]
