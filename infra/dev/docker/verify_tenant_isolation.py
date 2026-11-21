#!/usr/bin/env python3
"""SEC-004: Lightweight live two-tenant smoke verifier for an already-running Compose bench.

For the comprehensive 3-site attack suite (including workers, RQ Job prefix twin, files,
Redis, change_engine endpoints, and backups), use `infra/dev/docker/isolation/run_isolation_suite.py`
and `apps/engine/change_engine/change_engine/tests/live_sec_004_bench_attacks.py`.

Verifies five runtime isolation boundaries between two synthetic `.localhost` sites:
  1. Site config credential & key isolation (distinct non-empty `db_name`, `db_password`, `encryption_key`).
  2. MariaDB credential isolation (symmetrical `errno 1142` denial across SELECT/COUNT/INSERT/UPDATE/DELETE).
  3. Frappe ORM isolation (canary ToDo written in site A is invisible in site B and vice versa).
  4. Redis cache prefix isolation (canary key written in site A is invisible in site B and vice versa).
  5. HTTP Host / token swap isolation for Administrator AND a synthetic low-role principal (HTTP 401/403).

All probe records, low-role users, and cache keys are synthetic and cleaned up automatically.
Never logs or prints DB passwords, encryption keys, or API secrets.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple


DOCKER_DIR = Path(__file__).resolve().parent
DEFAULT_COMPOSE_FILE = DOCKER_DIR / "docker-compose.dev.yml"
SAFE_PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
SAFE_SITE_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*\.localhost$")


def validate_project_name(project: str) -> str:
    if not isinstance(project, str) or not SAFE_PROJECT_RE.fullmatch(project):
        raise ValueError(f"Invalid compose project name: {project!r}")
    return project


def validate_site_name(site: str) -> str:
    if not isinstance(site, str) or not SAFE_SITE_RE.fullmatch(site):
        raise ValueError(f"Invalid synthetic .localhost site name: {site!r}")
    return site


def redact_secrets(text: str, secret_values: List[str]) -> str:
    out = text
    for sec in secret_values:
        if sec:
            out = out.replace(sec, "<REDACTED>")
    return out


def compose_exec(
    project: str,
    compose_file: Path,
    service: str,
    *args: str,
    input_text: Optional[str] = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("DB_ROOT_PASSWORD", "verification-only")
    env.setdefault("ADMIN_PASSWORD", "verification-only")
    return subprocess.run(
        [
            "docker", "compose",
            "--project-name", project,
            "--env-file", os.devnull,
            "-f", str(compose_file),
            "exec", "-T", service, *args,
        ],
        cwd=str(compose_file.parent),
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def host_http_get(port: int, host_header: str, path: str, headers: Optional[Dict[str, str]] = None, timeout: float = 15.0) -> Tuple[int, str]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    req_headers = {"Host": host_header, "Connection": "close"}
    if headers:
        req_headers.update(headers)
    try:
        conn.request("GET", path, headers=req_headers)
        resp = conn.getresponse()
        return resp.status, resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"
    finally:
        try:
            conn.close()
        except Exception:
            pass


def check_site_configs_and_mariadb(
    project: str,
    compose_file: Path,
    site_a: str,
    site_b: str,
) -> Dict[str, Any]:
    """Check distinct site_config secrets/keys and symmetric MariaDB 1142 denial."""
    py = (
        "import json, os, pymysql, sys\n"
        "sites_dir = os.path.expanduser('~/frappe-bench/sites')\n"
        "common_path = os.path.join(sites_dir, 'common_site_config.json')\n"
        "common = json.load(open(common_path)) if os.path.exists(common_path) else {}\n"
        "a = json.load(open(os.path.join(sites_dir, sys.argv[1], 'site_config.json')))\n"
        "b = json.load(open(os.path.join(sites_dir, sys.argv[2], 'site_config.json')))\n"
        "enc_a, enc_b = a.get('encryption_key'), b.get('encryption_key')\n"
        "config_checks = {\n"
        "    'distinct_db_name': bool(a.get('db_name')) and bool(b.get('db_name')) and a.get('db_name') != b.get('db_name'),\n"
        "    'distinct_db_password': bool(a.get('db_password')) and bool(b.get('db_password')) and a.get('db_password') != b.get('db_password'),\n"
        "    'no_shared_encryption_key': (not common.get('encryption_key')) and bool(enc_a) and bool(enc_b) and enc_a != enc_b,\n"
        "}\n"
        "def probe(src, dst):\n"
        "    db_host = src.get('db_host') or common.get('db_host') or 'mariadb'\n"
        "    db_port = int(src.get('db_port') or common.get('db_port') or 3306)\n"
        "    conn = pymysql.connect(host=db_host, port=db_port, user=src['db_name'], password=src['db_password'], database=src['db_name'])\n"
        "    out = {}\n"
        "    stmts = {\n"
        "        'select': f\"SELECT name FROM `{dst['db_name']}`.`tabUser` LIMIT 1\",\n"
        "        'count': f\"SELECT COUNT(*) FROM `{dst['db_name']}`.`tabToDo`\",\n"
        "        'insert': f\"INSERT INTO `{dst['db_name']}`.`tabToDo` (name, description) VALUES ('sec004-bad', 'bad')\",\n"
        "        'update': f\"UPDATE `{dst['db_name']}`.`tabToDo` SET description='bad' WHERE name='nonexistent'\",\n"
        "        'delete': f\"DELETE FROM `{dst['db_name']}`.`tabToDo` WHERE name='nonexistent'\",\n"
        "    }\n"
        "    try:\n"
        "        with conn.cursor() as cur:\n"
        "            for op, sql in stmts.items():\n"
        "                try:\n"
        "                    cur.execute(sql)\n"
        "                    out[op] = {'denied': False, 'errno': None}\n"
        "                except Exception as exc:\n"
        "                    code = exc.args[0] if exc.args else None\n"
        "                    out[op] = {'denied': code == 1142, 'errno': code}\n"
        "    finally:\n"
        "        conn.close()\n"
        "    return out\n"
        "res = {\n"
        "    'config_checks': config_checks,\n"
        "    'a_to_b': probe(a, b),\n"
        "    'b_to_a': probe(b, a),\n"
        "}\n"
        "print('__ISOLATION_DB__' + json.dumps(res))\n"
    )
    proc = compose_exec(project, compose_file, "engine", "env/bin/python", "-c", py, site_a, site_b)
    if proc.returncode != 0:
        raise RuntimeError(f"MariaDB/config isolation check failed: {proc.stderr or proc.stdout}")
    marker = "__ISOLATION_DB__"
    idx = proc.stdout.rfind(marker)
    if idx == -1:
        raise RuntimeError("Missing MariaDB isolation output marker")
    data = json.loads(proc.stdout[idx + len(marker):].strip())
    all_cfg_ok = all(data["config_checks"].values())
    all_db_ok = all(v["denied"] for direction in ("a_to_b", "b_to_a") for v in data[direction].values())
    data["passed"] = bool(all_cfg_ok and all_db_ok)
    return data


def probe_runtime_orm_cache_and_tokens(
    project: str,
    compose_file: Path,
    site_a: str,
    site_b: str,
    canary_a: str,
    canary_b: str,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Create temporary canary ToDo + Redis keys + Admin and low-role tokens, verify runtime isolation."""
    py = (
        "import json, os, secrets, sys, frappe\n"
        "from frappe.core.doctype.user.user import generate_keys\n"
        "site_a, site_b, canary_a, canary_b = sys.argv[1:5]\n"
        "os.chdir(os.path.expanduser('~/frappe-bench/sites'))\n"
        "created = {}\n"
        "tokens = {}\n"
        "low_users = {}\n"
        "for site, canary in ((site_a, canary_a), (site_b, canary_b)):\n"
        "    frappe.init(site=site, sites_path='.')\n"
        "    frappe.connect()\n"
        "    try:\n"
        "        doc = frappe.get_doc({'doctype': 'ToDo', 'description': canary, 'status': 'Open'}).insert(ignore_permissions=True)\n"
        "        frappe.cache().set_value('sec004_canary_cache', canary, expires_in_sec=120)\n"
        "        res = generate_keys('Administrator')\n"
        "        api_key = frappe.db.get_value('User', 'Administrator', 'api_key')\n"
        "        tokens[site] = f\"{api_key}:{res['api_secret']}\"\n"
        "        if site == site_a:\n"
        "            low_email = f'sec004-low-{secrets.token_hex(4)}@example.invalid'\n"
        "            frappe.get_doc({'doctype': 'User', 'email': low_email, 'first_name': 'Sec004 Low', 'enabled': 1, 'user_type': 'Website User', 'send_welcome_email': 0, 'new_password': f'Low!{secrets.token_urlsafe(12)}'}).insert(ignore_permissions=True)\n"
        "            lres = generate_keys(low_email)\n"
        "            lkey = frappe.db.get_value('User', low_email, 'api_key')\n"
        "            tokens['low_a'] = f\"{lkey}:{lres['api_secret']}\"\n"
        "            low_users[site] = low_email\n"
        "        frappe.db.commit()\n"
        "        created[site] = doc.name\n"
        "    finally:\n"
        "        frappe.destroy()\n"
        "cross = {}\n"
        "for viewer, other, other_canary, self_canary in (\n"
        "    (site_a, site_b, canary_b, canary_a),\n"
        "    (site_b, site_a, canary_a, canary_b),\n"
        "):\n"
        "    frappe.init(site=viewer, sites_path='.')\n"
        "    frappe.connect()\n"
        "    try:\n"
        "        orm_leak = frappe.get_all('ToDo', filters={'description': other_canary}, pluck='name')\n"
        "        cache_val = frappe.cache().get_value('sec004_canary_cache')\n"
        "        cross[viewer] = {\n"
        "            'orm_isolated': len(orm_leak) == 0,\n"
        "            'cache_isolated': cache_val == self_canary and cache_val != other_canary,\n"
        "        }\n"
        "    finally:\n"
        "        frappe.destroy()\n"
        "print('__ISOLATION_RT__' + json.dumps({'created': created, 'low_users': low_users, 'cross': cross, 'tokens': tokens}))\n"
    )
    proc = compose_exec(project, compose_file, "engine", "env/bin/python", "-c", py, site_a, site_b, canary_a, canary_b)
    if proc.returncode != 0:
        raise RuntimeError(f"Runtime ORM/cache isolation check failed: {proc.stderr or proc.stdout}")
    marker = "__ISOLATION_RT__"
    idx = proc.stdout.rfind(marker)
    if idx == -1:
        raise RuntimeError("Missing runtime isolation output marker")
    payload = json.loads(proc.stdout[idx + len(marker):].strip())
    tokens = payload.pop("tokens")
    payload["passed"] = all(
        v["orm_isolated"] and v["cache_isolated"] for v in payload["cross"].values()
    )
    return payload, tokens


def cleanup_runtime_canaries(
    project: str,
    compose_file: Path,
    created: Dict[str, str],
    low_users: Optional[Dict[str, str]] = None,
) -> None:
    py = (
        "import json, os, sys, frappe\n"
        "os.chdir(os.path.expanduser('~/frappe-bench/sites'))\n"
        "data = json.loads(sys.stdin.read())\n"
        "created = data.get('created', {})\n"
        "low_users = data.get('low_users', {})\n"
        "for site, name in created.items():\n"
        "    frappe.init(site=site, sites_path='.')\n"
        "    frappe.connect()\n"
        "    try:\n"
        "        if frappe.db.exists('ToDo', name):\n"
        "            frappe.delete_doc('ToDo', name, force=True, ignore_permissions=True)\n"
        "        low_email = low_users.get(site)\n"
        "        if low_email and frappe.db.exists('User', low_email):\n"
        "            frappe.delete_doc('User', low_email, force=True, ignore_permissions=True)\n"
        "        frappe.cache().delete_value('sec004_canary_cache')\n"
        "        frappe.db.commit()\n"
        "    finally:\n"
        "        frappe.destroy()\n"
    )
    compose_exec(
        project,
        compose_file,
        "engine",
        "env/bin/python",
        "-c",
        py,
        input_text=json.dumps({"created": created, "low_users": low_users or {}}),
        timeout=60,
    )


def verify_live_isolation(
    *,
    project: str,
    compose_file: Path,
    engine_port: int,
    site_a: str,
    site_b: str,
) -> Dict[str, Any]:
    validate_project_name(project)
    validate_site_name(site_a)
    validate_site_name(site_b)
    if site_a == site_b:
        raise ValueError("site_a and site_b must be distinct sites.")

    canary_a = f"sec004-canary-a-{secrets.token_hex(6)}"
    canary_b = f"sec004-canary-b-{secrets.token_hex(6)}"

    db_report = check_site_configs_and_mariadb(project, compose_file, site_a, site_b)
    rt_report, tokens = probe_runtime_orm_cache_and_tokens(
        project, compose_file, site_a, site_b, canary_a, canary_b
    )
    low_users = rt_report.get("low_users") or {}
    low_token = tokens.get("low_a", "")
    low_email = low_users.get(site_a, "")
    try:
        doc_a = rt_report["created"][site_a]
        doc_b = rt_report["created"][site_b]

        # Own token + own Host must return 200 and contain own canary.
        st_a_ok, body_a_ok = host_http_get(
            engine_port, site_a, f"/api/resource/ToDo/{doc_a}",
            headers={"Authorization": f"token {tokens[site_a]}"},
        )
        st_b_ok, body_b_ok = host_http_get(
            engine_port, site_b, f"/api/resource/ToDo/{doc_b}",
            headers={"Authorization": f"token {tokens[site_b]}"},
        )

        # Swapped tokens / Host spoofing must fail closed (401/403) and never leak the other tenant's canary.
        st_a_on_b, body_a_on_b = host_http_get(
            engine_port, site_b, f"/api/resource/ToDo/{doc_b}",
            headers={"Authorization": f"token {tokens[site_a]}"},
        )
        st_b_on_a, body_b_on_a = host_http_get(
            engine_port, site_a, f"/api/resource/ToDo/{doc_a}",
            headers={"Authorization": f"token {tokens[site_b]}"},
        )
        st_spoof_doc, body_spoof_doc = host_http_get(
            engine_port, site_b, f"/api/resource/ToDo/{doc_a}",
            headers={"Authorization": f"token {tokens[site_b]}"},
        )

        # Low-role principal: authenticates on A, rejected on B's Host and B's canary ToDo.
        st_low_a_ok, body_low_a_ok = host_http_get(
            engine_port, site_a, "/api/method/frappe.auth.get_logged_user",
            headers={"Authorization": f"token {low_token}"},
        )
        st_low_a_on_b, body_low_a_on_b = host_http_get(
            engine_port, site_b, f"/api/resource/ToDo/{doc_b}",
            headers={"Authorization": f"token {low_token}"},
        )
    finally:
        cleanup_runtime_canaries(project, compose_file, rt_report["created"], low_users)

    http_checks = {
        "own_a_200": st_a_ok == 200 and canary_a in body_a_ok,
        "own_b_200": st_b_ok == 200 and canary_b in body_b_ok,
        "token_a_rejected_on_host_b": st_a_on_b in (401, 403) and canary_b not in body_a_on_b,
        "token_b_rejected_on_host_a": st_b_on_a in (401, 403) and canary_a not in body_b_on_a,
        "host_b_cannot_fetch_doc_a": st_spoof_doc in (403, 404) and canary_a not in body_spoof_doc,
        "low_role_a_200": st_low_a_ok == 200 and bool(low_email) and low_email in body_low_a_ok,
        "low_role_a_rejected_on_host_b": st_low_a_on_b in (401, 403) and canary_b not in body_low_a_on_b,
    }
    http_report = {
        "passed": all(http_checks.values()),
        "checks": http_checks,
        "statuses": {
            "own_a": st_a_ok,
            "own_b": st_b_ok,
            "token_a_on_b": st_a_on_b,
            "token_b_on_a": st_b_on_a,
            "doc_a_on_host_b": st_spoof_doc,
            "low_role_a": st_low_a_ok,
            "low_role_a_on_b": st_low_a_on_b,
        },
    }

    overall_passed = bool(db_report["passed"] and rt_report["passed"] and http_report["passed"])
    return {
        "plan_id": "SEC-004",
        "compose_project": project,
        "site_a": site_a,
        "site_b": site_b,
        "passed": overall_passed,
        "mariadb_and_config": db_report,
        "runtime_orm_and_cache": {"passed": rt_report["passed"], "cross": rt_report["cross"]},
        "http_host_and_token": http_report,
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="SEC-004 live cross-tenant isolation verifier.")
    ap.add_argument("--compose-project", default=os.environ.get("COMPOSE_PROJECT_NAME", ""))
    ap.add_argument("--compose-file", default=str(DEFAULT_COMPOSE_FILE))
    ap.add_argument("--engine-port", type=int, default=int(os.environ.get("ENGINE_PORT", "8000")))
    ap.add_argument("--site-a", required=True)
    ap.add_argument("--site-b", required=True)
    return ap.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        report = verify_live_isolation(
            project=args.compose_project,
            compose_file=Path(args.compose_file),
            engine_port=args.engine_port,
            site_a=args.site_a,
            site_b=args.site_b,
        )
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Verification error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
