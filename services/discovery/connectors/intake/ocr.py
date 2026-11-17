"""OCR engine port. The pipeline never imports an engine; the platform injects one. Engine output is
untrusted content (L3): it is validated for shape here and sanitised and labelled by the runner."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from .errors import Int008OcrInvalid


@dataclass(frozen=True)
class OcrToken:
    text: str
    confidence: float            # 0..1, per token
    box: tuple                   # (x, y, w, h) in page pixels
    line: int                    # line index on the page, reading order
    visible: bool = True         # False for white-on-white, tiny or off-page text (A01/A02)
    hidden_reason: str = ""
    language: str = ""           # "ar", "en", "" when unknown


@dataclass(frozen=True)
class OcrResult:
    tokens: tuple
    language: str = ""           # page-level language, "" when unknown


@runtime_checkable
class OcrEngine(Protocol):
    def recognise(self, image_bytes: bytes, hints: dict) -> OcrResult:
        """hints: page (1-based), kind (pdf|png|jpeg|tiff), languages (list of codes)."""
        ...


def validate_result(res: object, max_tokens: int) -> OcrResult:
    if not isinstance(res, OcrResult) or not isinstance(res.tokens, (tuple, list)):
        raise Int008OcrInvalid("engine did not return an OcrResult")
    if len(res.tokens) > max_tokens:
        raise Int008OcrInvalid("too many tokens")
    for t in res.tokens:
        if not isinstance(t, OcrToken) or not isinstance(t.text, str):
            raise Int008OcrInvalid("bad token")
        c = t.confidence
        if isinstance(c, bool) or not isinstance(c, (int, float)) or not 0 <= c <= 1:
            raise Int008OcrInvalid("token confidence outside 0..1")
        b = t.box
        if (not isinstance(b, (tuple, list)) or len(b) != 4
                or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in b)):
            raise Int008OcrInvalid("bad token box")
        if isinstance(t.line, bool) or not isinstance(t.line, int) or t.line < 0 or not isinstance(t.visible, bool):
            raise Int008OcrInvalid("bad token line or visibility")
    return OcrResult(tuple(res.tokens), res.language if isinstance(res.language, str) else "")
