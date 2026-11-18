import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "blueprint"))
BASE = json.loads((ROOT / "components" / "core" / "trading_ar" / "manifest.json").read_text(encoding="utf-8"))


@pytest.fixture
def make(tmp_path):
    """make(manifest_edit=None, test_body=...) -> candidate folder with manifest.json and tests/test_ok.py."""
    def _make(edit=None, test_body="def test_ok():\n    assert 1 + 1 == 2\n"):
        m = copy.deepcopy(BASE)
        m["tests"] = [{"id": "unit_ok", "kind": "unit", "path": "tests/test_ok.py", "blocking": True}]
        if edit:
            edit(m)
        d = tmp_path / "cand"
        (d / "tests").mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
        (d / "tests" / "test_ok.py").write_text(test_body, encoding="utf-8")
        return d
    return _make


def codes(rep):
    return {f.code for f in rep.findings}
