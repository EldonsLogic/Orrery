"""Semantic layer (OPR-006): governed metrics computed by deterministic code from the Event stream.

The chat asks for a metric by id; it never computes one. No model calls, no engine calls.
Design: docs/product/semantic-layer.md. Fails closed: any doubt is a coded `MET-` refusal.
"""
from .errors import MetricError
from .registry import MetricDef, default_registry
from .service import MetricService, Principal

__all__ = ["MetricError", "MetricDef", "MetricService", "Principal", "default_registry"]
