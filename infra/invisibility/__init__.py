"""Engine invisibility crawl testing package (QA-016, ADR-0016)."""
from __future__ import annotations

from typing import Any

__all__ = ["Finding", "InvisibilityCrawler", "Marker", "run_crawl"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from . import crawler

        return getattr(crawler, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
