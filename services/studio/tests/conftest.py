import sys
from pathlib import Path

import pytest

# `import studio_testlib` (this folder) and `import services.studio` (repo root), wherever pytest is started.
_HERE = Path(__file__).resolve().parent
for _p in (_HERE, _HERE.parents[2]):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import studio_testlib  # noqa: E402


@pytest.fixture(scope="module")
def server():
    srv, client = studio_testlib.start_server()
    yield srv, client
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def client(server):
    """A client on a freshly reset session (fixture Blueprint, new site)."""
    _, c = server
    status, body, _ = c.post("/api/reset")
    assert status == 200 and body["ok"], body
    return c
