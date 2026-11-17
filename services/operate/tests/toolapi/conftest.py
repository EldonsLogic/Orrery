import copy
import json
import sys
from pathlib import Path

import pytest

OPERATE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(OPERATE))
FIXTURE = OPERATE.parents[1] / "services/blueprint/fixtures/trading-distribution.blueprint.json"


@pytest.fixture(scope="session")
def _bp():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def bp(_bp):
    return copy.deepcopy(_bp)
