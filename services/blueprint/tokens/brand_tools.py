"""Adapter around the brand tools in docs/brand/tools (themelib.py, derive_tenant_theme.py). Those are reused, not rewritten.

derive_tenant_theme.py does `import themelib as T`, so a plain import would need docs/brand/tools on sys.path. Instead both
files are loaded by file path with importlib, once, with `themelib` registered for the duration of the load only (sys.path is
never changed and no bytecode is written next to the docs). The adapter turns derive's English reasons into stable codes.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional, Tuple

from . import codes as C

REPO = Path(__file__).resolve().parents[3]
TOOLS_DIR = REPO / "docs" / "brand" / "tools"


class BrandToolsUnavailable(RuntimeError):
    """docs/brand/tools could not be loaded."""


_loaded: Optional[Tuple[ModuleType, ModuleType]] = None


def _exec(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise BrandToolsUnavailable(str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load() -> Tuple[ModuleType, ModuleType]:
    """Return (themelib, derive_tenant_theme), loading them on first use."""
    global _loaded
    if _loaded is not None:
        return _loaded
    t_path, d_path = TOOLS_DIR / "themelib.py", TOOLS_DIR / "derive_tenant_theme.py"
    if not (t_path.is_file() and d_path.is_file()):
        raise BrandToolsUnavailable(f"missing brand tools under {TOOLS_DIR}")
    prev_bytecode, prev_mod = sys.dont_write_bytecode, sys.modules.get("themelib")
    sys.dont_write_bytecode = True
    try:
        themelib = _exec("seshna_brand_themelib", t_path)
        sys.modules["themelib"] = themelib
        derive = _exec("seshna_brand_derive", d_path)
    finally:
        sys.dont_write_bytecode = prev_bytecode
        if prev_mod is None:
            sys.modules.pop("themelib", None)
        else:
            sys.modules["themelib"] = prev_mod
    _loaded = (themelib, derive)
    return _loaded


def v1_base() -> Dict[str, Dict[str, str]]:
    T, _ = load()
    return {m: T.v1_base(m) for m in ("light", "dark")}


@dataclass(frozen=True)
class Derived:
    ok: bool
    findings: Tuple[C.Finding, ...]
    vars: Dict[str, Dict[str, str]] = field(default_factory=dict)  # {"light": {css var: value}, "dark": {...}}, full derive output
    colours: Dict[str, Dict[str, str]] = field(default_factory=dict)  # {"light": {"primary", "accent"}, "dark": {...}}


def _refusal_code(reason: str) -> str:
    accent = reason.startswith("Accent")
    r = reason
    if "Internal check failed" in r:
        return C.CONTRAST_INTERNAL
    if "too close to the primary" in r:
        return C.ACCENT_TOO_CLOSE_PRIMARY
    if "near-" in r or "as grey" in r:
        if r.startswith("Dark primary"):
            return C.COLOUR_DARK_GREY
        return C.ACCENT_GREY if accent else C.COLOUR_GREY
    if "indistinguishable" in r:
        return C.COLOUR_DARK_NEAR_TEXT
    if "Crimson" in r:
        return C.ACCENT_NEAR_CRIMSON if accent else C.COLOUR_NEAR_CRIMSON
    if "too light" in r:
        return C.ACCENT_TOO_LIGHT if accent else C.COLOUR_TOO_LIGHT
    if "too dark" in r:
        return C.COLOUR_TOO_DARK
    if r.startswith("No ") and "accent" in r:
        return C.ACCENT_NO_AA
    if r.startswith("No "):
        return C.COLOUR_NO_AA
    return C.COLOUR_REJECTED


def derive_colours(primary: str, accent: Optional[str]) -> Derived:
    """Run derive_tenant_theme.derive on already-validated hex strings and map its output to codes."""
    T, D = load()
    res = D.derive(primary, accent)
    p_path = "/branding/primaryColour"
    findings: List[C.Finding] = []
    if res["status"] != "ok":
        for reason in res["reasons"]:
            code = _refusal_code(reason)
            path = "/branding/accentColour" if code.startswith("TKN-ACCENT") else p_path
            findings.append(C.Finding(code, C.REFUSAL, path, {"input": res["input"]["primary"] if path == p_path else res["input"]["accent"]}))
        return Derived(False, tuple(findings))
    p_in, a_in = res["input"]["primary"], res["input"]["accent"]
    for adj in res["adjustments"]:
        if adj.startswith("light primary"):
            to = res["light"]["primary"]
            findings.append(C.Finding(C.ADJ_LIGHT_PRIMARY, C.ADJUSTMENT, p_path, {"from": p_in, "to": to, "mode": "light", "shiftL": round(T.to_oklch(p_in)[0] - T.to_oklch(to)[0], 3)}))
        elif adj.startswith("dark primary"):
            findings.append(C.Finding(C.ADJ_DARK_PRIMARY, C.ADJUSTMENT, p_path, {"from": p_in, "to": res["dark"]["primary"], "mode": "dark"}))
        elif adj.startswith("light accent"):
            to = res["light"]["accent"]
            findings.append(C.Finding(C.ADJ_LIGHT_ACCENT, C.ADJUSTMENT, "/branding/accentColour", {"from": a_in, "to": to, "mode": "light", "shiftL": round(T.to_oklch(a_in)[0] - T.to_oklch(to)[0], 3)}))
        elif adj.startswith("dark accent"):
            findings.append(C.Finding(C.ADJ_DARK_ACCENT, C.ADJUSTMENT, "/branding/accentColour", {"from": a_in, "to": res["dark"]["accent"], "mode": "dark"}))
        elif adj.startswith("accent:"):
            findings.append(C.Finding(C.ADJ_ACCENT_FALLBACK, C.ADJUSTMENT, "/branding/accentColour", {"to": "text"}))
        else:
            findings.append(C.Finding(C.ADJ_OTHER, C.ADJUSTMENT, p_path, {}))
    for w in res["warnings"]:
        m = re.search(r"\b(success|warning) colour", w)
        if m:
            findings.append(C.Finding(C.WARN_NEAR_STATUS, C.WARNING, p_path, {"status": m.group(1)}))
        else:
            findings.append(C.Finding(C.WARN_OTHER, C.WARNING, p_path, {}))
    return Derived(
        True,
        tuple(findings),
        {m: dict(res[m]["vars"]) for m in ("light", "dark")},
        {m: {"primary": res[m]["primary"], "accent": res[m]["accent"]} for m in ("light", "dark")},
    )


def locked_and_derivable_names() -> List[str]:
    """Every CSS variable name the brand tools know about (8 base colours plus all derived colours)."""
    T, _ = load()
    return sorted(set(T.BASE_VARS.values()) | {c[3] for c in T.COLOR_KEYS})
