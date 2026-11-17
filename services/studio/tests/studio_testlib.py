"""Test helpers: start the Studio server on an ephemeral loopback port in a thread and talk to it with urllib."""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[1]
REPO = STUDIO.parents[1]
STATIC = STUDIO / "static"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from services.studio.server import make_server  # noqa: E402

FIXTURE = REPO / "services" / "blueprint" / "fixtures" / "trading-distribution.blueprint.json"
DATA = REPO / "services" / "datasets" / "data"


class Client:
    def __init__(self, base: str):
        self.base = base

    def request(self, method: str, path: str, body=None, raw: bytes | None = None, headers: dict | None = None):
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
        hdrs = {"Content-Type": "application/json"} if method in ("PUT", "POST") else {}
        hdrs.update(headers or {})
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status, payload, rh = resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as exc:
            status, payload, rh = exc.code, exc.read(), exc.headers
        ctype = rh.get("Content-Type", "")
        parsed = json.loads(payload.decode("utf-8")) if ctype.startswith("application/json") else payload
        return status, parsed, rh

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def put(self, path, body=None, **kw):
        return self.request("PUT", path, body if body is not None else {}, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body, **kw)


def start_server():
    srv = make_server("127.0.0.1", 0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    host, port = srv.server_address[:2]
    return srv, Client(f"http://{host}:{port}")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
