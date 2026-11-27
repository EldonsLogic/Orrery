"""Import path setup, the same fallback the compiler uses (compiler/_deps.py): the Blueprint packages (compiler,
registry, adapter, tokens) are top-level packages under services/blueprint, and the dataset loader and the Phase 1
encoder are imported from the repo root. Reads only; nothing is written anywhere."""
from __future__ import annotations

import sys
from pathlib import Path

STUDIO_DIR = Path(__file__).resolve().parent
REPO = STUDIO_DIR.parents[1]
BLUEPRINT_DIR = REPO / "services" / "blueprint"
STATIC_DIR = STUDIO_DIR / "static"
FONTS_DIR = REPO / "web" / "app" / "public" / "fonts"
FONTS_CSS = REPO / "web" / "app" / "src" / "styles" / "fonts.css"
TOKENS_DIR = REPO / "docs" / "brand" / "tokens"
FIXTURE = BLUEPRINT_DIR / "fixtures" / "trading-distribution.blueprint.json"
REGISTRY_DIR = BLUEPRINT_DIR / "fixtures" / "registry"
MAPPING = REPO / "contracts" / "examples" / "engine-mapping-golden-path.json"

for _p in (REPO, BLUEPRINT_DIR):
    if str(_p) not in sys.path:
        sys.path.append(str(_p))
