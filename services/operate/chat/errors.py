"""User-visible chat errors (ADR-0036). Customer text comes only from this closed table or the Tool API catalog.

The chat codes below are chat-level (no record params). They are not in `contracts/tool-api-error-catalog.json` yet
(Q-261). Arabic text is marked unreviewed (ADR-0033). Raw exception text never leaves; it is logged by type only."""
from __future__ import annotations

import logging
import uuid

log = logging.getLogger("chat")

# code -> (retryable, en, ar). Arabic is UNREVIEWED.
TABLE = {
    "chat_session_not_found": (False, "This conversation was not found. Start a new one.",
                               "لم يتم العثور على هذه المحادثة. ابدأ محادثة جديدة."),
    "chat_run_in_progress": (True, "I am still answering your last message. Wait for it to finish or stop it.",
                             "ما زلت أجيب على رسالتك السابقة. انتظر حتى تنتهي أو أوقفها."),
    "chat_message_too_long": (False, "That message is too long. Please shorten it or split it.",
                              "الرسالة طويلة جدا. يرجى اختصارها أو تقسيمها."),
    "chat_message_empty": (False, "The message is empty.", "الرسالة فارغة."),
    "chat_message_id_invalid": (False, "The message could not be sent. Please try again.",
                                "تعذر إرسال الرسالة. حاول مرة أخرى."),
    "chat_message_id_conflict": (False, "This message id was already used for a different message.",
                                 "تم استخدام معرف الرسالة هذا لرسالة مختلفة."),
    "chat_rate_limited": (True, "You are sending messages too quickly. Try again in {minutes} min.",
                          "أنت ترسل الرسائل بسرعة كبيرة. حاول مرة أخرى بعد {minutes} دقيقة."),
    "chat_limit_unavailable": (False, "Messages cannot be accepted right now. If this continues, contact support.",
                               "لا يمكن قبول الرسائل الآن. إذا استمر ذلك، تواصل مع الدعم."),
    "chat_cancelled": (True, "Stopped.", "تم الإيقاف."),
    "permission_denied": (False, "You do not have access to this.", "ليس لديك صلاحية الوصول إلى هذا."),
    "internal_error": (True, "Something went wrong on our side. Please try again.",
                       "حدث خطأ من جانبنا. يرجى المحاولة مرة أخرى."),
}
ARABIC_REVIEW = "unreviewed"


class ChatFailure(Exception):
    """A failure expressed as a code from `TABLE`. An unknown code becomes `internal_error`."""

    def __init__(self, code: str, params: dict | None = None):
        super().__init__(code)
        self.code = code if code in TABLE else "internal_error"
        self.params = {k: v for k, v in (params or {}).items() if isinstance(k, str) and type(v) is int}


def render(code: str, locale: str = "en", params: dict | None = None) -> dict:
    """{"code", "message", "message_key", "retryable", "params"} for the wire; falls back to English. Only integer
    params fill a template; a template whose params are missing falls back to `internal_error`."""
    code = code if code in TABLE else "internal_error"
    retry, en, ar = TABLE[code]
    params = {k: v for k, v in (params or {}).items() if isinstance(k, str) and type(v) is int}
    try:
        message = (ar if locale == "ar" else en).format(**params)
    except (KeyError, IndexError, ValueError):
        return render("internal_error", locale)
    return {"code": code, "message": message, "message_key": f"errors.{code}", "retryable": retry, "params": params}


def firewall(exc: BaseException, locale: str = "en") -> dict:
    """Any exception to a safe error dict. Only the exception type is logged, against a correlation id."""
    if isinstance(exc, ChatFailure):
        return render(exc.code, locale, exc.params)
    status = getattr(exc, "status", None)
    if type(exc).__name__ == "AuthFailure" and status in (401, 403):
        return render("permission_denied", locale)
    log.error("chat failure correlation_id=%s type=%s", uuid.uuid4().hex, type(exc).__name__)
    return render("internal_error", locale)
