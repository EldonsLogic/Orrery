"""Feature flags (PLT-016). Boolean rollout switches, fail closed, audited.
A flag decides whether a code path is reached. The permission check, the human
floor and the deterministic tax, ledger and payroll code still run behind it: a
flag never grants a permission or role and never alters tax, ledger, payroll or
e-invoice maths. Restricted flags gate paths that touch agent authority, money or
compliance, so enabling one is a two-person change."""

from .admin import FlagAdmin
from .context import EvalContext
from .errors import FlagError
from .evaluator import Decision, FlagEvaluator, bucket
from .labels import label, missing
from .model import (AuditRecord, FlagDef, FlagState, KillState, Proposal, Registry,
                    TenantAuditView)
from .store import AuditSealer, InMemoryAnchor, InMemoryFlagStore

__all__ = ["AuditRecord", "AuditSealer", "InMemoryAnchor", "Proposal", "TenantAuditView", "Decision", "EvalContext", "FlagAdmin", "FlagDef", "FlagError",
           "FlagEvaluator", "FlagState", "InMemoryFlagStore", "KillState", "Registry",
           "bucket", "label", "missing"]
