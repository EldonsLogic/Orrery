"""Rules 10 to 13: colour contrast, brand assets, white label, SA e-invoicing."""
from __future__ import annotations

from .colour import HEX_RE, auto_adjust, contrast, passes_all
from .report import Report, ValidationContext, as_dict, as_list, ptr, sid
from .theme_surfaces import SURFACES

# Thresholds (docs/architecture/theming.md, "Guardrails"):
#   primaryColour is used for text and links (tokens.json claims primary-on-surface at 4.5), so it
#   must reach 4.5:1 against the surface AND the background of each theme.
#   accentColour is graphics only (tokens.json note: "Coral is for graphics only"), so it must reach
#   3:1 (UI components and graphics) against the surface AND the background of each theme.
THRESHOLDS = {"primaryColour": 4.5, "accentColour": 3.0}


def rule_contrast(bp: dict, ctx: ValidationContext | None, rep: Report) -> None:
    """Rule 10. Per colour and theme: pass, auto_adjust (warning plus a proposal in report.adjustments;
    same hue and saturation, nearest passing lightness within the allowed shift) or reject (error)."""
    branding = as_dict(bp.get("branding"))
    for key, need in THRESHOLDS.items():
        colour = branding.get(key)
        if not (isinstance(colour, str) and HEX_RE.match(colour)):
            continue
        for theme, tokens in SURFACES.items():
            bgs = [tokens["surface"], tokens["background"]]
            if passes_all(colour, bgs, need):
                continue
            path = ptr("branding", key)
            worst = min(contrast(colour, b) for b in bgs)
            fixed = auto_adjust(colour, bgs, need)
            if fixed is None:
                rep.error("BP-BRAND-001", path,
                          f"{key} {colour} has {worst:.2f}:1 in the {theme} theme (needs {need}:1) and cannot be adjusted")
                continue
            rep.warn("BP-BRAND-002", path,
                     f"{key} {colour} has {worst:.2f}:1 in the {theme} theme (needs {need}:1); proposed {fixed}")
            rep.adjustments.append({
                "path": path, "theme": theme, "original": colour.upper(), "proposed": fixed,
                "threshold": need, "ratioBefore": round(worst, 2),
                "ratioAfter": round(min(contrast(fixed, b) for b in bgs), 2),
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
