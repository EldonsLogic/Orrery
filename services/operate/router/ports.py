"""Injected ports. Tests use scripted fakes; the real classifier is a gateway-routed small model (not built here)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from .models import CLASSIFIER_LABELS, ABSTAIN, RouteContext, RouteDecision


class RouterPort(Protocol):
    def route(self, turn: str, ctx: RouteContext, data: tuple = (), risk_hint: Optional[str] = None) -> RouteDecision:
        """Decide the mode of one user message. `turn` is the signed-in user's own words (L2); `data` is untrusted
        content (L3) that is never read. The result carries no authority: roles decide what the caller may do."""


@dataclass(frozen=True)
class ClassifierRequest:
    """What the classifier sees: the user's turn and a locale. No data items, no tool results, no Blueprint text."""
    turn: str
    locale: str
    labels: tuple = CLASSIFIER_LABELS


class ModelClassifierPort(Protocol):
    def classify(self, request: ClassifierRequest) -> object:
        """Return a label from `request.labels` (a str) or {"label": <label>, "confidence": 0..1}. Closed-set
        decoding: anything else is treated as invalid. Raise on provider failure; the router fails closed."""


def decode_label(raw) -> tuple:
    """Closed-set decode. Returns (label, confidence in [0,1]) or (None, 0.0). No raw text survives."""
    conf = 0.5
    if isinstance(raw, dict):
        label, c = raw.get("label"), raw.get("confidence", 0.5)
        if isinstance(c, bool) or not isinstance(c, (int, float)) or not 0.0 <= c <= 1.0:
            return None, 0.0
        conf = float(c)
    else:
        label = raw
    if not isinstance(label, str) or label not in CLASSIFIER_LABELS:  # exact match: no strip, no case folding
        return None, 0.0
    return label, conf


def bucket(conf: float) -> str:
    return "high" if conf >= 0.8 else "medium" if conf >= 0.5 else "low"


__all__ = ["RouterPort", "ModelClassifierPort", "ClassifierRequest", "decode_label", "bucket", "ABSTAIN"]
