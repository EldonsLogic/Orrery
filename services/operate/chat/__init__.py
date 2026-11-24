"""Chat service (OPR-010): sessions, streaming, Arabic and English. Design: docs/architecture/chat-service.md.
Needs `services/operate` (runtime, agui, toolapi), `services/` and `services/blueprint/events` on the path."""
from .errors import ChatFailure, render as render_error
from .history import build_window, default_frame
from .language import LangInfo, clean_text, detect, extract_numbers, normalise_digits, parse_decimal
from .models import (MODES, ChangePort, ChatLimits, Entry, MessageRecord, PendingBinding, RouteRequest, RouteResult,
                     RunSetup, Session, Window)
from .router import DefaultRouter, IntentRouterAdapter, RouterPort, safe_route
from .runner import HistoryModel, loop_runtime_factory
from .service import ChatService
from .store import ChatStore, MemoryChatStore, MemoryPendingStore, NoRetention, RetentionHook

__all__ = ["ChatFailure", "render_error", "build_window", "default_frame", "LangInfo", "clean_text", "detect",
           "extract_numbers", "normalise_digits", "parse_decimal", "MODES", "ChatLimits", "Entry", "MessageRecord",
           "RouteRequest", "RunSetup", "Session", "Window", "DefaultRouter", "RouterPort", "HistoryModel",
           "loop_runtime_factory", "ChatService", "ChatStore", "MemoryChatStore", "NoRetention", "RetentionHook", "ChangePort", "PendingBinding", "RouteResult", "IntentRouterAdapter", "safe_route",
           "MemoryPendingStore"]
