"""Reuse metrics and Platform Autonomy Rate (BPL-022). Definitions: docs/strategy/autonomy-metrics.md.

From services/blueprint:  python3 -m metrics autonomy DRAFT.json APPLIED.json [--tenant T] [--revision N]
From the repo root:       PYTHONPATH=services/blueprint python3 -m metrics autonomy DRAFT.json APPLIED.json
Pure functions, no I/O, refusals are `MetricsError` with a `MET-` code.
"""
from .autonomy import AutonomyResult, autonomy_rate
from .elements import ELEMENT_KINDS, ElementKind
from .errors import CODES, MetricsError
from .reuse import NewComponentsResult, ReuseResult, new_components_per_build, reuse_ratio

__all__ = ["autonomy_rate", "AutonomyResult", "reuse_ratio", "ReuseResult", "new_components_per_build",
           "NewComponentsResult", "ELEMENT_KINDS", "ElementKind", "MetricsError", "CODES"]
