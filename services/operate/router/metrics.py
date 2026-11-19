"""Per-intent metrics hook, compatible with evals/harness/intent_routing.py (QA-020 scorer).

The router decides a mode, not an intent. A separate resolver (rules, a model, a test oracle) may name an intent and
the mode that intent belongs to; `record` keeps that intent only when the router agrees and did not abstain, so a
disagreement scores as an abstain, never as a wrong action. Predictions use the scorer's ndjson format."""
from __future__ import annotations

import json
from collections import Counter

from .models import RouteDecision


class RouterMetrics:
    def __init__(self):
        self._rows: list = []
        self.by_mode: Counter = Counter()
        self.by_reason: Counter = Counter()
        self.by_intent: dict = {}

    def record(self, case_id: str, decision: RouteDecision, intent=None, intent_mode=None, latency_ms=None) -> dict:
        keep = intent is not None and not decision.abstain and (intent_mode is None or intent_mode == decision.mode)
        row = {"id": case_id, "intent": intent if keep else None,
               "risk_class": decision.risk_hint if keep else None, "cost_usd": 0.0}
        if latency_ms is not None:
            row["latency_ms"] = round(latency_ms, 4)
        self._rows.append(row)
        self.by_mode[decision.mode] += 1
        self.by_reason.update(decision.reasons)
        if intent is not None:
            self.by_intent.setdefault(intent, Counter())["kept" if keep else "abstained"] += 1
        return row

    def predictions(self) -> list:
        return list(self._rows)

    def to_ndjson(self) -> str:
        return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in self._rows)
