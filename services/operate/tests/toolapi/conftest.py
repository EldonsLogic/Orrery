import copy
import json
import sys
from pathlib import Path

import pytest

OPERATE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(OPERATE))
FIXTURE = OPERATE.parents[1] / "services/blueprint/fixtures/trading-distribution.blueprint.json"
MINIMAL = OPERATE.parents[1] / "contracts/examples/blueprint-trading-minimal.json"


@pytest.fixture(scope="session")
def _bp():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def bp(_bp):
    return copy.deepcopy(_bp)


@pytest.fixture
def mini():
    return json.loads(MINIMAL.read_text(encoding="utf-8"))
