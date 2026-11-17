"""Base Arabic and RTL translation pack for the in-scope trading and distribution scope (ERP-006)."""

from .loader import (
    EXPECTED_EXCLUDED_COUNT,
    EXPECTED_TRANSLATABLE_COUNT,
    apply_trading_ar_translations,
    is_excluded_source,
    load_pack,
    load_translations,
)

__all__ = [
    "EXPECTED_EXCLUDED_COUNT",
    "EXPECTED_TRANSLATABLE_COUNT",
    "apply_trading_ar_translations",
    "is_excluded_source",
    "load_pack",
    "load_translations",
]
