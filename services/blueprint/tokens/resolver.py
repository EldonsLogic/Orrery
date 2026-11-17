"""resolve_tokens: the pure, deterministic token resolver (layers 0 to 3 of docs/brand/12-tenant-theming.md)."""
from __future__ import annotations

import copy
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from . import brand_tools, layers
from . import codes as C
from .codes import Finding

# The only custom properties a tenant can ever cause to be emitted (12-tenant-theming.md section 2, "May override" row Primary and
# Accent). The focus ring colour is `--color-primary` (there is no separate ring token), so it follows the primary.
TENANT_TOKENS: Tuple[str, ...] = tuple(sorted((
    "--color-primary", "--color-primary-hover", "--color-primary-pressed", "--color-primary-label", "--color-link-visited",
    "--state-selected", "--state-secondary-hover", "--state-secondary-pressed", "--color-device-primary", "--color-accent",
)))
ACCENT_VAR = "--color-accent"

THEME_MODES = ("light", "dark", "system")
ALLOWED_FIELDS = frozenset({
    "displayName", "primaryColour", "accentColour", "primary", "accent", "logo", "favicon", "loginPage", "documentHeader",
    "poweredBy", "provenance", "version", "themeAlgo", "resolved", "tokens",
})
# Field names that are recognisably locked categories (refused with a specific code instead of the generic unknown-field one).
LOCKED_FIELDS = frozenset({
    "typography", "fonts", "font", "spacing", "radius", "radii", "motion", "focusRing", "statusColours", "statusColors",
    "success", "warning", "danger", "neutrals", "background", "surface", "text", "chart", "chartPalette", "icons", "colors", "colours",
})
OBJECT_FIELDS = ("logo", "favicon", "loginPage", "documentHeader", "poweredBy", "provenance")

SLUG = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
HEX = re.compile(r"#[0-9A-Fa-f]{6}")
LOCALE = re.compile(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*")
_VALUE = re.compile(r"#[0-9A-F]{6}|rgba\((\d{1,3}),(\d{1,3}),(\d{1,3}),(0|1|0\.\d{1,4})\)")
_SAFE_NAME = re.compile(r"[A-Za-z0-9_.-]{1,64}")
NAME_MAX = 40

# Checked against the merged layers before anything is derived: derive_tenant_theme measures contrast against the v1 base colours.
_BASE_KEYS = {"--color-background": "background", "--color-surface": "surface", "--color-text": "text",
              "--color-success": "success", "--color-warning": "warning", "--color-danger": "danger"}

Algorithm = Callable[[str, Optional[str]], brand_tools.Derived]


def default_algorithms() -> Dict[int, Algorithm]:
    """themeAlgo -> implementation. Version 1 is derive_tenant_theme.py as it stands (PROPOSED constants)."""
    return {1: brand_tools.derive_colours}


@dataclass(frozen=True)
class ResolvedTokens:
    ok: bool                                   # False when any refusal was raised (the rest of the result is still safe to use)
    resolved: Dict[str, Dict[str, str]]        # full token sets, layers 0 to 2: {"light": {var: value}, "dark": {...}}
    tenant_tokens: Dict[str, Dict[str, str]]   # layer 2 only: the tenant-owned variables, {"light": {...}, "dark": {...}}
    css: str                                   # layer 2 as CSS text ("" when the tenant overrides nothing); load after layer 1
    theme_algo: Optional[int]                  # algorithm version the tenant tokens were derived with; None without tenant colours
    tenant_slug: Optional[str]                 # validated slug when tenant tokens are emitted
    theme_mode: str                            # layer 3: "light", "dark" or "system"
    html_attributes: Dict[str, str]            # attributes for <html>: data-tenant (when tenant tokens), data-theme (unless system)
    brand: Dict[str, Any]                      # untouched references for non-CSS surfaces: displayName, logo, favicon
    findings: Tuple[Finding, ...] = field(default_factory=tuple)

    @property
    def refusals(self) -> Tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == C.REFUSAL)

    @property
    def adjustments(self) -> Tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == C.ADJUSTMENT)

    @property
    def to_store(self) -> Optional[Dict[str, Any]]:
        """What to persist on an explicit branding save so a later algorithm change never restyles the tenant."""
        if self.theme_algo is None:
            return None
        return {"themeAlgo": self.theme_algo, "resolved": {m: dict(v) for m, v in self.tenant_tokens.items()}}

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "resolved": self.resolved, "tenantTokens": self.tenant_tokens, "css": self.css, "themeAlgo": self.theme_algo,
                "tenantSlug": self.tenant_slug, "themeMode": self.theme_mode, "htmlAttributes": self.html_attributes, "brand": self.brand,
                "findings": [f.to_dict() for f in self.findings]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _safe(name: Any) -> Optional[str]:
    return name if isinstance(name, str) and _SAFE_NAME.fullmatch(name) else None


def _pref(pref: Any, findings: List[Finding]) -> str:
    value: Any = "system"
    if pref is None:
        return value
    if isinstance(pref, str):
        value = pref
    elif isinstance(pref, Mapping):
        for k in sorted((k for k in pref if k != "theme"), key=repr):
            findings.append(Finding(C.PREF_FIELD, C.REFUSAL, "/userPreference", {"name": _safe(k)}))
        value = pref.get("theme", "system")
    else:
        findings.append(Finding(C.PREF_MODE, C.REFUSAL, "/userPreference", {}))
        return "system"
    if value not in THEME_MODES:
        findings.append(Finding(C.PREF_MODE, C.REFUSAL, "/userPreference/theme", {}))
        return "system"
    return value


def _display_name(v: Any, findings: List[Finding]) -> Optional[Dict[str, str]]:
    path = "/branding/displayName"
    if not isinstance(v, Mapping) or not v:
        findings.append(Finding(C.NAME_INVALID, C.REFUSAL, path, {}))
        return None
    ok = True
    for loc, text in v.items():
        if not (isinstance(loc, str) and LOCALE.fullmatch(loc) and isinstance(text, str)):
            ok = False
        elif not (1 <= len(text) <= NAME_MAX) or not text.strip() or any(unicodedata.category(ch) in ("Cc", "Cs") for ch in text):
            ok = False
    if not ok:
        findings.append(Finding(C.NAME_INVALID, C.REFUSAL, path, {"maxLength": NAME_MAX}))
        return None
    return {k: v[k] for k in sorted(v)}


def _tokens_attempt(v: Any, known: frozenset, findings: List[Finding]) -> None:
    """Direct token overrides are never applied: every entry is refused and logged."""
    path = "/branding/tokens"
    if not isinstance(v, Mapping):
        findings.append(Finding(C.FIELD_TYPE, C.REFUSAL, path, {}))
        return
    for name in sorted(v, key=repr):
        if not isinstance(name, str) or not layers.TOKEN_NAME.fullmatch(name):
            code = C.TOKEN_BAD_NAME
        elif name in TENANT_TOKENS:
            code = C.TOKEN_DERIVED_ONLY
        elif name in known:
            code = C.TOKEN_LOCKED
        else:
            code = C.TOKEN_UNKNOWN
        findings.append(Finding(code, C.REFUSAL, path, {"name": _safe(name)}))


def _hex(v: Any, path: str, findings: List[Finding]) -> Optional[str]:
    if isinstance(v, str) and HEX.fullmatch(v):
        return v.upper()
    findings.append(Finding(C.COLOUR_INVALID_HEX, C.REFUSAL, path, {}))
    return None


def _value_ok(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    m = _VALUE.fullmatch(v)
    return bool(m) and (m.group(1) is None or all(int(m.group(i)) <= 255 for i in (1, 2, 3)))


def _stored(branding: Mapping, findings: List[Finding]) -> Optional[Dict[str, Dict[str, str]]]:
    """Validate a stored `resolved` block ({"light": {...}, "dark": {...}}); None (and a refusal) when it is not safe to use."""
    path = "/branding/resolved"
    r = branding["resolved"]
    ok = isinstance(r, Mapping) and set(r) == {"light", "dark"} and isinstance(branding.get("themeAlgo"), int) and not isinstance(branding.get("themeAlgo"), bool)
    if ok:
        for m in ("light", "dark"):
            sec = r[m]
            if not (isinstance(sec, Mapping) and sec and all(k in TENANT_TOKENS and _value_ok(val) for k, val in sec.items())):
                ok = False
    if not ok:
        findings.append(Finding(C.RESOLVED_INVALID, C.REFUSAL, path, {}))
        return None
    return {m: {k: r[m][k] for k in sorted(r[m])} for m in ("light", "dark")}


def _render(slug: str, tokens: Mapping[str, Mapping[str, str]]) -> str:
    def block(theme: str, ind: str) -> str:
        return "".join(f"{ind}{k}: {tokens[theme][k]};\n" for k in sorted(tokens[theme]))
    s = f':root[data-tenant="{slug}"] {{\n{block("light", "  ")}}}\n\n'
    s += f'@media (prefers-color-scheme: dark) {{\n  :root[data-tenant="{slug}"]:not([data-theme="light"]) {{\n{block("dark", "    ")}  }}\n}}\n\n'
    s += f':root[data-tenant="{slug}"][data-theme="dark"] {{\n{block("dark", "  ")}}}\n'
    return s


def resolve_tokens(
    base_tokens: Optional[Mapping[str, Mapping[str, str]]],
    product_theme_tokens: Optional[Mapping[str, Mapping[str, str]]],
    tenant_branding: Optional[Mapping[str, Any]],
    user_preference: Any,
    *,
    algo_version: int,
    tenant_slug: Optional[str] = None,
    algorithms: Optional[Mapping[int, Algorithm]] = None,
) -> ResolvedTokens:
    """Resolve the four token layers. Pure and deterministic; never raises for bad input (it refuses and falls back).

    base_tokens / product_theme_tokens: token sets {"shared"|"light"|"dark": {"--var": "value"}} (layers 0 and 1).
    tenant_branding: the Blueprint `branding` section (contract names primaryColour/accentColour; primary/accent accepted as aliases).
    user_preference: None, "light" | "dark" | "system", or {"theme": ...}; anything else is refused.
    algo_version: the derivation algorithm to use for a tenant whose branding does not pin one (`themeAlgo`).
    tenant_slug: lands in a CSS selector, so it is validated strictly; required when the tenant overrides colours.
    """
    findings: List[Finding] = []
    algos = dict(algorithms) if algorithms is not None else default_algorithms()

    if not (layers.validate_layer(base_tokens) and layers.validate_layer(product_theme_tokens)):
        findings.append(Finding(C.LAYER_INVALID, C.REFUSAL, "/layers", {}))
        base_tokens = product_theme_tokens = None
    merged = layers.merge(base_tokens, product_theme_tokens)
    known = frozenset(merged["light"]) | frozenset(merged["dark"]) | frozenset(brand_tools.locked_and_derivable_names())
    mode = _pref(user_preference, findings)

    tenant: Dict[str, Dict[str, str]] = {"light": {}, "dark": {}}
    brand: Dict[str, Any] = {}
    theme_algo: Optional[int] = None
    slug_out: Optional[str] = None

    b = tenant_branding
    if b is not None and not isinstance(b, Mapping):
        findings.append(Finding(C.FIELD_TYPE, C.REFUSAL, "/branding", {}))
        b = None
    b = b or {}

    # ---- structure: unknown and locked fields, token overrides, names, references ----
    for k in sorted(b, key=repr):
        if k in ALLOWED_FIELDS:
            continue
        code = C.FIELD_LOCKED if k in LOCKED_FIELDS else C.FIELD_UNKNOWN
        findings.append(Finding(code, C.REFUSAL, "/branding", {"name": _safe(k)}))
    if "tokens" in b:
        _tokens_attempt(b["tokens"], known, findings)
    if "displayName" in b:
        name = _display_name(b["displayName"], findings)
        if name is not None:
            brand["displayName"] = name
    for k in OBJECT_FIELDS:
        if k in b and not isinstance(b[k], Mapping):
            findings.append(Finding(C.FIELD_TYPE, C.REFUSAL, f"/branding/{k}", {}))
        elif k in ("logo", "favicon") and k in b:
            brand[k] = copy.deepcopy(b[k])

    # ---- colours ----
    colours: Dict[str, Optional[str]] = {}
    for canon, alias in (("primaryColour", "primary"), ("accentColour", "accent")):
        if canon in b and alias in b:
            findings.append(Finding(C.FIELD_CONFLICT, C.REFUSAL, f"/branding/{canon}", {}))
            colours[canon] = None
            colours["_bad"] = "1"
        elif canon in b or alias in b:
            raw = b[canon] if canon in b else b[alias]
            if raw is None and canon == "accentColour":
                colours[canon] = None
            else:
                v = _hex(raw, f"/branding/{canon}", findings)
                colours[canon] = v
                if v is None:
                    colours["_bad"] = "1"
    primary, accent = colours.get("primaryColour"), colours.get("accentColour")
    has_resolved = "resolved" in b
    wants_tokens = (primary is not None or has_resolved) and "_bad" not in colours

    if wants_tokens:
        if tenant_slug is None:
            findings.append(Finding(C.SLUG_MISSING, C.REFUSAL, "/tenantSlug", {}))
        elif not (isinstance(tenant_slug, str) and SLUG.fullmatch(tenant_slug)):
            findings.append(Finding(C.SLUG_INVALID, C.REFUSAL, "/tenantSlug", {}))
        else:
            slug_out = tenant_slug
    if wants_tokens and slug_out is not None:
        stored_algo = b.get("themeAlgo")
        if has_resolved:
            got = _stored(b, findings)
            if got is not None:
                tenant, theme_algo = got, stored_algo
                if stored_algo != algo_version:
                    findings.append(Finding(C.NOTICE_ALGO_PINNED, C.NOTICE, "/branding/themeAlgo", {"stored": stored_algo, "current": algo_version}))
        else:
            effective: Any = stored_algo if stored_algo is not None else algo_version
            if not isinstance(effective, int) or isinstance(effective, bool):
                findings.append(Finding(C.ALGO_INVALID if stored_algo is not None else C.ALGO_UNSUPPORTED, C.REFUSAL,
                                        "/branding/themeAlgo" if stored_algo is not None else "/algoVersion", {}))
                effective = None
            elif effective not in algos:
                findings.append(Finding(C.ALGO_UNSUPPORTED, C.REFUSAL, "/branding/themeAlgo" if stored_algo is not None else "/algoVersion", {"version": effective}))
                effective = None
            if effective is not None and stored_algo is not None and stored_algo != algo_version:
                findings.append(Finding(C.NOTICE_ALGO_PINNED, C.NOTICE, "/branding/themeAlgo", {"stored": stored_algo, "current": algo_version}))
            if effective is not None:
                bm = _base_mismatch(merged)
                if bm:
                    findings.append(Finding(C.BASE_MISMATCH, C.REFUSAL, "/layers", {"names": bm}))
                else:
                    d = algos[effective](primary, accent)
                    findings.extend(d.findings)
                    if d.ok:
                        for m in ("light", "dark"):
                            vals = {k: d.vars[m][k] for k in TENANT_TOKENS if k in d.vars[m]}
                            if accent is None and vals.get(ACCENT_VAR, "").upper() == merged[m].get(ACCENT_VAR, "").upper():
                                vals.pop(ACCENT_VAR, None)  # Coral stays: nothing to override
                            tenant[m] = dict(sorted(vals.items()))
                        theme_algo = effective

    # ---- last line of defence: only allow-listed names and strictly shaped values reach the output ----
    if any(k not in TENANT_TOKENS or not _value_ok(v) for m in tenant for k, v in tenant[m].items()):
        findings.append(Finding(C.OUTPUT_REJECTED, C.REFUSAL, "/tenantTokens", {}))
        tenant = {"light": {}, "dark": {}}
    if any(f.severity == C.REFUSAL and f.code.startswith(("TKN-COLOUR", "TKN-ACCENT")) for f in findings):
        tenant = {"light": {}, "dark": {}}
    if not (tenant["light"] or tenant["dark"]):
        theme_algo, slug_out, css = None, None, ""
    else:
        css = _render(slug_out, tenant)  # type: ignore[arg-type]

    resolved = {m: dict(sorted({**merged[m], **tenant[m]}.items())) for m in ("light", "dark")}
    attrs: Dict[str, str] = {}
    if css:
        attrs["data-tenant"] = slug_out  # type: ignore[assignment]
    if mode != "system":
        attrs["data-theme"] = mode
    findings.sort(key=lambda f: f.sort_key())
    return ResolvedTokens(not any(f.severity == C.REFUSAL for f in findings), resolved, tenant, css, theme_algo, slug_out, mode,
                          dict(sorted(attrs.items())), brand, tuple(findings))


def _base_mismatch(merged: Mapping[str, Mapping[str, str]]) -> List[str]:
    v1 = brand_tools.v1_base()
    bad = []
    for m in ("light", "dark"):
        for var, key in _BASE_KEYS.items():
            if merged[m].get(var, "").upper() != v1[m][key].upper():
                bad.append(f"{m}:{var}")
    return bad
