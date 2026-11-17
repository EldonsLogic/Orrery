"""services/blueprint/tokens: BRD-004 token resolver (pure, deterministic). Layers per docs/brand/12-tenant-theming.md section 1.

    from tokens import resolve_tokens, layer_from_css
    result = resolve_tokens(base, product_theme, blueprint["branding"], "system", algo_version=1, tenant_slug="al-waha")

Layers: 0 base tokens, 1 product theme (light or dark), 2 tenant overrides (primary, optional accent), 3 user preference (theme mode only).
The result holds the resolved token sets for both themes, the layer-2 CSS (`:root[data-tenant="slug"]`, plus the same under
`prefers-color-scheme: dark` and `[data-theme="dark"]`, to be loaded after layer 1), the `themeAlgo` used, and findings: structured
refusals, adjustments, warnings and notices with stable codes (no English; text comes from i18n later).

Finding codes (severity in brackets)
  Colours (refusal): TKN-COLOUR-INVALID-HEX, -GREY, -NEAR-CRIMSON, -TOO-LIGHT, -TOO-DARK, -NO-AA, -DARK-GREY, -DARK-NEAR-TEXT,
    -REJECTED (unrecognised derive rejection, fail closed); TKN-ACCENT-GREY, -NEAR-CRIMSON, -TOO-LIGHT, -NO-AA, -TOO-CLOSE-PRIMARY;
    TKN-CONTRAST-INTERNAL.
  Structure (refusal): TKN-TOKEN-LOCKED, -DERIVED-ONLY, -UNKNOWN, -BAD-NAME; TKN-FIELD-LOCKED, -UNKNOWN, -TYPE, -CONFLICT;
    TKN-SLUG-INVALID, -MISSING; TKN-NAME-INVALID; TKN-PREF-FIELD, -MODE; TKN-ALGO-UNSUPPORTED, -INVALID; TKN-RESOLVED-INVALID;
    TKN-BASE-MISMATCH; TKN-LAYER-INVALID; TKN-OUTPUT-REJECTED.
  Adjustments: TKN-ADJ-LIGHT-PRIMARY-DARKENED, -DARK-PRIMARY-DERIVED, -LIGHT-ACCENT-DARKENED, -DARK-ACCENT-DERIVED,
    -ACCENT-FALLBACK-TEXT, -OTHER.   Warnings: TKN-WARN-NEAR-STATUS, -OTHER.   Notice: TKN-NOTICE-ALGO-PINNED.

Behaviour notes
  * Any colour refusal drops ALL tenant colour tokens (the tenant gets exactly the product theme). A refused locked-token override,
    unknown field or bad display name is dropped and logged; valid colours in the same branding are still applied.
  * A stored `resolved` block plus `themeAlgo` is used verbatim (never re-derived), so a later algorithm change cannot restyle a
    tenant; an explicit save should drop `resolved`, resolve again, and persist `ResolvedTokens.to_store`.
  * The brand tools are loaded by path from docs/brand/tools (brand_tools.py); nothing is imported from sys.path.

Open questions (also to be added to docs/open-questions.md by a founder lane; this package may not edit docs)
  1. Names: the Blueprint contract says primaryColour/accentColour, logo.onLight/onDark and has no themeAlgo or resolved fields
     (additionalProperties false); 12-tenant-theming.md section 10 sketches primary/accent, logo.light/dark, themeAlgo, resolved.
     The resolver accepts both colour spellings and `themeAlgo`/`resolved`; the contract needs a change before they validate.
  2. Two guardrail implementations disagree: validator rule 10 (BP-BRAND-001/002) searches HSL lightness; derive_tenant_theme uses
     OKLCH and stricter rules (grey, Crimson, 0.20 shift limit, 100 pairs). A Blueprint can validate yet be refused here. Which wins?
  3. Runtime dependency on docs/brand/tools and tokens/tokens.json (themelib reads v1 colours at call time). The validator's rule
     "docs are never read at runtime" suggests vendoring the tools into the service with a drift test; not done here.
  4. derive measures contrast against the v1 base colours. The resolver refuses (TKN-BASE-MISMATCH) when the merged layers carry
     different background, surface, text, success, warning or danger values, instead of re-deriving against them.
  5. "Focus ring colour" in the may-override table has no token of its own; it is taken to follow --color-primary.
  6. Slug rule: the docs say lowercase letters, digits and hyphen. Assumed 1 to 63 characters, no leading or trailing hyphen.
  7. Display name "1 to 40 characters" is counted in Unicode code points; control characters (Cc, Cs) and blank text are refused.
  8. Layer 1 (tokens.proposed.*) is PROPOSED, not accepted; the resolver takes any token set, so acceptance changes data, not code.
  9. A tenant accent that is absent leaves --color-accent alone unless derive falls back to the text colour (then it is overridden).
 10. `tokens` (direct overrides) is not a Blueprint field; it exists only as the channel through which attempts are refused and logged.
 11. A stored `resolved` block is not re-checked against primaryColour; callers must drop it when the colour changes (explicit save).
 12. Where the slug comes from (tenant record vs Blueprint) is not specified; it is a keyword argument.
 13. User preference persistence and the theme engine are BRD-005; this layer only validates the mode and emits data-theme.
"""
from .brand_tools import BrandToolsUnavailable
from .layers import layer_from_css, merge, validate_layer
from .resolver import TENANT_TOKENS, ResolvedTokens, default_algorithms, resolve_tokens

__all__ = ["resolve_tokens", "ResolvedTokens", "TENANT_TOKENS", "default_algorithms", "layer_from_css", "merge", "validate_layer", "BrandToolsUnavailable"]
