"""Binding, request limits, strict JSON, headers, error shape, the engine hook and the no-files-written rule."""
import http.client
import json
import os
import re

import pytest

from studio_testlib import REPO, start_server

from services.studio import engine as engine_mod
from services.studio.server import MAX_BODY, StudioConfigError, make_server

ENGINE_NAME = re.compile("frap" + "pe|erp" + "next", re.I)


def raw(client, method, path, body=b"", headers=None):
    host, port = client.base.split("//")[1].split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=30)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data, resp


def no_trace(data: bytes):
    text = data.decode("utf-8", "replace")
    assert "Traceback" not in text and 'File "' not in text and "Error:" not in text


def test_refuses_non_loopback_bind_by_default():
    with pytest.raises(StudioConfigError):
        make_server("0.0.0.0", 0)


def test_explicit_flag_allows_a_non_loopback_bind():
    srv = make_server("0.0.0.0", 0, allow_non_loopback=True)
    srv.server_close()


def test_default_bind_is_loopback(server):
    srv, _ = server
    assert srv.server_address[0] == "127.0.0.1"


def test_security_headers_on_api_and_static(client):
    for path in ("/api/state", "/", "/app.js"):
        status, _, headers = client.get(path)
        assert status == 200
        csp = headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp and "script-src 'self'" in csp and "unsafe" not in csp
        assert headers["X-Content-Type-Options"] == "nosniff" and headers["Cache-Control"] == "no-store"
        assert "Python" not in headers.get("Server", "")


def test_invalid_json_is_a_coded_400_without_a_stack_trace(client):
    for body in (b"{bad", b'{"a":1,"a":2}', b'{"x": NaN}', b"[1,2]", b"\xff\xfe"):
        status, data, _ = raw(client, "PUT", "/api/blueprint/branding", body, {"Content-Type": "application/json"})
        assert status == 400, body
        err = json.loads(data)["error"]
        assert err["code"] in ("STUDIO-JSON-INVALID", "STUDIO-JSON-NOT-OBJECT") and err["path"] == "/"
        no_trace(data)


def test_oversize_body_is_refused(client):
    big = b'{"primaryColour":"' + b"a" * (MAX_BODY + 10) + b'"}'
    status, data, _ = raw(client, "PUT", "/api/blueprint/branding", big, {"Content-Type": "application/json"})
    assert status == 413 and json.loads(data)["error"]["code"] == "STUDIO-BODY-TOO-LARGE"


def test_unknown_routes_and_methods_are_coded(client):
    status, body, _ = client.get("/api/nope")
    assert status == 404 and body["error"] == {"code": "STUDIO-ROUTE", "path": "/"}
    status, body, _ = client.get("/../../etc/passwd")
    assert status == 404 and body["error"]["code"] == "STUDIO-ROUTE"
    status, body, _ = client.get("/api/compile")
    assert status == 405 and body["error"]["code"] == "STUDIO-METHOD"
    status, data, _ = raw(client, "DELETE", "/api/state")
    assert status == 405 and json.loads(data)["error"]["code"] == "STUDIO-METHOD"


def test_writes_need_json_content_type_and_a_loopback_host_and_same_origin(client):
    status, data, _ = raw(client, "POST", "/api/reset", b"", {"Content-Type": "text/plain"})
    assert status == 415 and json.loads(data)["error"]["code"] == "STUDIO-CONTENT-TYPE"
    status, data, _ = raw(client, "GET", "/api/state", b"", {"Host": "evil.example"})
    assert status == 421 and json.loads(data)["error"]["code"] == "STUDIO-HOST"
    status, body, _ = client.post("/api/reset", headers={"Origin": "http://evil.example"})
    assert status == 403 and body["error"]["code"] == "STUDIO-ORIGIN"


def test_unexpected_body_keys_on_bodyless_posts_are_refused(client):
    status, body, _ = client.post("/api/compile", {"x": 1})
    assert status == 400 and body["error"] == {"code": "STUDIO-FIELD-UNKNOWN", "path": "/x"}


def test_internal_errors_fail_closed_without_detail(server, monkeypatch):
    srv, client = server

    def boom():
        raise RuntimeError("secret detail")
    monkeypatch.setattr(srv.session, "compile", boom)
    status, data, _ = raw(client, "POST", "/api/compile", b"", {"Content-Type": "application/json"})
    assert status == 500 and json.loads(data) == {"ok": False, "error": {"code": "STUDIO-INTERNAL", "path": "/"}}
    assert b"secret" not in data
    no_trace(data)


def test_engine_name_never_appears_in_any_response(client):
    client.post("/api/apply", {})
    for method, path in (("GET", "/api/state"), ("GET", "/api/export"), ("POST", "/api/compile"), ("POST", "/api/theme"),
                         ("GET", "/api/invoice?market=uae"), ("GET", "/"), ("GET", "/app.js"), ("GET", "/i18n.js")):
        status, body, _ = client.request(method, path, {} if method == "POST" else None)
        text = json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else body.decode("utf-8")
        assert status == 200 and not ENGINE_NAME.search(text), path
    status, body, _ = client.post("/api/apply", {})
    assert not ENGINE_NAME.search(json.dumps(body))


def test_engine_hook_defaults_to_the_fake_and_refuses_bad_specs(monkeypatch):
    monkeypatch.delenv("STUDIO_ENGINE", raising=False)
    assert engine_mod.load_engine().kind == "fake"
    for spec in ("no_such_module_xyz:factory", "services.studio.engine:nope", "not a spec", "os:getcwd"):
        with pytest.raises(engine_mod.EngineUnavailable):
            engine_mod.load_engine(spec)


def test_engine_hook_accepts_an_adapter_harness_factory():
    eng = engine_mod.load_engine("adapter.harness:FakeHarness")
    assert eng.kind == "plugged" and eng.badge() == {"kind": "plugged", "labelKey": "engine.plugged"}


def _tree():
    out = {}
    for d, dirs, files in os.walk(REPO):
        dirs[:] = [x for x in dirs if x not in {".git", "__pycache__", ".pytest_cache", "node_modules"}]
        for f in files:
            p = os.path.join(d, f)
            out[p] = os.stat(p).st_mtime_ns
    return out


def test_state_is_in_memory_and_nothing_is_written():
    before, cwd = _tree(), os.listdir(os.getcwd())
    srv, client = start_server()
    try:
        client.put("/api/blueprint/company", {"tradeName": {"ar": "س", "en": "S"}})
        client.put("/api/blueprint/branding", {"primaryColour": "#9333EA"})
        for path in ("/api/compile", "/api/apply", "/api/theme", "/api/rollback"):
            client.post(path, {})
        client.get("/api/export")
        client.get("/api/invoice?market=egy&lang=ar")
    finally:
        srv.shutdown()
        srv.server_close()
    assert os.listdir(os.getcwd()) == cwd
    assert _tree() == before


def test_each_server_has_its_own_session():
    a, ca = start_server()
    b, cb = start_server()
    try:
        ca.put("/api/blueprint/components", {"id": "core.customer", "enabled": False})
        assert ca.post("/api/compile")[1]["ok"] is False
        assert cb.post("/api/compile")[1]["ok"] is True
    finally:
        for s in (a, b):
            s.shutdown()
            s.server_close()
