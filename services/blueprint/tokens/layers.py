"""Layer 0 and layer 1 helpers: validate and merge token sets, and parse the GENERATED token CSS files into token sets.

A token set is {"shared": {var: value}, "light": {...}, "dark": {...}} (every key optional). `shared` applies to both themes.
The CSS parser is for tests, tooling and the later server wiring; it reads text it is given and never touches the filesystem.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

TOKEN_NAME = re.compile(r"--[a-z0-9][a-z0-9_-]{0,63}")
SECTIONS = ("shared", "light", "dark")
THEMES = ("light", "dark")


def validate_layer(layer: Any) -> bool:
    """True when `layer` is a token set of well-formed names and string values."""
    if layer is None:
        return True
    if not isinstance(layer, Mapping) or any(k not in SECTIONS for k in layer):
        return False
    for sec in layer.values():
        if not isinstance(sec, Mapping):
            return False
        for k, v in sec.items():
            if not isinstance(k, str) or not TOKEN_NAME.fullmatch(k) or not isinstance(v, str):
                return False
    return True


def merge(*layers: Optional[Mapping[str, Mapping[str, str]]]) -> Dict[str, Dict[str, str]]:
    """Merge token sets lowest precedence first into {"light": {...}, "dark": {...}} (shared applied under each theme)."""
    out: Dict[str, Dict[str, str]] = {"light": {}, "dark": {}}
    for layer in layers:
        if not layer:
            continue
        for theme in THEMES:
            out[theme].update(layer.get("shared", {}))
            out[theme].update(layer.get(theme, {}))
    return {t: dict(sorted(v.items())) for t, v in out.items()}


def _blocks(css: str) -> List[Tuple[str, int, str]]:
    """(selector, depth, body) for every rule that directly holds declarations."""
    out: List[Tuple[str, int, str]] = []
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    stack: List[Tuple[str, int]] = []
    start = 0
    for i, ch in enumerate(css):
        if ch == "{":
            stack.append((css[start:i].strip(), i + 1))
            start = i + 1
        elif ch == "}":
            sel, body_start = stack.pop()
            body = css[body_start:i]
            if "{" not in body:
                out.append((sel, len(stack), body))
            start = i + 1
    return out


def _decls(body: str) -> Dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"(--[a-zA-Z0-9_-]+)\s*:\s*([^;]+);", body)}


def layer_from_css(css: str) -> Dict[str, Dict[str, str]]:
    """Parse a generated tokens CSS file: top-level `:root` (light plus shared) and `:root[data-theme="dark"]` (dark).
    A variable is `shared` when it is not redeclared in the dark block, otherwise `light`/`dark`."""
    root: Dict[str, str] = {}
    dark: Dict[str, str] = {}
    for sel, depth, body in _blocks(css):
        if depth == 0 and sel == ":root" and not root:
            root = _decls(body)
        elif depth == 0 and sel == ':root[data-theme="dark"]':
            dark = _decls(body)
    shared = {k: v for k, v in root.items() if k not in dark}
    light = {k: v for k, v in root.items() if k in dark}
    # Dark-only variables (declared only in the dark block) stay dark-only.
    dark_only = {k: v for k, v in dark.items()}
    return {"shared": dict(sorted(shared.items())), "light": dict(sorted(light.items())), "dark": dict(sorted(dark_only.items()))}
