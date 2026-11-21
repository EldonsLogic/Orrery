"""Tenant branding resolution for printed documents (ERP-016, ADR-0014).

A tenant may set a display name (Arabic and English), a primary colour, an optional accent, a
logo, a mono-logo flag and, with the plan entitlement, hide the "Powered by" mark. Nothing else:
any other field (custom CSS, layout, fonts, status colours, direction ...) is rejected, so branding
cannot reach the locked compliance layout.

Colours are checked against the print surfaces (WCAG 2.x). The primary is used as text, so it
needs 4.5:1; the accent is graphics only, so 3:1. A failing colour is darkened (hue kept, at most
45%) or rejected, depending on ``contrast_policy``. Documents always use the light theme.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
import re
from typing import Any, Mapping
import unicodedata

from .brand_assets import BrandAssetError, SanitizedLogo, sanitize_brand_logo
from .document_layout import default_primary, print_surfaces

ENTITLEMENT_REMOVE_POWERED_BY = "branding.removePoweredBy"
MIN_TEXT_CONTRAST = 4.5
MIN_GRAPHIC_CONTRAST = 3.0
_MAX_DARKENING_FACTOR = 0.55  # never scale a channel below 55% of the tenant's colour
_MIN_CHANNEL_SPREAD = 24  # below this the colour reads as grey, not as a brand colour
_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}")
_BIDI_CONTROLS = set("‪‫‬‭‮⁦⁧⁨⁩")
_POLICIES = ("adjust", "reject")


class BrandingError(ValueError):
    """Tenant branding was rejected; the message names the field and the reason."""


@dataclass(frozen=True)
class DocumentBranding:
    display_name: dict[str, str] | str | None = None
    primary_color: str | None = None
    accent_color: str | None = None
    logo: str | bytes | None = None
    mono_logo: bool = False
    show_powered_by: bool = True
    contrast_policy: str = "adjust"


@dataclass(frozen=True)
class ResolvedDocumentBranding:
    display_name_ar: str | None
    display_name_en: str | None
    primary_color: str
    accent_color: str
    logo: SanitizedLogo | None
    mono_logo: bool
    show_powered_by: bool
    adjustments: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


_FIELD_ALIASES: dict[str, str] = {
    "display_name": "display_name", "displayName": "display_name",
    "primary_color": "primary_color", "primary": "primary_color",
    "accent_color": "accent_color", "accent": "accent_color",
    "logo": "logo", "logo_data_uri": "logo", "logoDataUri": "logo",
    "mono_logo": "mono_logo", "monoLogo": "mono_logo",
    "show_powered_by": "show_powered_by", "showPoweredBy": "show_powered_by",
    "remove_powered_by": "remove_powered_by", "removePoweredBy": "remove_powered_by",
    "contrast_policy": "contrast_policy", "contrastPolicy": "contrast_policy",
}


def _channels(hex_color: str) -> tuple[int, int, int]:
    return int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)


def _luminance(hex_color: str) -> float:
    def lin(value: int) -> float:
        s = value / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = _channels(hex_color)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2.x contrast ratio between two ``#RRGGBB`` colours."""
    for value in (foreground, background):
        if not isinstance(value, str) or not _HEX_RE.fullmatch(value):
            raise ValueError(f"Invalid hex color '{value}'; expected '#RRGGBB'")
    hi, lo = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _worst_surface(hex_color: str) -> tuple[str, float]:
    return min(((s, contrast_ratio(hex_color, s)) for s in print_surfaces()), key=lambda x: x[1])


def _fit_colour(raw: Any, label: str, minimum: float, policy: str) -> tuple[str, str | None]:
    if not isinstance(raw, str) or not _HEX_RE.fullmatch(raw):
        raise BrandingError(f"{label} must be a '#RRGGBB' hex colour")
    colour = raw.lower()
    channels = _channels(colour)
    if max(channels) - min(channels) < _MIN_CHANNEL_SPREAD:
        raise BrandingError(
            f"{label} '{raw}' is near-grey, white or black and cannot meet the WCAG AA contrast "
            "guardrail as a brand colour"
        )
    surface, ratio = _worst_surface(colour)
    if ratio >= minimum:
        return colour, None
    if policy == "reject":
        raise BrandingError(
            f"{label} '{raw}' fails WCAG AA contrast on print surface {surface} "
            f"({ratio:.2f}:1 < {minimum:.2f}:1)"
        )
    for percent in range(99, int(_MAX_DARKENING_FACTOR * 100) - 1, -1):
        factor = percent / 100
        candidate = "#" + "".join(f"{round(c * factor):02x}" for c in channels)
        if _worst_surface(candidate)[1] >= minimum:
            return candidate, (
                f"{label} '{raw}' darkened to '{candidate}' for contrast "
                f"({ratio:.2f}:1 -> {_worst_surface(candidate)[1]:.2f}:1 on print surfaces)"
            )
    raise BrandingError(
        f"{label} '{raw}' fails WCAG AA contrast on print surface {surface} "
        f"({ratio:.2f}:1 < {minimum:.2f}:1) and is too light to adjust within the allowed range"
    )


def _clean_name(value: Any, label: str) -> str | None:
    if not isinstance(value, str):
        raise BrandingError(f"{label} must be text")
    text = value.strip()
    if not text:
        return None
    if len(text) > 40:
        raise BrandingError(f"{label} must be 40 characters or fewer")
    for ch in text:
        if ch in _BIDI_CONTROLS or unicodedata.category(ch) == "Cc":
            raise BrandingError(f"{label} contains control or bidirectional override characters")
    return text


def _display_names(raw: Any) -> tuple[str | None, str | None]:
    if raw is None:
        return None, None
    if isinstance(raw, str):
        name = _clean_name(raw, "display_name")
        return name, name
    if isinstance(raw, Mapping):
        unknown = set(raw) - {"ar", "en"}
        if unknown:
            raise BrandingError(f"display_name has unsupported keys: {sorted(map(str, unknown))}")
        ar = _clean_name(raw["ar"], "display_name['ar']") if raw.get("ar") is not None else None
        en = _clean_name(raw["en"], "display_name['en']") if raw.get("en") is not None else None
        return ar, en
    raise BrandingError("display_name must be text, an {'ar', 'en'} mapping, or None")


def _normalise(branding: Any) -> dict[str, Any]:
    if branding is None:
        return {}
    if isinstance(branding, DocumentBranding):
        return {f.name: getattr(branding, f.name) for f in fields(branding)}
    if not isinstance(branding, Mapping):
        raise BrandingError("branding must be a DocumentBranding, a mapping, or None")
    out: dict[str, Any] = {}
    for key, value in branding.items():
        canonical = _FIELD_ALIASES.get(key) if isinstance(key, str) else None
        if canonical is None:
            raise BrandingError(f"Branding field '{key}' is not tenant-controllable")
        if canonical in out:
            raise BrandingError(f"Branding field '{canonical}' was given more than once")
        out[canonical] = value
    return out


def _flag(values: Mapping[str, Any], key: str, default: bool) -> bool:
    value = values.get(key, default)
    if not isinstance(value, bool):
        raise BrandingError(f"{key} must be true or false")
    return value


def resolve_document_branding(
    branding: DocumentBranding | Mapping[str, Any] | None,
    *,
    entitlements: Mapping[str, Any] | None = None,
) -> ResolvedDocumentBranding:
    """Validate tenant branding and resolve it to safe, final token values."""
    values = _normalise(branding)
    policy = values.get("contrast_policy", "adjust")
    if policy not in _POLICIES:
        raise BrandingError(f"contrast_policy must be one of {list(_POLICIES)}")

    adjustments: list[str] = []
    notes: list[str] = []
    primary_raw = values.get("primary_color") or default_primary()
    primary, note = _fit_colour(primary_raw, "primary colour", MIN_TEXT_CONTRAST, policy)
    if note:
        adjustments.append(note)
    if values.get("accent_color") is None:
        accent = primary
    else:
        accent, note = _fit_colour(values["accent_color"], "accent colour",
                                   MIN_GRAPHIC_CONTRAST, policy)
        if note:
            adjustments.append(note)

    name_ar, name_en = _display_names(values.get("display_name"))

    logo: SanitizedLogo | None = None
    if values.get("logo") not in (None, ""):
        try:
            logo = sanitize_brand_logo(values["logo"])
        except BrandAssetError as exc:
            raise BrandingError(f"logo rejected: {exc}") from exc

    show = _flag(values, "show_powered_by", True)
    if "remove_powered_by" in values:
        remove = _flag(values, "remove_powered_by", False)
        if "show_powered_by" in values and show == remove:
            raise BrandingError("show_powered_by and remove_powered_by contradict each other")
        show = not remove
    entitled = (entitlements or {}).get(ENTITLEMENT_REMOVE_POWERED_BY) is True
    if not show and not entitled:
        notes.append("Powered-by removal ignored: the plan entitlement is not active")
        show = True

    return ResolvedDocumentBranding(
        display_name_ar=name_ar,
        display_name_en=name_en,
        primary_color=primary,
        accent_color=accent,
        logo=logo,
        mono_logo=_flag(values, "mono_logo", False),
        show_powered_by=show,
        adjustments=tuple(adjustments),
        notes=tuple(notes),
    )
