import json

from fixture_registry import REPO
from validator.theme_surfaces import SURFACES


def test_copies_match_tokens_json():
    tokens = json.loads((REPO / "docs/brand/tokens/tokens.json").read_text(encoding="utf-8"))["color"]
    for theme in ("light", "dark"):
        for name in ("surface", "background"):
            assert SURFACES[theme][name].upper() == tokens[theme][name]["hex"].upper(), (theme, name)
