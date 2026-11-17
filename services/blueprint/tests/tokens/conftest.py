import sys
from pathlib import Path

import pytest

BLUEPRINT = Path(__file__).resolve().parents[2]
REPO = BLUEPRINT.parents[1]
# `import tokens` (services/blueprint/tokens) and `import tkn_helpers` (this folder).
sys.path.insert(0, str(BLUEPRINT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tokens import layer_from_css  # noqa: E402

TOKENS_DIR = REPO / "docs" / "brand" / "tokens"


@pytest.fixture(scope="session")
def base():
    return layer_from_css((TOKENS_DIR / "tokens.css").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def product():
    return layer_from_css((TOKENS_DIR / "tokens.proposed.css").read_text(encoding="utf-8"))


@pytest.fixture
def run(base, product):
    """resolve_tokens with the generated layers pre-filled."""
    from tokens import resolve_tokens

    def _run(branding=None, pref=None, slug="acme", algo=1, **kw):
        return resolve_tokens(base, product, branding, pref, algo_version=algo, tenant_slug=slug, **kw)

    return _run
