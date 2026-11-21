"""Bilingual admin labels. Flags carry i18n keys, never text; the catalogues come
from the i18n layer. `missing` lists keys a registry still needs in each language,
so a CI check can fail when Arabic or English is absent."""

LANGS = ("en", "ar")


def missing(registry, catalogues: dict) -> list:
    out = []
    for d in registry:
        for lang in LANGS:
            cat = catalogues.get(lang, {})
            for k in (d.label_key, d.description_key):
                v = cat.get(k)
                if not isinstance(v, str) or not v.strip():
                    out.append((lang, k))
    return out


def label(registry, catalogues: dict, key: str, lang: str) -> str:
    """Admin label, the i18n key when the string is missing, or empty for an unknown flag (never raises)."""
    d = registry.get(key)
    if d is None or lang not in LANGS:
        return ""  # never echo a hostile or unknown key
    v = catalogues.get(lang, {}).get(d.label_key)
    return v if isinstance(v, str) and v.strip() else d.label_key
