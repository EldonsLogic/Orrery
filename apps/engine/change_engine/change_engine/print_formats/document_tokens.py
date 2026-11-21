"""Light-theme brand token loader for printed documents (ERP-016, ADR-0014).

Printed documents take every colour and the font from ``docs/brand/tokens/tokens.json`` (the
generated token source, read-only here); nothing in the layout module is a literal. The file is
read on first use, not at import: the engine app is also mounted where ``docs/`` does not exist
(the dev bench), and the ERP-007 print hook must keep importing there. A missing or malformed file
raises ``DocumentTokenError``, so a branded document is never rendered with invented values.

``BRAND_TOKENS_PATH`` names the file for deployments that ship it elsewhere (operator setting,
never tenant input). Without it the file is found by walking up from this package to the repo root.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import re

ENV_TOKENS_PATH = "BRAND_TOKENS_PATH"
_RELATIVE = Path("docs") / "brand" / "tokens" / "tokens.json"
_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}")
# One font name: words of letters, digits, "_" and "-", starting with a letter, single spaces
# between words. That is a valid unquoted CSS family (or generic) name, so nothing can end a
# declaration, add a rule or leave an empty list item such as ``a,,b`` or a trailing comma.
_FONT_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*( [A-Za-z][A-Za-z0-9_-]*)*")
_MAX_FONT_NAME = 64
_MAX_FALLBACKS = 6
_COLOUR_KEYS = ("surface", "background", "text", "primary", "success", "warning", "danger")


class DocumentTokenError(RuntimeError):
    """The brand token source is missing or malformed; documents must not render."""


@dataclass(frozen=True)
class DocumentTokens:
    surface: str
    background: str
    text: str
    primary: str
    success: str
    warning: str
    danger: str
    font_stack: str  # CSS ``font-family`` value built from the body family token


def load_document_tokens(path: Path) -> DocumentTokens:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        light = data["color"]["light"]
        colours = {key: light[key]["hex"] for key in _COLOUR_KEYS}
        body = data["typography"]["families"]["body"]
        family, fallback = body["family"], body["fallback"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DocumentTokenError(f"brand tokens unreadable at '{path}': {exc!r}") from exc
    for key, value in colours.items():
        if not isinstance(value, str) or not _HEX_RE.fullmatch(value):
            raise DocumentTokenError(f"brand token color.light.{key} is not #RRGGBB")
    names = _font_names(family, fallback)
    return DocumentTokens(font_stack=f"'{names[0]}', {', '.join(names[1:])}", **colours)


def _font_names(family: object, fallback: object) -> list[str]:
    """The body family, then each fallback name, all validated (fail closed)."""
    if not isinstance(family, str) or not isinstance(fallback, str):
        raise DocumentTokenError("brand token body font family is not a plain font name")
    names = [family.strip()] + [part.strip() for part in fallback.split(",")]
    if len(names) < 2 or len(names) > _MAX_FALLBACKS + 1 or any(
            len(name) > _MAX_FONT_NAME or not _FONT_NAME_RE.fullmatch(name) for name in names):
        raise DocumentTokenError("brand token body font family is not a plain font name")
    return names


def _candidate_paths() -> list[Path]:
    override = os.environ.get(ENV_TOKENS_PATH)
    if override:
        return [Path(override)]
    here = Path(__file__).resolve()
    return [parent / _RELATIVE for parent in here.parents]


@lru_cache(maxsize=1)
def document_tokens() -> DocumentTokens:
    """The cached light-theme tokens; raises ``DocumentTokenError`` when the file is absent."""
    for path in _candidate_paths():
        if path.is_file():
            return load_document_tokens(path)
    raise DocumentTokenError(
        f"brand token file not found (set {ENV_TOKENS_PATH} or run from the repository)"
    )
