"""SEC-004: cross-tenant isolation suite (live, three throwaway tenant sites).

Runs only against a throwaway bench started by
`infra/dev/docker/isolation/run_isolation_suite.py`, which provisions tenant sites A
and B (plus a prefix-twin site T named `<A's site>.sa`) with the ERP-003 script and
passes their details in the JSON file named by SEC004_CONTEXT.

Named `live_*.py` (not `test_*.py`) so offline `pytest`/`unittest discover` never
silently skips live attacks and reports green. When `CI_REQUIRE_LIVE_SEC004=1` is set
without a usable `SEC004_CONTEXT`, setUpClass fails closed instead of skipping.

Known leaks are `unittest.expectedFailure` tracked by plan rows and `docs/risks.md`
(SEC-021 / R-032 for RQ Job prefix matching). The Redis auth leak (INF-015 / R-033) is fixed
and now a plain check. Once a
leak is fixed, unittest reports `unexpected success` as a loud failure so the marker
must be removed. Combined testing with the headless guard (ERP-020) is tracked in SEC-021.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import secrets
import subprocess
import time
import unittest
import uuid
from urllib.parse import quote, urlencode

CONTEXT_ENV = "SEC004_CONTEXT"
REQUIRE_LIVE_ENV = "CI_REQUIRE_LIVE_SEC004"
PROBE = "change_engine.tests.sec004_isolation_probe"
DENIED = (401, 403, 404, 417)
_GRANT_TARGET_RE = re.compile(r"^GRANT\s+.+\s+ON\s+(.+?)\s+TO\s+", re.IGNORECASE)


def _should_skip_live() -> bool:
    if os.environ.get(CONTEXT_ENV):
        return False
    if os.environ.get(REQUIRE_LIVE_ENV) == "1":
        return False  # Fail closed inside setUpClass when CI requires live execution.
    return True


@unittest.skipIf(_should_skip_live(), f"live SEC-004 bench only; set {CONTEXT_ENV}")
class CrossTenantIsolation(unittest.TestCase):
    ctx: dict

    # ---------- harness ----------
    @classmethod
    def setUpClass(cls):
        ctx_path = os.environ.get(CONTEXT_ENV)
        if not ctx_path:
            raise RuntimeError(f"{CONTEXT_ENV} is required when {REQUIRE_LIVE_ENV}=1 (fail closed)")
        with open(ctx_path, encoding="utf-8") as fh:
            cls.ctx = json.load(fh)
        for key in ("a", "b", "twin"):
            if key not in cls.ctx["tenants"]:
                raise RuntimeError(f"context missing tenant '{key}'")
        cls.A, cls.B, cls.T = (cls.ctx["tenants"][k] for k in ("a", "b", "twin"))
        if len({cls.A["site"], cls.B["site"], cls.T["site"]}) != 3:
            raise RuntimeError("tenant sites must differ")
        run = uuid.uuid4().hex[:10]
        cls.mark_a, cls.mark_b = f"SEC004-A-{run}", f"SEC004-B-{run}"
        cls.mark_t = f"SEC004-T-{run}"

        cls.sid_a = cls.login(cls.A)
        cls.sid_b = cls.login(cls.B)
        cls.sid_t = cls.login(cls.T)
        cls.todo_a = cls.probe(cls.A, "create_todo", marker=cls.mark_a)
        cls.todo_b = cls.probe(cls.B, "create_todo", marker=cls.mark_b)
        cls.priv_b = cls.probe(cls.B, "create_file", file_name=f"b-priv-{run}.txt", content=cls.mark_b, is_private=1)
        cls.pub_b = cls.probe(cls.B, "create_file", file_name=f"b-pub-{run}.txt", content=cls.mark_b, is_private=0)
        cls.token_a = cls.probe(cls.A, "make_api_token")
        cls.token_b = cls.probe(cls.B, "make_api_token")
        cls.low_a = cls.probe(
            cls.A,
            "create_low_role_user",
            email=f"sec004-low-a-{run}@example.invalid",
            password=f"Low!{secrets.token_urlsafe(14)}",
        )
        cls.policy_b_id = f"POL_SEC004_B_{run.upper()}"
        cls.probe(cls.B, "register_canary_policy", policy_id=cls.policy_b_id, marker=cls.mark_b)

    @classmethod
    def compose(cls, *args, env=None, timeout=300):
        cmd = ["docker", "compose", "--project-name", cls.ctx["compose_project"], "--env-file", os.devnull]
        for f in cls.ctx["compose_files"]:
            cmd += ["-f", f]
        full_env = dict(os.environ, DB_ROOT_PASSWORD="unused", ADMIN_PASSWORD="unused", **(env or {}))
        return subprocess.run(cmd + list(args), capture_output=True, text=True, env=full_env, timeout=timeout)

    @classmethod
    def bench(cls, site, *args, timeout=300):
        return cls.compose("exec", "-T", "engine", "bench", "--site", site, *args, timeout=timeout)

    @classmethod
    def probe(cls, tenant, fn, **kwargs):
        res = cls.bench(tenant["site"], "execute", f"{PROBE}.{fn}", "--kwargs", repr(kwargs))
        if res.returncode != 0:
            raise RuntimeError(f"probe {fn} on {tenant['site']} failed: {res.stderr[-2000:]}")
        lines = [ln for ln in res.stdout.strip().splitlines() if ln.strip()]
        return json.loads(lines[-1]) if lines else None

    @classmethod
    def http(cls, method, path, host, headers=None, body=None, sid=None, token=None):
        conn = http.client.HTTPConnection("127.0.0.1", int(cls.ctx["engine_port"]), timeout=60)
        hdrs = {"Host": host, "Accept": "application/json"}
        if sid:
            hdrs["Cookie"] = f"sid={sid}"
        if token:
            hdrs["Authorization"] = f"token {token}"
        hdrs.update(headers or {})
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        data = body.encode() if isinstance(body, str) else body
        if data is not None:
            hdrs.setdefault("Content-Length", str(len(data)))
        for k, v in hdrs.items():
            conn.putheader(k, v)
        conn.endheaders(data)
        resp = conn.getresponse()
        payload = resp.read()
        result = resp.status, payload, resp.msg
        conn.close()
        return result

    @classmethod
    def login(cls, tenant):
        body = urlencode({"usr": "Administrator", "pwd": tenant["admin_password"]})
        status, _, headers = cls.http(
            "POST", "/api/method/login", tenant["site"], body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        parts = [p.strip() for c in headers.get_all("Set-Cookie") or [] for p in c.split(";")]
        sid = next((p.split("=", 1)[1] for p in parts if p.startswith("sid=")), "")
        if status != 200 or not sid or sid == "Guest":
            raise RuntimeError(f"login to {tenant['site']} failed: HTTP {status}")
        return sid

    def logged_user(self, host, **auth):
        status, body, _ = self.http("GET", "/api/method/frappe.auth.get_logged_user", host, **auth)
        try:
            return status, json.loads(body).get("message")
        except ValueError:
            return status, None

    def assert_no_leak(self, resp, marker, what):
        status, body, _ = resp
        self.assertNotIn(marker.encode(), body, f"{what}: tenant marker leaked (HTTP {status})")

    # ---------- 1. A's credentials (Admin + low-role) against B's host ----------
    def test_control_a_credentials_work_on_a(self):
        self.assertEqual(self.logged_user(self.A["site"], sid=self.sid_a), (200, "Administrator"))
        self.assertEqual(self.logged_user(self.A["site"], token=self.token_a), (200, "Administrator"))
        status, body, _ = self.http("GET", f"/api/resource/ToDo/{self.todo_a}", self.A["site"], sid=self.sid_a)
        self.assertEqual(status, 200)
        self.assertIn(self.mark_a.encode(), body)

    def test_control_b_reads_own_todo(self):
        status, body, _ = self.http("GET", f"/api/resource/ToDo/{self.todo_b}", self.B["site"], sid=self.sid_b)
        self.assertEqual(status, 200)
        self.assertIn(self.mark_b.encode(), body)

    def test_a_session_cookie_rejected_on_b_host(self):
        status, user = self.logged_user(self.B["site"], sid=self.sid_a)
        self.assertNotEqual(user, "Administrator", f"A's sid authenticated on B (HTTP {status})")
        resp = self.http("GET", f"/api/resource/ToDo/{self.todo_b}", self.B["site"], sid=self.sid_a)
        self.assertIn(resp[0], DENIED)
        self.assert_no_leak(resp, self.mark_b, "A sid on B host")

    def test_a_api_token_rejected_on_b_host(self):
        list_path = "/api/resource/ToDo?fields=%5B%22description%22%5D&limit_page_length=0"
        ctrl_status, ctrl_body, _ = self.http("GET", list_path, self.B["site"], token=self.token_b)
        self.assertEqual(ctrl_status, 200)
        self.assertIn(self.mark_b.encode(), ctrl_body)

        status, user = self.logged_user(self.B["site"], token=self.token_a)
        self.assertNotEqual(user, "Administrator", f"A's API token authenticated on B (HTTP {status})")
        resp = self.http("GET", list_path, self.B["site"], token=self.token_a)
        self.assertIn(resp[0], DENIED)
        self.assert_no_leak(resp, self.mark_b, "A token on B host")

    def test_low_role_principal_cannot_cross_tenants_or_escalate(self):
        """Low-privilege user on A authenticates on A but cannot access B or admin/RQ endpoints."""
        low_tok = self.low_a["token"]
        self.assertEqual(self.logged_user(self.A["site"], token=low_tok), (200, self.low_a["email"]))
        self.assertNotEqual(self.logged_user(self.B["site"], token=low_tok)[1], self.low_a["email"])

        for host, path in (
            (self.B["site"], f"/api/resource/ToDo/{self.todo_b}"),
            (self.B["site"], self.priv_b["file_url"]),
            (self.B["site"], "/api/method/change_engine.api.endpoints.get_runtime_policies"),
            (self.A["site"], "/api/resource/RQ%20Job?fields=%5B%22*%22%5D&order_by=creation%20desc"),
        ):
            with self.subTest(host=host, path=path):
                resp = self.http("GET", path, host, token=low_tok)
                self.assertIn(resp[0], DENIED)
                self.assert_no_leak(resp, self.mark_b, f"low-role {host}{path}")

        reg_body = json.dumps({"policy_data": {"policy_id": "POL_LOW_BAD", "doctype": "ToDo",
                                               "policy_type": "field_constraint", "target_field": "description",
                                               "condition_expr": "description == 'x'", "required_role": "System Manager",
                                               "error_message": "bad"}})
        resp = self.http("POST", "/api/method/change_engine.api.endpoints.register_runtime_policy",
                         self.A["site"], body=reg_body, headers={"Content-Type": "application/json"}, token=low_tok)
        self.assertIn(resp[0], DENIED)

    # ---------- 2. Host / X-Forwarded-Host / site-selector header swaps ----------
    def test_header_swaps_do_not_reach_b(self):
        a, b = self.A["site"], self.B["site"]
        list_path = "/api/resource/ToDo?fields=%5B%22description%22%5D&limit_page_length=0"

        # Positive controls: spoofed site headers on Host: B with B's credentials must still route to B.
        for extra in ({"X-Forwarded-Host": a}, {"X-Frappe-Site-Name": a}):
            for auth in ({"sid": self.sid_b}, {"token": self.token_b}):
                with self.subTest(control=True, headers=extra, auth=list(auth)):
                    st, body, _ = self.http("GET", f"/api/resource/ToDo/{self.todo_b}", b, headers=extra, **auth)
                    self.assertEqual(st, 200)
                    self.assertIn(self.mark_b.encode(), body)

        # Attacks on Host: B with spoofed A headers and A's credentials must fail closed (never 200 on A).
        for extra in ({"X-Forwarded-Host": a}, {"X-Frappe-Site-Name": a}):
            for auth in ({"sid": self.sid_a}, {"token": self.token_a}):
                with self.subTest(host=b, headers=extra, auth=list(auth)):
                    for path in (f"/api/resource/ToDo/{self.todo_b}", list_path):
                        resp = self.http("GET", path, b, headers=extra, **auth)
                        self.assertIn(resp[0], DENIED, f"Host:B + {extra} with A creds not denied: HTTP {resp[0]}")
                        self.assert_no_leak(resp, self.mark_b, f"{b} {extra} {path}")

        # Attacks on Host: A with spoofed B headers must keep routing on A and deny B's doc.
        swaps_on_a = [
            (a, {"X-Forwarded-Host": b}),
            (a, {"X-Frappe-Site-Name": b}),
            (a, {"Forwarded": f"host={b}"}),
            (a, {"X-Forwarded-Server": b, "X-Original-Host": b, "X-Host": b}),
            (f"{a}:80", {"X-Frappe-Site-Name": b}),
        ]
        for host, extra in swaps_on_a:
            for auth in ({"sid": self.sid_a}, {"token": self.token_a}):
                with self.subTest(host=host, headers=extra, auth=list(auth)):
                    doc_resp = self.http("GET", f"/api/resource/ToDo/{self.todo_b}", host, headers=extra, **auth)
                    self.assertIn(doc_resp[0], DENIED)
                    self.assert_no_leak(doc_resp, self.mark_b, f"{host} {extra} doc_b")
                    list_resp = self.http("GET", list_path, host, headers=extra, **auth)
                    self.assert_no_leak(list_resp, self.mark_b, f"{host} {extra} list")

    # ---------- 3. B's site name in path, query or body (CSRF-exempt API token) ----------
    def test_site_name_in_path_query_body_ignored(self):
        a, b, name = self.A["site"], self.B["site"], self.todo_b

        # Positive controls: POST RPCs with token_a actually succeed on A's own ToDo (no CSRF block).
        ctrl_json = self.http("POST", "/api/method/frappe.client.get", a,
                              body=json.dumps({"doctype": "ToDo", "name": self.todo_a}),
                              headers={"Content-Type": "application/json"}, token=self.token_a)
        self.assertEqual(ctrl_json[0], 200)
        self.assertIn(self.mark_a.encode(), ctrl_json[1])

        ctrl_form = self.http("POST", "/", a,
                              body=urlencode({"cmd": "frappe.client.get", "doctype": "ToDo", "name": self.todo_a}),
                              headers={"Content-Type": "application/x-www-form-urlencoded"}, token=self.token_a)
        self.assertEqual(ctrl_form[0], 200)
        self.assertIn(self.mark_a.encode(), ctrl_form[1])

        q = urlencode({"doctype": "ToDo", "name": name, "site": b, "_site": b, "sites": b})
        attempts = [
            ("GET", f"/api/resource/ToDo/{name}?site={b}&_site={b}", None, {}, True),
            ("GET", f"/{b}/api/resource/ToDo/{name}", None, {}, True),
            ("GET", f"/api/method/frappe.client.get?{q}", None, {}, True),
            ("GET", "/api/method/frappe.client.get_list?" + urlencode(
                {"doctype": "ToDo", "fields": '["description"]', "site": b, "limit_page_length": 0}), None, {}, False),
            ("POST", "/api/method/frappe.client.get",
             json.dumps({"doctype": "ToDo", "name": name, "site": b}), {"Content-Type": "application/json"}, True),
            ("POST", "/", urlencode({"cmd": "frappe.client.get", "doctype": "ToDo", "name": name, "site": b}),
             {"Content-Type": "application/x-www-form-urlencoded"}, True),
        ]
        for method, path, body, hdrs, expect_denied in attempts:
            with self.subTest(method=method, path=path):
                resp = self.http(method, path, a, headers=hdrs, body=body, token=self.token_a)
                self.assertNotIn(b"CSRFTokenError", resp[1], f"{method} {path} failed on CSRF instead of isolation")
                if expect_denied:
                    self.assertIn(resp[0], DENIED, f"{method} {path} returned HTTP {resp[0]}")
                self.assert_no_leak(resp, self.mark_b, f"{method} {path}")

    # ---------- 4. B's file and private-file URLs with A's credentials ----------
    def test_control_b_reads_own_private_file(self):
        status, body, _ = self.http("GET", self.priv_b["file_url"], self.B["site"], sid=self.sid_b)
        self.assertEqual(status, 200)
        self.assertIn(self.mark_b.encode(), body)

    def test_b_private_file_unreachable_with_a_session(self):
        url, b_site = self.priv_b["file_url"], self.B["site"]
        fname = url.rsplit("/", 1)[1]
        rel = f"{b_site}/private/files/{fname}"
        tries = [
            (self.B["site"], url), (self.A["site"], url),
            (self.A["site"], "/private/files/" + quote(f"../../../{rel}", safe="")),
            (self.A["site"], f"/private/files/../../../{rel}"),
            (self.A["site"], f"/private/files/%2e%2e/%2e%2e/%2e%2e/{rel}"),
            (self.A["site"], "/files/" + quote(f"../../{rel}", safe="")),
            (self.A["site"], f"/files/../../{rel}"),
            (self.A["site"], f"/api/method/frappe.utils.file_manager.download_file?file_url={quote(url)}"),
        ]
        for host, path in tries:
            for auth in ({"sid": self.sid_a}, {"token": self.token_a}):
                with self.subTest(host=host, path=path, auth=list(auth)):
                    resp = self.http("GET", path, host, **auth)
                    self.assertIn(resp[0], DENIED)
                    self.assert_no_leak(resp, self.mark_b, f"{host}{path}")

    def test_a_file_record_pointing_into_b_store_is_refused(self):
        """A's Administrator registers a File via CSRF-exempt API token traversing into B's private store."""
        evil = f"/private/files/../../../{self.B['site']}/private/files/{self.priv_b['file_url'].rsplit('/', 1)[1]}"
        body = json.dumps({"file_name": "x.txt", "file_url": evil, "is_private": 1})
        post_status, post_body, _ = self.http(
            "POST", "/api/resource/File", self.A["site"], body=body,
            headers={"Content-Type": "application/json"}, token=self.token_a,
        )
        self.assertNotIn(b"CSRFTokenError", post_body, "File POST blocked by CSRF instead of isolation")
        self.assertNotIn(self.mark_b.encode(), post_body)
        created_url = None
        if post_status in (200, 201):
            try:
                created_url = (json.loads(post_body).get("data") or {}).get("file_url")
            except ValueError:
                created_url = None
        else:
            self.assertIn(post_status, (400, 403, 417, 422), f"Unexpected File POST status {post_status}")

        read_paths = [
            evil,
            evil.replace("../", "%2e%2e/"),
            f"/api/method/frappe.utils.file_manager.download_file?file_url={quote(evil)}",
        ]
        if created_url:
            read_paths.append(created_url)
            read_paths.append(f"/api/method/frappe.utils.file_manager.download_file?file_url={quote(created_url)}")
        for path in read_paths:
            with self.subTest(path=path):
                resp = self.http("GET", path, self.A["site"], token=self.token_a)
                self.assertIn(resp[0], DENIED)
                self.assert_no_leak(resp, self.mark_b, path)

    def test_b_public_file_not_served_under_a_host(self):
        ctrl_status, ctrl_body, _ = self.http("GET", self.pub_b["file_url"], self.B["site"])
        self.assertEqual(ctrl_status, 200)
        self.assertIn(self.mark_b.encode(), ctrl_body)

        resp = self.http("GET", self.pub_b["file_url"], self.A["site"], sid=self.sid_a)
        self.assertIn(resp[0], DENIED)
        self.assert_no_leak(resp, self.mark_b, "B public file via A host")

    # ---------- 5. change_engine HTTP endpoints ----------
    def test_change_engine_policy_endpoints_isolate_sites(self):
        """change_engine.api.endpoints.* must never leak B's runtime policies or accept site_id=B."""
        get_ep = "/api/method/change_engine.api.endpoints.get_runtime_policies"
        reg_ep = "/api/method/change_engine.api.endpoints.register_runtime_policy"

        # Positive control: B reads its own canary policy.
        ctrl = self.http("GET", get_ep, self.B["site"], token=self.token_b)
        self.assertEqual(ctrl[0], 200)
        self.assertIn(self.mark_b.encode(), ctrl[1])

        # A reads its own policies: must not contain B's marker.
        own_a = self.http("GET", get_ep, self.A["site"], token=self.token_a)
        self.assertEqual(own_a[0], 200)
        self.assert_no_leak(own_a, self.mark_b, "A get_runtime_policies")

        # Cross-site addressing attempts via site_id / site kwargs or B's host must fail closed.
        for method, host, path, body in (
            ("GET", self.A["site"], f"{get_ep}?site_id={quote(self.B['site'])}", None),
            ("GET", self.A["site"], f"{get_ep}?site={quote(self.B['site'])}", None),
            ("GET", self.B["site"], get_ep, None),
            ("POST", self.A["site"], reg_ep, json.dumps({
                "site_id": self.B["site"],
                "policy_data": {"policy_id": "POL_CROSS_BAD", "doctype": "ToDo", "policy_type": "field_constraint",
                                "target_field": "description", "condition_expr": "description == 'x'",
                                "required_role": "System Manager", "error_message": "cross"},
            })),
        ):
            with self.subTest(method=method, host=host, path=path):
                hdrs = {"Content-Type": "application/json"} if body else {}
                resp = self.http(method, path, host, headers=hdrs, body=body, token=self.token_a)
                self.assertIn(resp[0], DENIED)
                self.assert_no_leak(resp, self.mark_b, f"{method} {host}{path}")

    # ---------- 6. Site config keys & MariaDB grants / symmetric DML denial ----------
    def test_site_configs_have_distinct_non_empty_encryption_keys(self):
        cfg_a = self.probe(self.A, "site_config_summary")
        cfg_b = self.probe(self.B, "site_config_summary")
        self.assertFalse(cfg_a["common_has_encryption_key"], "common_site_config.json must not hold encryption_key")
        self.assertTrue(cfg_a["has_encryption_key"], "site A missing encryption_key")
        self.assertTrue(cfg_b["has_encryption_key"], "site B missing encryption_key")
        self.assertNotEqual(cfg_a["encryption_key_sha256"], cfg_b["encryption_key_sha256"])

    def sql(self, tenant, statement, database=None, password=None):
        args = ["exec", "-T", "-e", "MYSQL_PWD", "mariadb", "mariadb", "-h", "127.0.0.1",
                "-u", tenant["db_user"], "-N", "-B", "-e", statement]
        if database:
            args.insert(-2, "-D")
            args.insert(-2, database)
        return self.compose(*args, env={"MYSQL_PWD": password or tenant["db_password"]})

    def test_control_a_db_user_reads_own_db(self):
        res = self.sql(self.A, f"SELECT description FROM `{self.A['db_name']}`.tabToDo")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn(self.mark_a, res.stdout)

    def test_a_db_user_cannot_reach_b_database(self):
        b_db = self.B["db_name"]
        for stmt, db in (("SELECT 1", b_db), (f"SELECT description FROM `{b_db}`.tabToDo", None),
                         (f"SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='{b_db}'", None)):
            with self.subTest(stmt=stmt, db=db):
                res = self.sql(self.A, stmt, database=db)
                self.assertNotIn(self.mark_b, res.stdout)
                if "information_schema" in stmt:
                    self.assertEqual(res.stdout.strip(), "0")
                else:
                    self.assertNotEqual(res.returncode, 0, "A's DB user reached B's database")
        res = self.sql(self.A, "SHOW DATABASES")
        self.assertEqual(set(res.stdout.split()), {"information_schema", self.A["db_name"]})

        # Symmetric DML denial (errno 1142) across A -> B and B -> A.
        for src, dst in ((self.A, self.B), (self.B, self.A)):
            dst_db = dst["db_name"]
            for op, stmt in (
                ("insert", f"INSERT INTO `{dst_db}`.`tabToDo` (name, description) VALUES ('sec004-bad', 'bad')"),
                ("update", f"UPDATE `{dst_db}`.`tabToDo` SET description='bad' WHERE name='nonexistent'"),
                ("delete", f"DELETE FROM `{dst_db}`.`tabToDo` WHERE name='nonexistent'"),
            ):
                with self.subTest(src=src["site"], dst=dst["site"], op=op):
                    dml = self.sql(src, stmt)
                    self.assertNotEqual(dml.returncode, 0)
                    self.assertIn("1142", dml.stderr, f"expected MariaDB errno 1142: {dml.stderr}")

    def test_a_db_user_has_no_global_privileges(self):
        res = self.sql(self.A, "SHOW GRANTS")
        self.assertEqual(res.returncode, 0, res.stderr)
        expected_target = f"`{self.A['db_name']}`.*"
        grant_lines = [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]
        self.assertTrue(grant_lines)
        for line in grant_lines:
            match = _GRANT_TARGET_RE.match(line)
            self.assertIsNotNone(match, f"unexpected SHOW GRANTS line: {line}")
            target = match.group(1).strip()
            if target == "*.*":
                self.assertTrue(line.startswith("GRANT USAGE ON *.*"), f"global privilege: {line}")
            else:
                self.assertEqual(target, expected_target, f"unexpected non-own/wildcard schema grant: {line}")

        processes = self.sql(self.A, "SELECT COUNT(*) FROM information_schema.PROCESSLIST "
                                     "WHERE USER <> SUBSTRING_INDEX(CURRENT_USER(), '@', 1)")
        self.assertEqual(processes.stdout.split("\n")[0].strip(), "0", "A sees other users' queries")

        lf = self.sql(self.A, "SELECT COALESCE(LOAD_FILE('/etc/passwd'), '')")
        self.assertNotIn("root:", lf.stdout, "A DB user has FILE / LOAD_FILE privilege")

        mysql_user = self.sql(self.A, "SELECT COUNT(*) FROM mysql.user")
        self.assertNotEqual(mysql_user.returncode, 0, "A DB user read mysql.user")

        perf = self.sql(self.A, "SELECT COUNT(*) FROM performance_schema.events_statements_current")
        self.assertTrue(perf.returncode != 0 or perf.stdout.strip() == "0", f"performance_schema exposed: {perf.stdout}")

    def test_a_db_password_does_not_open_b_user(self):
        res = self.sql(self.B, "SELECT 1", password=self.A["db_password"])
        self.assertNotEqual(res.returncode, 0)

    # ---------- 7. Redis cache and queue namespacing ----------
    def test_cache_namespaced_per_site(self):
        key = f"sec004_cache_{uuid.uuid4().hex[:8]}"
        self.probe(self.B, "cache_set", key=key, value=self.mark_b)
        self.assertEqual(self.probe(self.B, "cache_get", key=key)["value"], self.mark_b)  # control
        self.assertIsNone(self.probe(self.A, "cache_get", key=key)["value"])
        raw_b = self.probe(self.B, "cache_key_bytes", key=key)
        self.assertTrue(raw_b.startswith(f"{self.B['db_name']}|"), raw_b)
        self.assertNotEqual(raw_b, self.probe(self.A, "cache_key_bytes", key=key))

    def test_shared_cache_keys_hold_no_tenant_data(self):
        """Unprefixed keys in redis-cache and non-B keys in redis-queue must not carry B's data or DB password.

        Connects with the bench's own authenticated URLs (INF-015), so a refused login fails the test."""
        inspector = (
            "import gzip, json, pickle, redis, sys, zlib\n"
            "key, mark_b, pwd_b, prefixes_json = sys.argv[1:5]\n"
            "prefixes = tuple(json.loads(prefixes_json))\n"
            "r = redis.Redis.from_url(json.load(open('sites/common_site_config.json'))[key])\n"
            "r.ping()\n"
            "leaks = []\n"
            "for k in r.scan_iter(count=200):\n"
            "    ks = k.decode('utf-8', 'replace')\n"
            "    if any(ks.startswith(p) for p in prefixes):\n"
            "        continue\n"
            "    ktype = r.type(k).decode('ascii', 'replace')\n"
            "    blobs = []\n"
            "    if ktype == 'string':\n"
            "        v = r.get(k)\n"
            "        if v is not None: blobs.append(v)\n"
            "    elif ktype == 'hash':\n"
            "        for hk, hv in r.hgetall(k).items(): blobs.extend([hk, hv])\n"
            "    elif ktype == 'list':\n"
            "        blobs.extend(r.lrange(k, 0, 50))\n"
            "    elif ktype == 'set':\n"
            "        blobs.extend(r.smembers(k))\n"
            "    elif ktype == 'zset':\n"
            "        blobs.extend(m for m, _ in r.zrange(k, 0, 50, withscores=True))\n"
            "    for raw in blobs:\n"
            "        texts = [raw.decode('utf-8', 'replace')]\n"
            "        for dec in (zlib.decompress, gzip.decompress):\n"
            "            try:\n"
            "                unp = dec(raw)\n"
            "                texts.append(unp.decode('utf-8', 'replace'))\n"
            "                try: texts.append(repr(pickle.loads(unp)))\n"
            "                except Exception: pass\n"
            "            except Exception: pass\n"
            "        try: texts.append(repr(pickle.loads(raw)))\n"
            "        except Exception: pass\n"
            "        joined = '\\n'.join(texts)\n"
            "        if mark_b in joined or pwd_b in joined:\n"
            "            leaks.append(ks)\n"
            "            break\n"
            "print(json.dumps(leaks))\n"
        )
        cache_prefixes = [f"{t['db_name']}|" for t in (self.A, self.B, self.T)]
        queue_prefixes = [f"{self.B['db_name']}|", f"rq:job:{self.B['site']}::"]
        for key, prefixes in (("redis_cache", cache_prefixes), ("redis_queue", queue_prefixes)):
            with self.subTest(config_key=key):
                res = self.compose(
                    "exec", "-T", "engine", "env/bin/python", "-c", inspector,
                    key, self.mark_b, self.B["db_password"], json.dumps(prefixes),
                )
                self.assertEqual(res.returncode, 0, res.stderr)
                leaks = json.loads(res.stdout.strip().splitlines()[-1])
                self.assertEqual(leaks, [], f"{key} shared/unprefixed keys leaked B data: {leaks}")

    def test_redis_requires_authentication(self):
        """INF-015 / R-033 (fixed): redis-cache and redis-queue (also backing redis_socketio) refuse
        unauthenticated clients with NOAUTH, while the bench's own password URLs still answer.
        Residual: code inside the shared engine or worker holds the password (key-prefix isolation)."""
        checker = (
            "import json, redis, sys\n"
            "service, key = sys.argv[1:3]\n"
            "conf = json.load(open('sites/common_site_config.json'))\n"
            "out = {'authed': redis.Redis.from_url(conf[key], socket_timeout=5).ping()}\n"
            "try:\n"
            "    out['anonymous'] = repr(redis.Redis(host=service, socket_timeout=5).ping())\n"
            "except Exception as exc:\n"
            "    out['anonymous'] = type(exc).__name__\n"
            "print(json.dumps(out))\n"
        )
        for service, key in (("redis-cache", "redis_cache"), ("redis-queue", "redis_queue")):
            with self.subTest(service=service):
                res = self.compose("exec", "-T", "engine", "env/bin/python", "-c", checker, service, key)
                self.assertEqual(res.returncode, 0, res.stderr[-2000:])
                out = json.loads(res.stdout.strip().splitlines()[-1])
                self.assertIs(out["authed"], True, f"{service} did not answer the bench's password (control)")
                self.assertEqual(out["anonymous"], "AuthenticationError",
                                 f"{service} did not refuse an unauthenticated PING with NOAUTH")

    # ---------- 8. Background job context & RQ Job API ----------
    def test_job_enqueued_by_a_runs_in_a_only(self):
        token = uuid.uuid4().hex[:10]
        self.probe(self.A, "enqueue_record_job_site", token=token, attacker_site=self.B["site"])
        ran = self.probe(self.A, "wait_for_job_record", token=token)["value"]
        self.assertIsNotNone(ran, "worker did not run A's job (is the worker service up?)")
        self.assertTrue(ran.startswith(f"sec004_job_{token}|{self.A['site']}|Administrator|"), ran)
        self.assertIsNone(self.probe(self.B, "get_job_record", token=token)["value"])

    def rq_jobs_as(self, tenant, sid):
        path = "/api/resource/RQ%20Job?" + urlencode(
            {"fields": '["*"]', "limit_page_length": 500, "order_by": "creation desc"})
        resp = self.http("GET", path, tenant["site"], sid=sid)
        self.assertEqual(resp[0], 200, "RQ Job list must answer, or the leak checks are vacuous")
        return resp

    def wait_for_rq_job_marker(self, tenant, sid, marker, timeout=30):
        deadline = time.time() + timeout
        last_body = b""
        while time.time() < deadline:
            _, body, _ = self.rq_jobs_as(tenant, sid)
            last_body = body
            if marker.encode() in body:
                return body
            time.sleep(0.5)
        self.fail(f"positive control failed: {tenant['site']} RQ Job list never showed {marker} ({len(last_body)}B)")

    def test_b_jobs_invisible_to_a_rq_job_api(self):
        job_id = self.probe(self.B, "enqueue_marker_job", marker=self.mark_b)
        self.wait_for_rq_job_marker(self.B, self.sid_b, self.mark_b)  # list positive control

        # Single-doc positive control on B before asserting A is denied.
        job_path = f"/api/resource/RQ%20Job/{quote(job_id, safe='')}"
        ctrl = self.http("GET", job_path, self.B["site"], sid=self.sid_b)
        self.assertEqual(ctrl[0], 200)
        self.assertIn(self.mark_b.encode(), ctrl[1])

        self.assert_no_leak(self.rq_jobs_as(self.A, self.sid_a), self.mark_b, "RQ Job list as A")
        resp = self.http("GET", job_path, self.A["site"], sid=self.sid_a)
        self.assertIn(resp[0], DENIED)
        self.assert_no_leak(resp, self.mark_b, "RQ Job by id as A")

    @unittest.expectedFailure
    def test_prefix_twin_jobs_invisible_to_a(self):
        """CONFIRMED LEAK (HIGH when custom domains exist; tracked by SEC-021 & docs/risks.md R-032):
        Frappe's `filter_current_site_jobs` filters with `job_id.startswith(site)` (no `::`), so
        site `acme.com` lists jobs/kwargs/exc_info of `acme.com.sa` (or `acme.co` -> `acme.com`).
        A site-naming prefix rule alone is NOT sufficient (case/FQDN trailing-dot/Punycode IDN
        mismatch, order-dependent DoS, lifecycle reuse); SEC-021 tracks exact `f"{site}::"` fix,
        gateway route blocking (PLT-024), and canonical hostname validation (PLT-003). Once fixed,
        unittest reports `unexpected success` loudly so this marker must be removed."""
        self.probe(self.T, "enqueue_marker_job", marker=self.mark_t)
        self.wait_for_rq_job_marker(self.T, self.sid_t, self.mark_t)  # positive control on T
        self.assert_no_leak(self.rq_jobs_as(self.A, self.sid_a), self.mark_t, "twin-site RQ Job list as A")

    # ---------- 9. Backups and restore paths (DB, site_config, file tarballs) ----------
    def backup(self, tenant):
        res = self.bench(tenant["site"], "backup", "--with-files", timeout=600)
        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
        paths = self.probe(tenant, "site_paths")
        listing = self.compose("exec", "-T", "engine", "ls", "-1", paths["backups"]).stdout.split()
        db_files = sorted(f for f in listing if f.endswith("-database.sql.gz"))
        cfg_files = sorted(f for f in listing if f.endswith("-site_config_backup.json"))
        tar_files = sorted(f for f in listing if f.endswith(("-files.tar", "-private-files.tar")))
        self.assertTrue(db_files, f"no database backup for {tenant['site']}")
        self.assertTrue(cfg_files, f"no site_config_backup.json for {tenant['site']}")
        return paths, listing, {
            "db": f"{paths['backups']}/{db_files[-1]}",
            "cfg": f"{paths['backups']}/{cfg_files[-1]}",
            "tars": [f"{paths['backups']}/{f}" for f in tar_files],
        }

    def test_backups_are_per_site_and_contain_only_own_data(self):
        pa, list_a, files_a = self.backup(self.A)
        pb, list_b, files_b = self.backup(self.B)
        self.assertTrue(pa["backups"].startswith(pa["site_path"] + "/"))
        self.assertTrue(pb["backups"].startswith(pb["site_path"] + "/"))
        self.assertNotEqual(pa["backups"], pb["backups"])
        self.assertFalse(set(list_a) & set(list_b), "backup file names shared between sites")

        for files, own_t, other_t, own_m, other_m in (
            (files_a, self.A, self.B, self.mark_a, self.mark_b),
            (files_b, self.B, self.A, self.mark_b, self.mark_a),
        ):
            db_text = self.compose("exec", "-T", "engine", "sh", "-c", 'zcat "$0"', files["db"]).stdout
            self.assertIn(own_m, db_text)
            self.assertNotIn(other_m, db_text)

            cfg_text = self.compose("exec", "-T", "engine", "cat", files["cfg"]).stdout
            self.assertIn(own_t["db_name"], cfg_text)
            self.assertNotIn(other_t["db_name"], cfg_text)
            self.assertNotIn(other_t["db_password"], cfg_text)

            for tar_path in files["tars"]:
                tar_dump = self.compose("exec", "-T", "engine", "tar", "-xOf", tar_path).stdout
                self.assertNotIn(other_m, tar_dump, f"cross-tenant marker in {tar_path}")

    def test_b_backup_not_downloadable_with_a_session(self):
        _, _, files_b = self.backup(self.B)
        db_b, cfg_b = files_b["db"], files_b["cfg"]
        digest = self.compose("exec", "-T", "engine", "sha256sum", db_b).stdout.split()[0]
        db_fname = db_b.rsplit("/", 1)[1]
        cfg_fname = cfg_b.rsplit("/", 1)[1]

        # Positive control: B downloads its own database backup.
        status, body, _ = self.http("GET", f"/backups/{db_fname}", self.B["site"], sid=self.sid_b)
        self.assertEqual((status, hashlib.sha256(body).hexdigest()), (200, digest))

        rel = f"{self.B['site']}/private/backups/{db_fname}"
        target_fnames = [db_fname, cfg_fname] + [t.rsplit("/", 1)[1] for t in files_b["tars"]]
        tries = [
            (self.A["site"], "/backups/" + quote(f"../../../{rel}", safe="")),
            (self.A["site"], f"/backups/../../../{rel}"),
            (self.A["site"], f"/private/files/{quote('../backups/' + db_fname, safe='')}"),
        ]
        for fname in target_fnames:
            tries.append((self.B["site"], f"/backups/{fname}"))
            tries.append((self.A["site"], f"/backups/{fname}"))

        for host, path in tries:
            for auth in ({}, {"sid": self.sid_a}, {"token": self.token_a}):
                with self.subTest(host=host, path=path, auth=list(auth) or ["anon"]):
                    status, body, _ = self.http("GET", path, host, **auth)
                    self.assertIn(status, DENIED, f"unauthorized backup read HTTP {status}: {host}{path}")
                    self.assertNotEqual(hashlib.sha256(body).hexdigest(), digest, f"B backup served: {host}{path}")
                    self.assertNotIn(self.B["db_password"].encode(), body, f"B db_password leaked: {host}{path}")


if __name__ == "__main__":
    unittest.main()
