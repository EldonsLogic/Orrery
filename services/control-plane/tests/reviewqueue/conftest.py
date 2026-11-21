import pytest
from rq_support import World


@pytest.fixture
def w():
    return World()
