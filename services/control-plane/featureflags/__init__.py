"""Feature flags (PLT-016). Boolean rollout switches, fail closed, audited.
Flags gate the rollout of code paths only: they never grant a permission, role
or agent authority and never change tax, ledger, payroll or e-invoice behaviour."""

from .admin import FlagAdmin
from .context import EvalContext
from .errors import FlagError
from .evaluator import Decision, FlagEvaluator, bucket
from .labels import label, missing
from .model import AuditRecord, FlagDef, FlagState, KillState, Registry
from .store import InMemoryFlagStore

__all__ = ["AuditRecord", "Decision", "EvalContext", "FlagAdmin", "FlagDef", "FlagError",
           "FlagEvaluator", "FlagState", "InMemoryFlagStore", "KillState", "Registry",
           "bucket", "label", "missing"]
