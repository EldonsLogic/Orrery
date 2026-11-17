"""Stable finding codes and the Finding record. Codes only: no user-visible English lives here (text comes from i18n later)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

REFUSAL, ADJUSTMENT, WARNING, NOTICE = "refusal", "adjustment", "warning", "notice"
SEVERITIES = (REFUSAL, ADJUSTMENT, WARNING, NOTICE)

# ---- refusals: colours (from the guardrails of derive_tenant_theme) ----
COLOUR_INVALID_HEX = "TKN-COLOUR-INVALID-HEX"
COLOUR_GREY = "TKN-COLOUR-GREY"
COLOUR_NEAR_CRIMSON = "TKN-COLOUR-NEAR-CRIMSON"
COLOUR_TOO_LIGHT = "TKN-COLOUR-TOO-LIGHT"
COLOUR_TOO_DARK = "TKN-COLOUR-TOO-DARK"
COLOUR_NO_AA = "TKN-COLOUR-NO-AA"
COLOUR_DARK_GREY = "TKN-COLOUR-DARK-GREY"
COLOUR_DARK_NEAR_TEXT = "TKN-COLOUR-DARK-NEAR-TEXT"
COLOUR_REJECTED = "TKN-COLOUR-REJECTED"  # a derive rejection this adapter does not recognise (fail closed)
ACCENT_GREY = "TKN-ACCENT-GREY"
ACCENT_NEAR_CRIMSON = "TKN-ACCENT-NEAR-CRIMSON"
ACCENT_TOO_LIGHT = "TKN-ACCENT-TOO-LIGHT"
ACCENT_NO_AA = "TKN-ACCENT-NO-AA"
ACCENT_TOO_CLOSE_PRIMARY = "TKN-ACCENT-TOO-CLOSE-PRIMARY"
CONTRAST_INTERNAL = "TKN-CONTRAST-INTERNAL"  # a final pair failed re-verification (a bug, not a colour problem)

# ---- refusals: structure ----
TOKEN_LOCKED = "TKN-TOKEN-LOCKED"
TOKEN_DERIVED_ONLY = "TKN-TOKEN-DERIVED-ONLY"
TOKEN_UNKNOWN = "TKN-TOKEN-UNKNOWN"
TOKEN_BAD_NAME = "TKN-TOKEN-BAD-NAME"
FIELD_LOCKED = "TKN-FIELD-LOCKED"
FIELD_UNKNOWN = "TKN-FIELD-UNKNOWN"
FIELD_TYPE = "TKN-FIELD-TYPE"
FIELD_CONFLICT = "TKN-FIELD-CONFLICT"
SLUG_INVALID = "TKN-SLUG-INVALID"
SLUG_MISSING = "TKN-SLUG-MISSING"
NAME_INVALID = "TKN-NAME-INVALID"
PREF_FIELD = "TKN-PREF-FIELD"
PREF_MODE = "TKN-PREF-MODE"
ALGO_UNSUPPORTED = "TKN-ALGO-UNSUPPORTED"
ALGO_INVALID = "TKN-ALGO-INVALID"
RESOLVED_INVALID = "TKN-RESOLVED-INVALID"
BASE_MISMATCH = "TKN-BASE-MISMATCH"
LAYER_INVALID = "TKN-LAYER-INVALID"
OUTPUT_REJECTED = "TKN-OUTPUT-REJECTED"

# ---- adjustments (from derive_tenant_theme) ----
ADJ_LIGHT_PRIMARY = "TKN-ADJ-LIGHT-PRIMARY-DARKENED"
ADJ_DARK_PRIMARY = "TKN-ADJ-DARK-PRIMARY-DERIVED"
ADJ_LIGHT_ACCENT = "TKN-ADJ-LIGHT-ACCENT-DARKENED"
ADJ_DARK_ACCENT = "TKN-ADJ-DARK-ACCENT-DERIVED"
ADJ_ACCENT_FALLBACK = "TKN-ADJ-ACCENT-FALLBACK-TEXT"
ADJ_OTHER = "TKN-ADJ-OTHER"

# ---- warnings and notices ----
WARN_NEAR_STATUS = "TKN-WARN-NEAR-STATUS"
WARN_OTHER = "TKN-WARN-OTHER"
NOTICE_ALGO_PINNED = "TKN-NOTICE-ALGO-PINNED"


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    path: str
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "severity": self.severity, "path": self.path, "params": dict(sorted(self.params.items()))}

    def sort_key(self):
        return (SEVERITIES.index(self.severity), self.path, self.code, repr(sorted(self.params.items())))
