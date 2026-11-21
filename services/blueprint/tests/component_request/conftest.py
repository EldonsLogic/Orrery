import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cr_support import build  # noqa: E402


@pytest.fixture
def system():
    return build
