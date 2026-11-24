"""Intent router (OPR-002): decides discover, ask, act or change for each user message. Design:
docs/architecture/intent-router.md. No model calls and no network here; the classifier is an injected port."""
from .metrics import RouterMetrics
from .models import MODES, PRIVILEGED, Pending, RouteContext, RouteDecision
from .ports import ClassifierRequest, ModelClassifierPort, RouterPort
from .router import IntentRouter

__all__ = ["IntentRouter", "RouterMetrics", "RouterPort", "ModelClassifierPort", "ClassifierRequest", "RouteContext",
           "RouteDecision", "Pending", "MODES", "PRIVILEGED"]
