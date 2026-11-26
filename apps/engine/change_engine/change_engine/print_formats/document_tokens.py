"""Light-theme brand token loader for printed documents (ERP-016, ADR-0014).

Printed documents take every colour and the font from ``docs/brand/tokens/tokens.json`` (the
generated token source, read-only here); nothing in the layout module is a literal. The one
addition made here is the Arabic print fallback in every font stack
(``_ARABIC_PRINT_FALLBACKS``). The file is read on first use, not at import, and a missing or
malformed file raises ``DocumentTokenError``, so a branded document is never rendered with
invented values.

Where the tokens come from, first match wins:

1. ``BRAND_TOKENS_PATH`` (operator setting, never tenant input). When set it is the only source:
   a missing file there refuses, it never falls back.
2. ``docs/brand/tokens/tokens.json``, found by walking up from this package (the repository).
3. ``brand_tokens_snapshot.json`` next to this module: a generated copy of only the values the
   layout reads, for the engine bench, which mounts the app without ``docs/`` (round 6). A test
   fails when it drifts from the token source; regenerate it with ``SNAPSHOT_COMMAND`` from the
   repository root and never hand-edit it (ADR-0014).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import re

ENV_TOKENS_PATH = "BRAND_TOKENS_PATH"
_RELATIVE = Path("docs") / "brand" / "tokens" / "tokens.json"
SNAPSHOT_PATH = Path(__file__).with_name("brand_tokens_snapshot.json")
SNAPSHOT_COMMAND = (
    "PYTHONPATH=apps/engine/change_engine python3 -c \"from change_engine.print_formats."
    "document_tokens import write_snapshot; write_snapshot()\""
)
_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}")
# One font name: words of letters, digits, "_" and "-", starting with a letter, single spaces
# between words. That is a valid unquoted CSS family (or generic) name, so nothing can end a
# declaration, add a rule or leave an empty list item such as ``a,,b`` or a trailing comma.
_FONT_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*( [A-Za-z][A-Za-z0-9_-]*)*")
# CSS-wide keywords and ``default`` are not valid family names (CSS Fonts 4, 2.1.1, accessed
# 2026-11-21): ``inherit, sans-serif`` would make the whole declaration invalid.
_RESERVED_FONT_NAMES = frozenset({"inherit", "initial", "unset", "revert", "revert-layer",
                                  "default"})
# A generic family is only a generic when it is unquoted; the primary family is quoted.
_GENERIC_FONT_NAMES = frozenset({"serif", "sans-serif", "system-ui", "monospace", "cursive",
                                 "fantasy", "ui-serif", "ui-sans-serif", "ui-monospace",
                                 "ui-rounded", "math", "emoji", "fangsong"})
_MAX_FONT_NAME = 64
_MAX_FALLBACKS = 6
# Placed right after the token family, ahead of any generic: a PDF renderer without the brand
# families must not fall to a generic that may have no Arabic glyphs on a legal document.
_ARABIC_PRINT_FALLBACKS = ("Noto Sans Arabic", "DejaVu Sans")
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
    heading_font_stack: str  # the same, built from the heading family token (titles, figures)


def load_document_tokens(path: Path) -> DocumentTokens:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        light = data["color"]["light"]
        colours = {key: light[key]["hex"] for key in _COLOUR_KEYS}
        families = data["typography"]["families"]
        body, heading = families["body"], families["heading"]
        family, fallback = body["family"], body["fallback"]
        heading_family, heading_fallback = heading["family"], heading["fallback"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DocumentTokenError(f"brand tokens unreadable at '{path}': {exc!r}") from exc
    for key, value in colours.items():
        if not isinstance(value, str) or not _HEX_RE.fullmatch(value):
            raise DocumentTokenError(f"brand token color.light.{key} is not #RRGGBB")
    return DocumentTokens(font_stack=_font_stack(family, fallback, "body"),
                          heading_font_stack=_font_stack(heading_family, heading_fallback,
                                                         "heading"), **colours)


def _font_stack(family: object, fallback: object, role: str) -> str:
    primary, *fallbacks = _font_names(family, fallback, role)
    quoted = [f"'{name}'" for name in (primary, *_ARABIC_PRINT_FALLBACKS)]
    return ", ".join(quoted + fallbacks)


def _font_names(family: object, fallback: object, role: str = "body") -> list[str]:
    """The family, then each fallback name, all validated (fail closed)."""
    if not isinstance(family, str) or not isinstance(fallback, str):
        raise DocumentTokenError(f"brand token {role} font family is not a plain font name")
    names = [family.strip()] + [part.strip() for part in fallback.split(",")]
    if len(names) < 2 or len(names) > _MAX_FALLBACKS + 1 or any(
            len(name) > _MAX_FONT_NAME or not _FONT_NAME_RE.fullmatch(name)
            or name.lower() in _RESERVED_FONT_NAMES for name in names):
        raise DocumentTokenError(f"brand token {role} font family is not a plain font name")
    if names[0].lower() in _GENERIC_FONT_NAMES:
        raise DocumentTokenError(
            f"brand token {role} font family cannot be a generic family name")
    return names


def snapshot_of(tokens: Mapping) -> dict:
    """The part of the token source the layout reads, in the same shape (the packaged snapshot)."""
    light = tokens["color"]["light"]
    families = tokens["typography"]["families"]
    return {
        "_generated": (f"Generated from {_RELATIVE.as_posix()} by: {SNAPSHOT_COMMAND}. "
                       "Never hand-edit (ADR-0014)."),
        "color": {"light": {key: {"hex": light[key]["hex"]} for key in _COLOUR_KEYS}},
        "typography": {"families": {
            role: {"family": families[role]["family"], "fallback": families[role]["fallback"]}
            for role in ("body", "heading")}},
    }


def write_snapshot() -> Path:
    """Regenerate ``brand_tokens_snapshot.json`` from the repository token source."""
    source = next((path for path in _candidate_paths() if path.is_file()), None)
    if source is None:
        raise DocumentTokenError(f"{_RELATIVE.as_posix()} not found; run from the repository")
    load_document_tokens(source)  # never snapshot a source the loader would refuse
    tokens = json.loads(source.read_text(encoding="utf-8"))
    SNAPSHOT_PATH.write_text(json.dumps(snapshot_of(tokens), indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    return SNAPSHOT_PATH


def _candidate_paths() -> list[Path]:
    here = Path(__file__).resolve()
    return [parent / _RELATIVE for parent in here.parents]


def _token_source() -> Path:
    override = os.environ.get(ENV_TOKENS_PATH)
    if override:
        return Path(override)
    for path in _candidate_paths():
        if path.is_file():
            return path
    return SNAPSHOT_PATH


@lru_cache(maxsize=1)
def document_tokens() -> DocumentTokens:
    """The cached light-theme tokens; raises ``DocumentTokenError`` when no source is readable."""
    path = _token_source()
    if not path.is_file():
        raise DocumentTokenError(
            f"brand token file not found at '{path}' (set {ENV_TOKENS_PATH} or run from the "
            "repository)"
        )
    return load_document_tokens(path)
