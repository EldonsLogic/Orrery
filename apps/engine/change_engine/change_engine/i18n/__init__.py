"""Arabic translation audit and synchronization bridge for change_engine (ERP-006)."""

from __future__ import annotations

from importlib.util import find_spec
import os
from pathlib import Path
import sys


def _has_trading_ar_package() -> bool:
    try:
        return find_spec("components.core.trading_ar") is not None
    except ModuleNotFoundError:
        return False


def _ensure_components_on_path() -> None:
    """Ensure the repository root or bench components parent is importable without hardcoding host paths."""
    if _has_trading_ar_package():
        return

    candidates: list[Path] = []
    env_root = os.environ.get("PLATFORM_COMPONENTS_ROOT")
    if env_root:
        env_path = Path(env_root).expanduser().resolve()
        candidates.extend([env_path, env_path.parent])

    exe = Path(sys.executable).resolve()
    if len(exe.parents) >= 3:
        candidates.append(exe.parents[2])

    candidates.append(Path.cwd().resolve())

    here = Path(__file__).resolve()
    if len(here.parents) >= 6:
        candidates.append(here.parents[5])

    for base in candidates:
        pkg = base / "components" / "core" / "trading_ar" / "loader.py"
        if pkg.is_file():
            base_str = str(base)
            if base_str not in sys.path:
                sys.path.insert(0, base_str)
            return


_ensure_components_on_path()

from .arabic_trading import (  # noqa: E402
    AREA_DOCTYPES,
    TRADING_IN_SCOPE_DOCTYPES,
    TRADING_IN_SCOPE_REPORTS,
    audit_trading_arabic_coverage,
    check_excluded_site_translations,
    check_rtl_support,
    sync_trading_arabic_translations,
)

__all__ = [
    "AREA_DOCTYPES",
    "TRADING_IN_SCOPE_DOCTYPES",
    "TRADING_IN_SCOPE_REPORTS",
    "audit_trading_arabic_coverage",
    "check_excluded_site_translations",
    "check_rtl_support",
    "sync_trading_arabic_translations",
]
