"""ERP-020 live smoke test: a headless engine under its own Compose project.

Starts the stack from docker-compose.headless.yml, creates one synthetic site with the
change engine app, then checks from a sidecar container on the internal network that Desk,
login and website routes are blocked while the allowlisted internal calls work. Tears down
only the project it started (volumes included). Synthetic data only; secrets are generated
in memory and never printed.

    python3 infra/dev/docker/smoke_headless_engine.py [--keep]
"""

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

DOCKER_DIR = Path(__file__).resolve().parent
PROJECT = "erp020-headless-smoke"
SITE = "headless-smoke.localhost"
FILES = ("docker-compose.headless.yml",)
SIDECAR = r'''
import json, sys, urllib.request, urllib.error
cfg = json.load(sys.stdin)
def call(method, path, headers=None, body=None):
    h = {"Host": cfg["site"], "Accept": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request("http://engine:8000" + path, method=method, headers=h,
                                 data=body if body is not None else (b"" if method == "POST" else None))
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")
tok = {"X-Internal-Token": cfg["token"]}
auth = {"Authorization": "token " + cfg["api_key"] + ":" + cfg["api_secret"]}
out = {"blocked": {}, "internal": {}}
for path in ["/", "/app", "/desk", "/login", "/update-password", "/about", "/assets/frappe/js/frappe-web.bundle.js",
             "/files/x.png", "/private/files/x.pdf", "/api/method/login", "/api/method/frappe.auth.get_logged_user",
             "/api/method/frappe.client.get_list?doctype=User", "/api/method/ping/x"]:
    for label, hdr in (("anon", {}), ("token", tok), ("token+auth", {**tok, **auth})):
        s, h, b = call("GET", path, hdr)
        out["blocked"][label + " GET " + path] = {"status": s, "marker": any(
            m in (b + json.dumps(h)).lower() for m in ("frappe", "erpnext", "set-cookie", "sid="))}
s, h, b = call("POST", "/", {**tok, **auth}, b"cmd=frappe.auth.get_logged_user")
out["blocked"]["POST / cmd"] = {"status": s, "marker": "frappe" in (b + json.dumps(h)).lower()}
out["internal"]["collection anon"] = call("GET", "/api/resource/User")[0]
out["internal"]["ping anon"] = call("GET", "/api/method/ping")[0]
s, _, b = call("GET", "/api/resource/User/Administrator", {**tok, **auth})
out["internal"]["resource token+auth"] = {"status": s, "ok": s == 200 and "Administrator" in b}
out["internal"]["resource auth only"] = call("GET", "/api/resource/User/Administrator", auth)[0]
out["internal"]["resource token only"] = call("GET", "/api/resource/User/Administrator", tok)[0]
s, _, b = call("POST", "/api/method/change_engine.api.endpoints.get_runtime_policies", {**tok, **auth})
out["internal"]["adapter method token+auth"] = {"status": s, "not_guard_404": s != 404}
out["internal"]["adapter method auth only"] = call(
    "POST", "/api/method/change_engine.api.endpoints.get_runtime_policies", auth)[0]
print(json.dumps(out))
'''


def compose(env, *args, stdin=None, timeout=900):
    command = ["docker", "compose", "--project-name", PROJECT, "--env-file", os.devnull]
    for name in FILES:
        command += ["-f", str(DOCKER_DIR / name)]
    return subprocess.run(command + list(args), cwd=str(DOCKER_DIR), env=env, input=stdin,
                          capture_output=True, text=True, timeout=timeout, check=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="leave the project running")
    keep = parser.parse_args().keep
    env = os.environ.copy()
    env.update(DB_ROOT_PASSWORD=secrets.token_urlsafe(24), ADMIN_PASSWORD=secrets.token_urlsafe(24),
               SITE_NAME=SITE, ENGINE_INTERNAL_TOKEN=secrets.token_urlsafe(48))
    failures = []

    def check(name, condition):
        print(("PASS " if condition else "FAIL ") + name)
        if not condition:
            failures.append(name)

    try:
        up = compose(env, "up", "-d", "--build")
        if up.returncode != 0:
            print(up.stderr[-2000:], file=sys.stderr)
            return 2
        # The entrypoint installs the mounted app at start; wait until it is importable.
        for _ in range(60):
            if compose(env, "exec", "-T", "engine", "python3", "-c", "import change_engine").returncode == 0:
                break
            time.sleep(5)
        site = compose(env, "exec", "-T", "engine", "sh", "-ec",
                       'bench new-site "$SITE_NAME" --db-host "$DB_HOST" --mariadb-user-host-login-scope=% '
                       '--db-root-password "$DB_ROOT_PASSWORD" --admin-password "$ADMIN_PASSWORD" '
                       '--install-app change_engine')
        if site.returncode != 0:
            print("site creation failed:", (site.stdout + site.stderr)[-2500:], file=sys.stderr)
            return 2
        keys = compose(env, "exec", "-T", "engine", "sh", "-ec",
                       f'bench --site {SITE} execute frappe.core.doctype.user.user.generate_keys '
                       '--args "[\'Administrator\']" >/dev/null && '
                       f'bench --site {SITE} execute frappe.db.get_value --args "[\'User\',\'Administrator\',\'api_key\']"'
                       f' && bench --site {SITE} execute frappe.utils.password.get_decrypted_password '
                       '--args "[\'User\',\'Administrator\',\'api_secret\']"')
        lines = [x.strip().strip("'\"") for x in keys.stdout.splitlines() if x.strip()]
        if keys.returncode != 0 or len(lines) < 2:
            print("could not create API keys", file=sys.stderr)
            return 2
        api_key, api_secret = lines[-2], lines[-1]
        # Wait until gunicorn answers on the internal network.
        image = compose(env, "images", "engine", "--format", "json").stdout
        image = json.loads(image)
        image = (image[0] if isinstance(image, list) else image)
        image_ref = f'{image["Repository"]}:{image["Tag"]}'
        network = f"{PROJECT}_engine_internal"
        payload = json.dumps({"site": SITE, "token": env["ENGINE_INTERNAL_TOKEN"],
                              "api_key": api_key, "api_secret": api_secret})
        run = subprocess.run(["docker", "run", "--rm", "-i", "--network", network, "--entrypoint", "python3",
                              image_ref, "-c", SIDECAR], input=payload, capture_output=True, text=True,
                             timeout=300, check=False)
        if run.returncode != 0:
            print(run.stderr[-1500:], file=sys.stderr)
            return 2
        result = json.loads(run.stdout.strip().splitlines()[-1])

        for name, row in result["blocked"].items():
            check(f"blocked 404 without engine markers: {name} (got {row['status']}, marker={row['marker']})",
                  row["status"] == 404 and not row["marker"])
        i = result["internal"]
        check("record collection blocked without the token", i["collection anon"] == 404)
        check("ping answers without a token", i["ping anon"] == 200)
        check("record API works with token and engine auth", i["resource token+auth"]["ok"])
        check("record API blocked without the token (engine auth alone)", i["resource auth only"] == 404)
        check("record API blocked with the token but no engine auth", i["resource token only"] in (401, 403))
        check("adapter method reaches the engine with token and auth", i["adapter method token+auth"]["not_guard_404"])
        check("adapter method blocked without the token", i["adapter method auth only"] == 404)

        ports = compose(env, "ps", "--format", "json").stdout
        rows = [json.loads(x) for x in ports.splitlines() if x.strip()] if ports.strip().startswith("{") else json.loads(ports or "[]")
        check("no service publishes a host port", all(not r.get("Publishers") or all(
            not p.get("PublishedPort") for p in r["Publishers"]) for r in rows) and bool(rows))
        info = json.loads(subprocess.run(["docker", "network", "inspect", network], capture_output=True,
                                         text=True, check=False).stdout or "[{}]")[0]
        check("engine_internal network is internal", info.get("Internal") is True)
    finally:
        if not keep:
            compose(env, "down", "--volumes", "--remove-orphans")
    print("FAILED: " + ", ".join(failures) if failures else "ALL PASSED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
