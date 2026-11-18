"""Email and WhatsApp forwarding intake (DSC-015), tier 4. Offline, deterministic, stdlib `email`.
See README.md and docs/security/prompt-injection-defence.md (PI-007, S2, Q-E)."""
from .attachments import classify
from .email_connector import ForwardedEmailConnector, attachment_payloads, register as register_email
from .emailparse import dedupe_messages, parse_email, thread_key
from .errors import (ForwardRefusal, Fwd001NotAMessage, Fwd002ExecutableAttachment, Fwd003TooManyParts,
                     Fwd004Undecodable)
from .whatsapp import WhatsAppExportConnector, parse_chat, register as register_whatsapp

__all__ = ["ForwardedEmailConnector", "WhatsAppExportConnector", "attachment_payloads", "classify",
           "dedupe_messages", "parse_email", "parse_chat", "thread_key", "register_email", "register_whatsapp",
           "ForwardRefusal", "Fwd001NotAMessage", "Fwd002ExecutableAttachment", "Fwd003TooManyParts",
           "Fwd004Undecodable"]
