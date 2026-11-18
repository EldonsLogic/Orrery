"""SEC-004: cross-tenant isolation suite (live, two throwaway tenant sites).

Runs only against a throwaway bench started by
`infra/dev/docker/isolation/run_isolation_suite.py`, which provisions tenant sites A
and B (plus a prefix-twin site T named `<A's site>.sa`) with the ERP-003 script and
passes their details in the JSON file named by SEC004_CONTEXT. Without that variable
the whole module is skipped; with it set but unusable, setUpClass fails (fail closed).

Every attack runs with tenant A's strongest principal (Administrator session, API
token, DB user) and asserts that B's data stays unreachable. Each attack has a positive
control (B's own principal does reach the data), so a test cannot pass vacuously.

Known leaks are `unittest.expectedFailure` with the precise defect in the docstring;
they are not fixed here (engine internals are out of scope for SEC-004).

Where these move once built (they stay here as engine-level defence in depth):
- PLT-024 gateway: Host / X-Forwarded-Host / X-Frappe-Site-Name are stripped and the
  site is derived from the authenticated tenant; site names in path, query or body are
  ignored; `/private/files`, `/files`, `/backups` and RQ Job routes are blocked or mapped.
- PLT-005 identity: engine `sid` cookies and API keys never reach clients; the session
  token is tenant-bound and run tokens are checked per tenant (ALP-003, ALP-004).
- Infra (no row yet; request filed in the SEC-004 PR): Redis auth / per-tenant ACLs.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import subprocess
import time
import unittest
import uuid
from urllib.parse import quote, urlencode

CONTEXT_ENV = "SEC004_CONTEXT"
PROBE = "change_engine.tests.sec004_isolation_probe"
DENIED = (401, 403, 404, 417)


@unittest.skipUnless(os.environ.get(CONTEXT_ENV), f"live SEC-004 bench only; set {CONTEXT_ENV}")
class CrossTenantIsolation(unittest.TestCase):
    ctx: dict

    # ---------- harness ----------
    @classmethod
    def setUpClass(cls):
        with open(os.environ[CONTEXT_ENV], encoding="utf-8") as fh:
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
        cls.todo_a = cls.probe(cls.A, "create_todo", marker=cls.mark_a)
        cls.todo_b = cls.probe(cls.B, "create_todo", marker=cls.mark_b)
        cls.priv_b = cls.probe(cls.B, "create_file", file_name=f"b-priv-{run}.txt", content=cls.mark_b, is_private=1)
        cls.pub_b = cls.probe(cls.B, "create_file", file_name=f"b-pub-{run}.txt", content=cls.mark_b, is_private=0)
        cls.token_a = cls.probe(cls.A, "make_api_token")

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
        self.assertNotIn(marker.encode(), body, f"{what}: tenant B marker leaked (HTTP {status})")

    # ---------- 1. A's session cookie and API key against B's host ----------
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
        status, user = self.logged_user(self.B["site"], token=self.token_a)
        self.assertNotEqual(user, "Administrator", f"A's API token authenticated on B (HTTP {status})")
        resp = self.http("GET", "/api/resource/ToDo?fields=%5B%22description%22%5D&limit_page_length=0",
                         self.B["site"], token=self.token_a)
        self.assertIn(resp[0], DENIED)
        self.assert_no_leak(resp, self.mark_b, "A token on B host")

    # ---------- 2. Host / X-Forwarded-Host / site-selector header swaps ----------
    def test_header_swaps_do_not_reach_b(self):
        a, b = self.A["site"], self.B["site"]
        swaps = [
            (a, {"X-Forwarded-Host": b}),
            (a, {"X-Frappe-Site-Name": b}),
            (a, {"Forwarded": f"host={b}"}),
            (a, {"X-Forwarded-Server": b, "X-Original-Host": b, "X-Host": b}),
            (b, {"X-Forwarded-Host": a}),
            (b, {"X-Frappe-Site-Name": a}),
            (f"{a}:80", {"X-Frappe-Site-Name": f"{b}"}),
        ]
        list_path = "/api/resource/ToDo?fields=%5B%22description%22%5D&limit_page_length=0"
        for host, extra in swaps:
            for auth in ({"sid": self.sid_a}, {"token": self.token_a}):
                with self.subTest(host=host, headers=extra, auth=list(auth)):
                    for path in (f"/api/resource/ToDo/{self.todo_b}", list_path):
                        self.assert_no_leak(self.http("GET", path, host, headers=extra, **auth),
                                            self.mark_b, f"{host} {extra} {path}")

    # ---------- 3. B's site name in path, query or body ----------
    def test_site_name_in_path_query_body_ignored(self):
        a, b, name = self.A["site"], self.B["site"], self.todo_b
        q = urlencode({"doctype": "ToDo", "name": name, "site": b, "_site": b, "sites": b})
        attempts = [
            ("GET", f"/api/resource/ToDo/{name}?site={b}&_site={b}", None, {}),
            ("GET", f"/{b}/api/resource/ToDo/{name}", None, {}),
            ("GET", f"/api/method/frappe.client.get?{q}", None, {}),
            ("GET", "/api/method/frappe.client.get_list?" + urlencode(
                {"doctype": "ToDo", "fields": '["description"]', "site": b, "limit_page_length": 0}), None, {}),
            ("POST", "/api/method/frappe.client.get",
             json.dumps({"doctype": "ToDo", "name": name, "site": b}), {"Content-Type": "application/json"}),
            ("POST", "/", urlencode({"cmd": "frappe.client.get", "doctype": "ToDo", "name": name, "site": b}),
             {"Content-Type": "application/x-www-form-urlencoded"}),
        ]
        for method, path, body, hdrs in attempts:
            with self.subTest(path=path):
                self.assert_no_leak(self.http(method, path, a, headers=hdrs, body=body, sid=self.sid_a),
                                    self.mark_b, path)

    # ---------- 4. B's file and private-file URLs with A's session ----------
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
                    self.assert_no_leak(self.http("GET", path, host, **auth), self.mark_b, f"{host}{path}")

    def test_a_file_record_pointing_into_b_store_is_refused(self):
        """A's Administrator registers a File whose URL traverses into B's private store."""
        evil = f"/private/files/../../../{self.B['site']}/private/files/{self.priv_b['file_url'].rsplit('/', 1)[1]}"
        body = json.dumps({"file_name": "x.txt", "file_url": evil, "is_private": 1})
        self.http("POST", "/api/resource/File", self.A["site"], body=body,
                  headers={"Content-Type": "application/json"}, sid=self.sid_a)
        for path in (evil, evil.replace("../", "%2e%2e/")):
            with self.subTest(path=path):
                self.assert_no_leak(self.http("GET", path, self.A["site"], sid=self.sid_a), self.mark_b, path)

    def test_b_public_file_not_served_under_a_host(self):
        resp = self.http("GET", self.pub_b["file_url"], self.A["site"], sid=self.sid_a)
        self.assert_no_leak(resp, self.mark_b, "B public file via A host")

    # ---------- 5. A's DB user against B's database ----------
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

    def test_a_db_user_has_no_global_privileges(self):
        res = self.sql(self.A, "SHOW GRANTS")
        self.assertEqual(res.returncode, 0, res.stderr)
        for line in res.stdout.splitlines():
            if " ON *.* " in line:
                self.assertTrue(line.startswith("GRANT USAGE ON *.*"), f"global privilege: {line}")
        processes = self.sql(self.A, "SELECT COUNT(*) FROM information_schema.PROCESSLIST "
                                     "WHERE USER <> SUBSTRING_INDEX(CURRENT_USER(), '@', 1)")
        self.assertEqual(processes.stdout.split("\n")[0].strip(), "0", "A sees other users' queries")

    def test_a_db_password_does_not_open_b_user(self):
        res = self.sql(self.B, "SELECT 1", password=self.A["db_password"])
        self.assertNotEqual(res.returncode, 0)

    # ---------- 6. Redis cache and queue namespacing ----------
    def test_cache_namespaced_per_site(self):
        key = f"sec004_cache_{uuid.uuid4().hex[:8]}"
        self.probe(self.B, "cache_set", key=key, value=self.mark_b)
        self.assertEqual(self.probe(self.B, "cache_get", key=key)["value"], self.mark_b)  # control
        self.assertIsNone(self.probe(self.A, "cache_get", key=key)["value"])
        raw_b = self.probe(self.B, "cache_key_bytes", key=key)
        self.assertTrue(raw_b.startswith(f"{self.B['db_name']}|"), raw_b)
        self.assertNotEqual(raw_b, self.probe(self.A, "cache_key_bytes", key=key))

    def test_shared_cache_keys_hold_no_tenant_data(self):
        """Keys outside every site prefix (shared=True) must not carry B's data."""
        prefixes = tuple(f"{t['db_name']}|" for t in (self.A, self.B, self.T))
        keys = self.redis("redis-cache", "--scan").split()
        shared = [k for k in keys if not k.startswith(prefixes)]
        for key in shared:
            with self.subTest(key=key):
                dump = self.redis("redis-cache", "--no-raw", "DUMP", key)
                self.assertNotIn(self.mark_b, dump)
                self.assertNotIn(self.B["db_password"], dump)

    def redis(self, service, *args):
        res = self.compose("exec", "-T", service, "redis-cli", *args)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    @unittest.expectedFailure
    def test_redis_requires_authentication(self):
        """LEAK (defence in depth, MEDIUM): redis-cache and redis-queue accept unauthenticated
        clients. Site isolation in Redis is only a key-prefix convention (`<db_name>|`), so any
        code that reaches the network (a compromised worker, a server script escape, a sidecar)
        reads every tenant's cache and sessions and can push RQ jobs with `site=<any tenant>`.
        Fix (infra, not this PR): requirepass or per-bench ACL users, network policy."""
        for service in ("redis-cache", "redis-queue"):
            res = self.compose("exec", "-T", "engine", "python", "-c",
                               f"import redis;print(redis.Redis(host='{service}').ping())")
            self.assertNotIn("True", res.stdout, f"{service} answered an unauthenticated PING")

    # ---------- 7. Background job context ----------
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

    def test_b_jobs_invisible_to_a_rq_job_api(self):
        job_id = self.probe(self.B, "enqueue_marker_job", marker=self.mark_b)
        time.sleep(3)
        _, body, _ = self.rq_jobs_as(self.B, self.sid_b)  # control
        self.assertIn(self.mark_b.encode(), body)
        self.assert_no_leak(self.rq_jobs_as(self.A, self.sid_a), self.mark_b, "RQ Job list as A")
        resp = self.http("GET", f"/api/resource/RQ%20Job/{quote(job_id, safe='')}", self.A["site"], sid=self.sid_a)
        self.assertIn(resp[0], DENIED)
        self.assert_no_leak(resp, self.mark_b, "RQ Job by id as A")

    @unittest.expectedFailure
    def test_prefix_twin_jobs_invisible_to_a(self):
        """LEAK (HIGH when custom domains exist): RQ Job list filters jobs with
        `job_id.startswith(site)` (frappe/core/doctype/rq_job/rq_job.py filter_current_site_jobs,
        no `::` separator), so a System Manager on site `acme.com` lists the jobs, full
        `arguments` (kwargs) and `exc_info` of site `acme.com.sa`. Fetch by id uses the correct
        `site::` check. Mitigation until fixed upstream: no site name may be a prefix of another
        (tenant ids under one fixed suffix), and the gateway blocks RQ Job routes (PLT-024)."""
        self.probe(self.T, "enqueue_marker_job", marker=self.mark_t)
        time.sleep(3)
        self.assert_no_leak(self.rq_jobs_as(self.A, self.sid_a), self.mark_t, "twin-site RQ Job list as A")

    # ---------- 8. Backups and restore paths ----------
    def backup(self, tenant):
        res = self.bench(tenant["site"], "backup", timeout=600)
        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
        paths = self.probe(tenant, "site_paths")
        listing = self.compose("exec", "-T", "engine", "ls", "-1", paths["backups"]).stdout.split()
        db_files = sorted(f for f in listing if f.endswith("-database.sql.gz"))
        self.assertTrue(db_files, f"no database backup for {tenant['site']}")
        return paths, listing, f"{paths['backups']}/{db_files[-1]}"

    def test_backups_are_per_site_and_contain_only_own_data(self):
        pa, list_a, db_a = self.backup(self.A)
        pb, list_b, db_b = self.backup(self.B)
        self.assertTrue(pa["backups"].startswith(pa["site_path"] + "/"))
        self.assertTrue(pb["backups"].startswith(pb["site_path"] + "/"))
        self.assertNotEqual(pa["backups"], pb["backups"])
        self.assertFalse(set(list_a) & set(list_b), "backup file names shared between sites")
        for path, own, other in ((db_a, self.mark_a, self.mark_b), (db_b, self.mark_b, self.mark_a)):
            text = self.compose("exec", "-T", "engine", "sh", "-c", 'zcat "$0"', path).stdout
            self.assertIn(own, text)
            self.assertNotIn(other, text)

    def test_b_backup_not_downloadable_with_a_session(self):
        _, _, db_b = self.backup(self.B)
        digest = self.compose("exec", "-T", "engine", "sha256sum", db_b).stdout.split()[0]
        fname = db_b.rsplit("/", 1)[1]
        status, body, _ = self.http("GET", f"/backups/{fname}", self.B["site"], sid=self.sid_b)  # control
        self.assertEqual((status, hashlib.sha256(body).hexdigest()), (200, digest))
        rel = f"{self.B['site']}/private/backups/{fname}"
        tries = [(self.B["site"], f"/backups/{fname}"), (self.A["site"], f"/backups/{fname}"),
                 (self.A["site"], "/backups/" + quote(f"../../../{rel}", safe="")),
                 (self.A["site"], f"/backups/../../../{rel}"),
                 (self.A["site"], f"/private/files/{quote('../backups/' + fname, safe='')}")]
        for host, path in tries:
            with self.subTest(host=host, path=path):
                status, body, _ = self.http("GET", path, host, sid=self.sid_a)
                self.assertNotEqual(hashlib.sha256(body).hexdigest(), digest, f"B backup served: {host}{path}")


if __name__ == "__main__":
    unittest.main()
