"""Rules 10 to 13: colour contrast, brand assets, white label, SA e-invoicing."""
from __future__ import annotations

from tokens import codes as TC
from tokens.brand_tools import BrandToolsUnavailable, derive_colours

from .colour import HEX_RE, contrast
from .report import Report, ValidationContext, as_dict, as_list, ptr, sid
from .theme_surfaces import SURFACES

# Q-64 (ADR-0057): the token resolver's OKLCH derive is authoritative. Rule 10 calls the same pure function
# (tokens.brand_tools.derive_colours, themeAlgo 1) so a Blueprint that validates is never refused by the resolver.
# The thresholds (4.5:1 primary text, 3:1 accent graphics) and the shift limits live in docs/brand/tools/derive_tenant_theme.py.
THRESHOLDS = {"primaryColour": 4.5, "accentColour": 3.0}
_ADJUSTED = {TC.ADJ_LIGHT_PRIMARY: "primaryColour", TC.ADJ_LIGHT_ACCENT: "accentColour"}
_KEY_OF_PATH = {"/branding/primaryColour": "primaryColour", "/branding/accentColour": "accentColour"}


def rule_contrast(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    """Rule 10. The resolver's derive decides: a refusal is an error (BP-BRAND-001); a colour it has to darken to
    reach AA is a warning plus a proposal in report.adjustments (BP-BRAND-002)."""
    branding = as_dict(bp.get("branding"))
    primary, accent = branding.get("primaryColour"), branding.get("accentColour")
    if not (isinstance(primary, str) and HEX_RE.match(primary)):
        return  # the schema step reports it; without a primary the resolver emits no tenant tokens
    if not (isinstance(accent, str) and HEX_RE.match(accent)):
        accent = None
    try:
        derived = derive_colours(primary, accent)
    except BrandToolsUnavailable:
        rep.error("BP-BRAND-001", ptr("branding", "primaryColour"), "brand colours could not be checked: the token derive is unavailable")
        return
    for f in derived.findings:
        if f.severity == TC.REFUSAL:
            key = _KEY_OF_PATH.get(f.path, "primaryColour")
            colour = branding.get(key)
            rep.error("BP-BRAND-001", ptr("branding", key),
                      f"{key} {colour} is refused by the token derive ({f.code}) and cannot be adjusted")
        elif f.code in _ADJUSTED:
            key = _ADJUSTED[f.code]
            colour, fixed = f.params["from"], f.params["to"]
            bgs = list(SURFACES["light"].values())
            need = THRESHOLDS[key]
            before = min(contrast(colour, b) for b in bgs)
            after = min(contrast(fixed, b) for b in bgs)
            rep.warn("BP-BRAND-002", ptr("branding", key),
                     f"{key} {colour} has {before:.2f}:1 in the light theme (needs {need}:1); proposed {fixed}")
            rep.adjustments.append({
                "path": ptr("branding", key), "theme": "light", "original": colour.upper(), "proposed": fixed,
                "threshold": need, "ratioBefore": round(before, 2), "ratioAfter": round(after, 2),
            })


def _asset_refs(branding: dict):
    logo = as_dict(branding.get("logo"))
    yield ("branding", "logo", "onLight"), logo.get("onLight")
    yield ("branding", "logo", "onDark"), logo.get("onDark")
    yield ("branding", "favicon", "asset"), as_dict(branding.get("favicon")).get("asset")
    yield ("branding", "loginPage", "backgroundAsset"), as_dict(branding.get("loginPage")).get("backgroundAsset")


def rule_assets(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    """Rule 11. Each assetRef must equal its stored asset record; the record is authoritative."""
    refs = [(p, r) for p, r in _asset_refs(as_dict(bp.get("branding"))) if isinstance(r, dict)]
    if not refs:
        return
    if ctx is None or ctx.assets is None:
        rep.warn("BP-ASSET-003", ptr("branding"), "brand assets not checked: no asset records supplied")
        return
    for path, ref in refs:
        aid = sid(ref.get("assetId"))
        rec = ctx.assets.get(aid) if aid else None
        if not isinstance(rec, dict):
            rep.error("BP-ASSET-002", ptr(*path, "assetId"), f"no stored asset record for '{aid}'")
            continue
        for k in ("mediaType", "bytes", "sha256", "widthPx", "heightPx", "sanitised"):
            if k in ref and (k not in rec or rec[k] != ref[k] or type(rec[k]) is not type(ref[k])):
                rep.error("BP-ASSET-001", ptr(*path, k), f"{k} does not match the stored asset record")
        if rec.get("sanitised") is not True:
            rep.error("BP-ASSET-001", ptr(*path, "sanitised"), "stored asset record is not sanitised")


def rule_white_label(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    """Rule 12. poweredBy.show=false needs the white_label entitlement; no context means fail closed."""
    if as_dict(as_dict(bp.get("branding")).get("poweredBy")).get("show") is not False:
        return
    if ctx is None or ctx.entitlements is None or "white_label" not in ctx.entitlements:
        rep.error("BP-WL-001", ptr("branding", "poweredBy", "show"),
                  "poweredBy.show=false requires the white_label entitlement (none confirmed)")


def rule_einvoicing(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    """Rule 13. For country SA with e-invoicing on: 'ar' in documentLanguages and a VAT number."""
    comp = as_dict(bp.get("compliance"))
    mode = as_dict(comp.get("eInvoicing")).get("mode")
    if comp.get("country") != "SA" or not isinstance(mode, str) or mode == "none":
        return
    if "ar" not in as_list(comp.get("documentLanguages")):
        rep.error("BP-EINV-001", ptr("compliance", "documentLanguages"),
                  "documentLanguages must contain 'ar' when SA e-invoicing is on")
    if not sid(as_dict(bp.get("company")).get("vatNumber")):
        rep.error("BP-EINV-002", ptr("company", "vatNumber"), "company.vatNumber must be set when SA e-invoicing is on")
