"""Bilingual label catalogue (`labels.json`, en and ar, same keys). Quote line labels come from services/discovery/quote."""
import json
from pathlib import Path

_FILE = Path(__file__).with_name("labels.json")


def labels(locale: str) -> dict:
    if locale not in ("en", "ar"):
        raise ValueError("locale")
    return dict(json.loads(_FILE.read_text(encoding="utf-8"))[locale])
