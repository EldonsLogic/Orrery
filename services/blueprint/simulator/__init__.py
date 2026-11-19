"""Simulator (BPL-018): replay a month of the owner's data on the compiled tenant through the Tool API.

Design: docs/architecture/simulator.md. Entry point: `simulate(...)` in report.py.
"""
from .codes import CODES, Anomaly
from .plan import SimulatorError, plan_replay
from .report import simulate, validate_report
from .runner import EnginePort, ToolCall, run_plan
from .simulated_port import SimulatedPort

__all__ = ["CODES", "Anomaly", "EnginePort", "SimulatedPort", "SimulatorError", "ToolCall", "plan_replay",
           "run_plan", "simulate", "validate_report"]
