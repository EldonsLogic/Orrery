"""Deterministic static analysis for factory-built components (SEC-010). See README.md."""
from .analyse import analyse_component, declared_from
from .codes import Analysis, Issue

__all__ = ["analyse_component", "declared_from", "Analysis", "Issue"]
