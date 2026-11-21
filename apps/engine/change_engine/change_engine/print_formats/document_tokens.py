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
_FAMILY_RE = re.compile(r"[A-Za-z0-9 _-]{1,64}")
_FALLBACK_RE = re.compile(r"[A-Za-z0-9 ,_-]{1,128}")
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
    if not isinstance(family, str) or not _FAMILY_RE.fullmatch(family) \
            or not isinstance(fallback, str) or not _FALLBACK_RE.fullmatch(fallback):
        raise DocumentTokenError("brand token body font family is not a plain font name")
    return DocumentTokens(font_stack=f"'{family}', {fallback}", **colours)


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
