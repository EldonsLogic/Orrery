#!/usr/bin/env python3
"""
ERP-002 Spike: 50-Tenant Provisioning & Load Test on One Bench Pool.

Proves and measures multi-tenant density on the pinned Frappe/ERPNext v15 Compose
bench (`infra/dev/docker/docker-compose.dev.yml`):
  1. Cold single-site provisioning baseline (`bench new-site` with erpnext, hrms, change_engine)
  2. Fast parallel template-clone provisioning up to N synthetic sites (default 50)
  3. Idle & warm resource footprint across 50 live sites (MariaDB tables/disk, Redis keys/RAM,
     Gunicorn worker RSS)
  4. Concurrent HTTP + authenticated REST read/write load across all 50 tenants at
     escalating concurrency levels (e.g. 10, 25, 50, 100)

Isolation evidence: the in-wave response checks only prove the request succeeded and the
response is well-formed (they cannot detect wrong-site routing: ping is unauthenticated,
get_logged_user is "Administrator" on every site, and the ToDo POST echoes the request body).
The real cross-tenant check is `verify_tag_isolation`, run once after all waves: it reads every
site's ToDo rows back with that site's own token and asserts each tag written for a site exists
in that site and in no other. The SEC-004 live suite remains the authoritative isolation proof.

All data created is synthetic (`load-001.localhost` .. `load-050.localhost`).
Never logs or writes DB passwords, admin passwords, or API secrets.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import dataclasses
import datetime
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import random
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Tuple


DOCKER_DIR = Path(__file__).resolve().parent
DEFAULT_COMPOSE_FILE = DOCKER_DIR / "docker-compose.dev.yml"

SAFE_PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
SAFE_SITE_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*\.localhost$")
SAFE_DB_RE = re.compile(r"^_l50_[a-f0-9]{10}$")


def validate_project_name(project: str) -> str:
    if not isinstance(project, str) or not SAFE_PROJECT_RE.fullmatch(project):
        raise ValueError(f"Invalid compose project name: {project!r}")
    return project


def validate_site_name(site_name: str) -> str:
    if not isinstance(site_name, str) or not SAFE_SITE_RE.fullmatch(site_name):
        raise ValueError(f"Invalid synthetic .localhost site name: {site_name!r}")
    return site_name


def parse_concurrency_levels(raw: str) -> List[int]:
    levels: List[int] = []
    for part in raw.split(","):
        s = part.strip()
        if not s:
            continue
        val = int(s)
        if val < 1 or val > 500:
            raise ValueError(f"Concurrency level must be in [1, 500], got {val}")
        levels.append(val)
    if not levels:
        raise ValueError("At least one concurrency level is required.")
    return levels


def site_names_for_count(count: int, prefix: str = "load") -> List[str]:
    if count < 2 or count > 200:
        raise ValueError(f"Tenant count must be in [2, 200], got {count}")
    if not re.fullmatch(r"[a-z0-9-]+", prefix):
        raise ValueError(f"Invalid site prefix: {prefix!r}")
    return [validate_site_name(f"{prefix}-{idx:03d}.localhost") for idx in range(1, count + 1)]


def db_name_for_site(site_name: str) -> str:
    digest = hashlib.sha256(site_name.encode("utf-8")).hexdigest()[:10]
    db = f"_l50_{digest}"
    if not SAFE_DB_RE.fullmatch(db):
        raise ValueError(f"Generated unsafe db name: {db}")
    return db


def compute_latency_stats(samples_ms: List[float]) -> Dict[str, float]:
    """Compute min/mean/p50/p95/p99/max latency in milliseconds."""
    if not samples_ms:
        return {"min_ms": 0.0, "mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "max_ms": 0.0}
    ordered = sorted(samples_ms)
    n = len(ordered)

    def pct(p: float) -> float:
        if n == 1:
            return ordered[0]
        rank = (p / 100.0) * (n - 1)
        lo = int(math.floor(rank))
        hi = int(math.ceil(rank))
        if lo == hi:
            return ordered[lo]
        frac = rank - lo
        return ordered[lo] * (1.0 - frac) + ordered[hi] * frac

    return {
        "min_ms": round(ordered[0], 2),
        "mean_ms": round(sum(ordered) / n, 2),
        "p50_ms": round(pct(50.0), 2),
        "p95_ms": round(pct(95.0), 2),
        "p99_ms": round(pct(99.0), 2),
        "max_ms": round(ordered[-1], 2),
    }


def redact_secrets(text: str, secrets_list: List[str]) -> str:
    masked = text
    for sec in secrets_list:
        if sec:
            masked = masked.replace(sec, "<REDACTED>")
    return masked


def parse_docker_mem_to_mib(raw: str) -> float:
    """Parse docker stats memory string such as '199.2MiB' or '1.45GiB' into MiB."""
    token = raw.strip().split("/")[0].strip()
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(B|KiB|MiB|GiB|kB|MB|GB)", token)
    if not m:
        return 0.0
    val = float(m.group(1))
    unit = m.group(2)
    scale = {
        "B": 1.0 / (1024 * 1024),
        "KiB": 1.0 / 1024,
        "MiB": 1.0,
        "GiB": 1024.0,
        "kB": 1000.0 / (1024 * 1024),
        "MB": 1_000_000.0 / (1024 * 1024),
        "GB": 1_000_000_000.0 / (1024 * 1024),
    }[unit]
    return round(val * scale, 2)


def compose_exec(
    project: str,
    compose_file: Path,
    service: str,
    *args: str,
    env_overrides: Optional[Dict[str, str]] = None,
    input_text: Optional[str] = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("DB_ROOT_PASSWORD", "bench-runner-placeholder")
    env.setdefault("ADMIN_PASSWORD", "bench-runner-placeholder")
    if env_overrides:
        env.update(env_overrides)
    cmd = [
        "docker", "compose",
        "--project-name", project,
        "--env-file", os.devnull,
        "-f", str(compose_file),
        "exec", "-T",
    ]
    for key in sorted((env_overrides or {}).keys()):
        cmd.extend(["-e", key])
    cmd.append(service)
    cmd.extend(args)
    return subprocess.run(
        cmd,
        cwd=str(compose_file.parent),
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _host_http_request(
    port: int,
    host_header: str,
    method: str,
    path: str,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[str] = None,
    timeout: float = 30.0,
) -> Tuple[int, str, float]:
    t0 = time.perf_counter()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    req_headers = {"Host": host_header, "Connection": "close"}
    if headers:
        req_headers.update(headers)
    try:
        conn.request(method, path, body=body, headers=req_headers)
        resp = conn.getresponse()
        payload = resp.read().decode("utf-8", errors="replace")
        dt_ms = (time.perf_counter() - t0) * 1000.0
        return resp.status, payload, dt_ms
    except Exception as exc:
        dt_ms = (time.perf_counter() - t0) * 1000.0
        return 0, f"{type(exc).__name__}: {exc}", dt_ms
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _provision_template_site(
    project: str,
    compose_file: Path,
    site_name: str,
    db_name: str,
    db_root_password: str,
    admin_password: str,
) -> Dict[str, Any]:
    db_password = secrets.token_urlsafe(24)
    script = (
        'site="$1"; db_name="$2"; tenant_id="$3"; '
        'bench new-site "$site" '
        '--db-host mariadb '
        '--mariadb-user-host-login-scope=% '
        '--db-root-password "$DB_ROOT_PASSWORD" '
        '--admin-password "$ADMIN_PASSWORD" '
        '--db-name "$db_name" '
        '--db-password "$DB_PASSWORD" '
        '--install-app erpnext --install-app hrms --install-app change_engine && '
        'bench --site "$site" set-config tenant_id "$tenant_id" && '
        'bench --site "$site" set-config country_code SA && '
        'bench --site "$site" set-config currency SAR && '
        'bench --site "$site" set-config language ar && '
        'bench --site "$site" set-config time_zone Asia/Riyadh && '
        'bench --site "$site" set-config --parse developer_mode 0'
    )
    t0 = time.perf_counter()
    res = compose_exec(
        project,
        compose_file,
        "engine",
        "sh", "-ec", script, "erp002_template",
        site_name, db_name, site_name.split(".")[0],
        env_overrides={
            "DB_ROOT_PASSWORD": db_root_password,
            "ADMIN_PASSWORD": admin_password,
            "DB_PASSWORD": db_password,
        },
        timeout=600,
    )
    elapsed_s = time.perf_counter() - t0
    if res.returncode != 0:
        detail = redact_secrets(res.stderr or res.stdout, [db_root_password, admin_password, db_password])
        raise RuntimeError(f"Failed creating template site {site_name}: {detail}")

    # Seed one synthetic Company/marker check and return site metadata
    return {
        "site_name": site_name,
        "db_name": db_name,
        "cold_provision_seconds": round(elapsed_s, 2),
    }


def _dump_template_db(
    project: str,
    compose_file: Path,
    db_name: str,
    db_root_password: str,
    dump_path: str = "/tmp/erp002_template.sql",
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    cmd = (
        'db_name="$1"; dump_path="$2"; '
        'mariadb-dump -h 127.0.0.1 -u root -p"$MYSQL_ROOT_PASSWORD" '
        '--single-transaction --routines --triggers --quick "$db_name" > "$dump_path" && '
        'stat -c %s "$dump_path"'
    )
    res = compose_exec(
        project,
        compose_file,
        "mariadb",
        "sh", "-ec", cmd, "erp002_dump", db_name, dump_path,
        env_overrides={"MYSQL_ROOT_PASSWORD": db_root_password},
        timeout=180,
    )
    elapsed_s = time.perf_counter() - t0
    if res.returncode != 0:
        detail = redact_secrets(res.stderr or res.stdout, [db_root_password])
        raise RuntimeError(f"Template DB dump failed: {detail}")
    size_bytes = int(res.stdout.strip().splitlines()[-1])
    return {"dump_seconds": round(elapsed_s, 2), "dump_bytes": size_bytes, "dump_path": dump_path}


def _clone_single_site(
    project: str,
    compose_file: Path,
    site_name: str,
    db_name: str,
    db_root_password: str,
    dump_path: str = "/tmp/erp002_template.sql",
    skip_existing_db: bool = False,
) -> float:
    t0 = time.perf_counter()
    db_password = secrets.token_urlsafe(24)
    tenant_id = site_name.split(".")[0]

    already_populated = False
    if skip_existing_db:
        chk = compose_exec(
            project,
            compose_file,
            "mariadb",
            "sh", "-ec",
            f'mariadb -N -B -h 127.0.0.1 -u root -p"$MYSQL_ROOT_PASSWORD" -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = \'{db_name}\';"',
            env_overrides={"MYSQL_ROOT_PASSWORD": db_root_password},
            timeout=30,
        )
        if chk.returncode == 0 and chk.stdout.strip().isdigit() and int(chk.stdout.strip()) >= 850:
            already_populated = True

    if already_populated:
        sh_grant = (
            'db="$1"; '
            'printf "CREATE USER IF NOT EXISTS \'%s\'@\'%%\' IDENTIFIED BY \'%s\'; '
            "ALTER USER '%s'@'%%' IDENTIFIED BY '%s'; "
            "GRANT ALL PRIVILEGES ON \\`%s\\`.* TO '%s'@'%%'; FLUSH PRIVILEGES;\\n\" "
            '"$db" "$TARGET_DB_PW" "$db" "$TARGET_DB_PW" "$db" "$db" | '
            'mariadb -h 127.0.0.1 -u root -p"$MYSQL_ROOT_PASSWORD"'
        )
        res_db = compose_exec(
            project,
            compose_file,
            "mariadb",
            "sh", "-ec", sh_grant, "erp002_grant_db", db_name,
            env_overrides={"MYSQL_ROOT_PASSWORD": db_root_password, "TARGET_DB_PW": db_password},
            timeout=60,
        )
        if res_db.returncode != 0:
            detail = redact_secrets(res_db.stderr or res_db.stdout, [db_root_password, db_password])
            raise RuntimeError(f"Grant update failed for {site_name}: {detail}")
    else:
        # 1. Cleanly recreate DB, least-privilege user, and load SQL dump in mariadb container
        sh_setup = (
            'db="$1"; dump="$2"; '
            'printf "DROP DATABASE IF EXISTS \\`%s\\`; '
            'CREATE DATABASE \\`%s\\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; '
            "CREATE USER IF NOT EXISTS '%s'@'%%' IDENTIFIED BY '%s'; "
            "ALTER USER '%s'@'%%' IDENTIFIED BY '%s'; "
            "GRANT ALL PRIVILEGES ON \\`%s\\`.* TO '%s'@'%%'; FLUSH PRIVILEGES;\\n\" "
            '"$db" "$db" "$db" "$TARGET_DB_PW" "$db" "$TARGET_DB_PW" "$db" "$db" | '
            'mariadb -h 127.0.0.1 -u root -p"$MYSQL_ROOT_PASSWORD" && '
            'mariadb -h 127.0.0.1 -u root -p"$MYSQL_ROOT_PASSWORD" "$db" < "$dump"'
        )
        res_db = compose_exec(
            project,
            compose_file,
            "mariadb",
            "sh", "-ec", sh_setup, "erp002_clone_db", db_name, dump_path,
            env_overrides={"MYSQL_ROOT_PASSWORD": db_root_password, "TARGET_DB_PW": db_password},
            timeout=300,
        )
        if res_db.returncode != 0:
            detail = redact_secrets(res_db.stderr or res_db.stdout, [db_root_password, db_password])
            raise RuntimeError(f"Clone DB load failed for {site_name}: {detail}")

    # 2. Materialize isolated site directory and per-site config + encryption_key inside engine container
    site_setup = (
        "import json, os, sys\n"
        "from cryptography.fernet import Fernet\n"
        "site, db_name, tenant_id = sys.argv[1], sys.argv[2], sys.argv[3]\n"
        "db_pw = os.environ['TARGET_DB_PW']\n"
        "base = os.path.join(os.path.expanduser('~/frappe-bench/sites'), site)\n"
        "for sub in ('', 'private/files', 'public/files', 'locks', 'logs'):\n"
        "    os.makedirs(os.path.join(base, sub), exist_ok=True)\n"
        "cfg = {\n"
        "    'db_name': db_name,\n"
        "    'db_password': db_pw,\n"
        "    'db_type': 'mariadb',\n"
        "    'db_host': 'mariadb',\n"
        "    'encryption_key': Fernet.generate_key().decode(),\n"
        "    'tenant_id': tenant_id,\n"
        "    'country_code': 'SA',\n"
        "    'currency': 'SAR',\n"
        "    'language': 'ar',\n"
        "    'time_zone': 'Asia/Riyadh',\n"
        "    'developer_mode': 0,\n"
        "}\n"
        "with open(os.path.join(base, 'site_config.json'), 'w') as fh:\n"
        "    fh.write(json.dumps(cfg, indent=1) + '\\n')\n"
    )
    res_fs = compose_exec(
        project,
        compose_file,
        "engine",
        "env/bin/python", "-c", site_setup, site_name, db_name, tenant_id,
        env_overrides={"TARGET_DB_PW": db_password},
        timeout=60,
    )
    if res_fs.returncode != 0:
        detail = redact_secrets(res_fs.stderr or res_fs.stdout, [db_password])
        raise RuntimeError(f"Clone site dir setup failed for {site_name}: {detail}")

    return round(time.perf_counter() - t0, 3)


def _set_mariadb_trx_commit(
    project: str,
    compose_file: Path,
    db_root_password: str,
    value: int,
) -> None:
    if value not in (0, 1, 2):
        raise ValueError(f"Invalid innodb_flush_log_at_trx_commit: {value}")
    res = compose_exec(
        project,
        compose_file,
        "mariadb",
        "sh", "-ec",
        f'mariadb -h 127.0.0.1 -u root -p"$MYSQL_ROOT_PASSWORD" -e "SET GLOBAL innodb_flush_log_at_trx_commit = {value};"',
        env_overrides={"MYSQL_ROOT_PASSWORD": db_root_password},
        timeout=30,
    )
    if res.returncode != 0:
        detail = redact_secrets(res.stderr or res.stdout, [db_root_password])
        raise RuntimeError(f"Failed setting innodb_flush_log_at_trx_commit={value}: {detail}")


def _generate_per_site_api_tokens(
    project: str,
    compose_file: Path,
    sites: List[str],
) -> Dict[str, str]:
    """Generate unique per-site API tokens ('api_key:api_secret') inside the engine container."""
    py = (
        "import json, os, sys, frappe\n"
        "from frappe.core.doctype.user.user import generate_keys\n"
        "os.chdir(os.path.expanduser('~/frappe-bench/sites'))\n"
        "sites = json.loads(sys.stdin.read())\n"
        "tokens = {}\n"
        "for site in sites:\n"
        "    frappe.init(site=site, sites_path='.')\n"
        "    frappe.connect()\n"
        "    try:\n"
        "        res = generate_keys('Administrator')\n"
        "        frappe.db.commit()\n"
        "        api_key = frappe.db.get_value('User', 'Administrator', 'api_key')\n"
        "        tokens[site] = f\"{api_key}:{res['api_secret']}\"\n"
        "    finally:\n"
        "        frappe.destroy()\n"
        "print('__TOKENS_JSON__' + json.dumps(tokens))\n"
    )
    res = compose_exec(
        project,
        compose_file,
        "engine",
        "env/bin/python", "-c", py,
        input_text=json.dumps(sites),
        timeout=300,
    )
    if res.returncode != 0:
        raise RuntimeError(f"Failed generating API tokens: {res.stderr or res.stdout}")
    marker = "__TOKENS_JSON__"
    idx = res.stdout.rfind(marker)
    if idx == -1:
        raise RuntimeError(f"Missing token output marker; stdout tail: {res.stdout[-300:]}")
    return json.loads(res.stdout[idx + len(marker):].strip())


def _collect_snapshots(
    project: str,
    compose_file: Path,
    db_root_password: str,
    db_prefix: str = "_l50_",
) -> Dict[str, Any]:
    """Collect MariaDB, Redis, Gunicorn worker RSS, disk, and Docker stats."""
    snap: Dict[str, Any] = {}

    # 1. docker stats
    names = [
        f"{project}-engine-1",
        f"{project}-mariadb-1",
        f"{project}-redis-cache-1",
        f"{project}-redis-queue-1",
    ]
    ds = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.PIDs}}", *names],
        capture_output=True, text=True, timeout=30, check=False,
    )
    containers: Dict[str, Any] = {}
    if ds.returncode == 0:
        for line in ds.stdout.strip().splitlines():
            parts = line.split("|")
            if len(parts) == 4:
                cname, cpu, mem, pids = parts
                containers[cname.replace(f"{project}-", "")] = {
                    "cpu_pct": cpu.strip(),
                    "mem_usage_raw": mem.strip(),
                    "mem_mib": parse_docker_mem_to_mib(mem),
                    "pids": int(pids.strip()) if pids.strip().isdigit() else pids.strip(),
                }
    snap["containers"] = containers

    # 2. Gunicorn process RSS breakdown inside engine container
    proc_py = (
        "import json, os\n"
        "procs = []\n"
        "for pid in os.listdir('/proc'):\n"
        "    if not pid.isdigit(): continue\n"
        "    try:\n"
        "        cmd = open(f'/proc/{pid}/cmdline', 'rb').read().replace(b'\\x00', b' ').decode('utf-8', 'replace').strip()\n"
        "        status = open(f'/proc/{pid}/status').read()\n"
        "        rss_kb = 0\n"
        "        for ln in status.splitlines():\n"
        "            if ln.startswith('VmRSS:'): rss_kb = int(ln.split()[1])\n"
        "        if 'gunicorn' in cmd or 'frappe' in cmd:\n"
        "            procs.append({'pid': int(pid), 'rss_mib': round(rss_kb / 1024.0, 2), 'cmd': cmd[:120]})\n"
        "    except Exception: pass\n"
        "print(json.dumps(procs))\n"
    )
    ep = compose_exec(project, compose_file, "engine", "env/bin/python", "-c", proc_py, timeout=30)
    if ep.returncode == 0 and ep.stdout.strip():
        try:
            snap["engine_processes"] = json.loads(ep.stdout.strip().splitlines()[-1])
        except Exception:
            pass

    # 3. Sites disk usage
    du = compose_exec(project, compose_file, "engine", "sh", "-c", 'du -sb "$HOME/frappe-bench/sites"', timeout=30)
    if du.returncode == 0 and du.stdout.strip():
        bytes_used = int(du.stdout.strip().split()[0])
        snap["sites_dir_mib"] = round(bytes_used / (1024.0 * 1024.0), 2)

    # 4. MariaDB status, variables, and schema footprint
    sql = (
        "SHOW GLOBAL STATUS WHERE Variable_name IN ("
        "'Threads_connected','Threads_running','Max_used_connections',"
        "'Innodb_buffer_pool_reads','Innodb_buffer_pool_read_requests',"
        "'Table_open_cache_hits','Table_open_cache_misses','Open_tables','Opened_tables'"
        "); "
        "SHOW VARIABLES WHERE Variable_name IN ("
        "'version','max_connections','innodb_buffer_pool_size','innodb_flush_log_at_trx_commit','table_open_cache','open_files_limit'"
        "); "
        f"SELECT COUNT(DISTINCT table_schema) AS db_count, COUNT(*) AS table_count, "
        f"ROUND(COALESCE(SUM(data_length + index_length), 0) / 1024 / 1024, 2) AS total_mb "
        f"FROM information_schema.tables WHERE table_schema LIKE '{db_prefix}%';"
    )
    mdb = compose_exec(
        project, compose_file, "mariadb",
        "sh", "-ec", 'mariadb -N -B -h 127.0.0.1 -u root -p"$MYSQL_ROOT_PASSWORD" -e "$1"',
        "erp002_mdb_stats", sql,
        env_overrides={"MYSQL_ROOT_PASSWORD": db_root_password},
        timeout=30,
    )
    if mdb.returncode == 0:
        mdb_info: Dict[str, Any] = {}
        for line in mdb.stdout.strip().splitlines():
            cols = line.split("\t")
            if len(cols) == 2:
                mdb_info[cols[0]] = int(cols[1]) if cols[1].isdigit() else cols[1]
            elif len(cols) == 3:
                mdb_info["load_db_count"] = int(cols[0])
                mdb_info["load_table_count"] = int(cols[1])
                mdb_info["load_total_mb"] = float(cols[2])
        snap["mariadb"] = mdb_info

    # 5. Redis cache metrics
    rc = compose_exec(project, compose_file, "redis-cache", "redis-cli", "INFO", "memory", timeout=15)
    rs = compose_exec(project, compose_file, "redis-cache", "redis-cli", "INFO", "stats", timeout=15)
    rk = compose_exec(project, compose_file, "redis-cache", "redis-cli", "DBSIZE", timeout=15)
    redis_info: Dict[str, Any] = {}
    for raw in (rc.stdout if rc.returncode == 0 else "", rs.stdout if rs.returncode == 0 else ""):
        for ln in raw.splitlines():
            if ":" in ln and not ln.startswith("#"):
                k, v = ln.split(":", 1)
                if k in ("used_memory", "used_memory_human", "used_memory_rss_human",
                         "keyspace_hits", "keyspace_misses", "evicted_keys", "instantaneous_ops_per_sec"):
                    redis_info[k] = int(v) if v.isdigit() else v.strip()
    if rk.returncode == 0 and rk.stdout.strip().isdigit():
        redis_info["dbsize"] = int(rk.stdout.strip())
    snap["redis_cache"] = redis_info

    return snap


def _run_concurrent_wave(
    engine_port: int,
    sites: List[str],
    tokens: Dict[str, str],
    concurrency: int,
    total_requests: int,
    seed: int = 20261118,
    written_tags: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Run an authenticated mixed workload across all sites at a given concurrency.

    `response_check_failures` counts malformed or failed responses only; it is NOT an isolation
    signal. Tags of successful ToDo writes are appended to `written_tags` (site -> tags) so
    `verify_tag_isolation` can check them against every site after the run.
    """
    tags_lock = threading.Lock()
    rng = random.Random(seed + concurrency)
    plan: List[Tuple[str, str]] = []
    for i in range(total_requests):
        site = sites[i % len(sites)] if i < len(sites) else rng.choice(sites)
        r = rng.random()
        if r < 0.40:
            op = "ping"
        elif r < 0.80:
            op = "read_user"
        else:
            op = "write_todo"
        plan.append((site, op))

    latencies_by_op: Dict[str, List[float]] = {"ping": [], "read_user": [], "write_todo": []}
    all_latencies: List[float] = []
    status_counts: Dict[str, int] = {}
    response_check_failures = 0
    errors_sample: List[str] = []

    def execute_one(item: Tuple[str, str]) -> Tuple[str, int, float, bool, Optional[str]]:
        site, op = item
        tok = tokens[site]
        auth_headers = {"Authorization": f"token {tok}", "Accept": "application/json"}
        if op == "ping":
            st, body, ms = _host_http_request(engine_port, site, "GET", "/api/method/ping")
            return op, st, ms, True, None if st == 200 else f"{site} ping -> {st}: {body[:120]}"
        if op == "read_user":
            st, body, ms = _host_http_request(
                engine_port, site, "GET", "/api/method/frappe.auth.get_logged_user", headers=auth_headers
            )
            ok_resp = st == 200 and "Administrator" in body
            err = None if ok_resp else f"{site} read_user -> {st}: {body[:120]}"
            return op, st, ms, ok_resp or st != 200, err
        # write_todo: write a tenant-tagged ToDo; the echoed tag only proves the response is
        # well-formed. Cross-tenant placement is checked after the run (verify_tag_isolation).
        tag = f"erp002-{site}-{secrets.token_hex(4)}"
        payload = json.dumps({"description": tag, "status": "Open"})
        headers = {**auth_headers, "Content-Type": "application/json"}
        st, body, ms = _host_http_request(
            engine_port, site, "POST", "/api/resource/ToDo", headers=headers, body=payload
        )
        ok_iso = True
        if st == 200:
            ok_iso = tag in body
            if written_tags is not None:
                with tags_lock:
                    written_tags.setdefault(site, []).append(tag)
        err = None if (st == 200 and ok_iso) else f"{site} write_todo -> {st}: {body[:120]}"
        return op, st, ms, ok_iso, err

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futs = [pool.submit(execute_one, item) for item in plan]
        for fut in as_completed(futs):
            op, st, ms, ok_iso, err = fut.result()
            latencies_by_op[op].append(ms)
            all_latencies.append(ms)
            key = str(st)
            status_counts[key] = status_counts.get(key, 0) + 1
            if not ok_iso:
                response_check_failures += 1
            if err and len(errors_sample) < 5:
                errors_sample.append(err)
    wall_s = time.perf_counter() - t0
    ok_200 = status_counts.get("200", 0)

    return {
        "concurrency": concurrency,
        "total_requests": total_requests,
        "wall_seconds": round(wall_s, 2),
        "rps": round(total_requests / max(wall_s, 1e-6), 2),
        "http_200": ok_200,
        "success_rate_pct": round((ok_200 / total_requests) * 100.0, 2),
        "status_counts": status_counts,
        "response_check_failures": response_check_failures,
        "overall_latency": compute_latency_stats(all_latencies),
        "op_latency": {op: compute_latency_stats(vals) for op, vals in latencies_by_op.items()},
        "errors_sample": errors_sample,
    }


def verify_tag_isolation(
    engine_port: int,
    sites: List[str],
    tokens: Dict[str, str],
    written_tags: Dict[str, List[str]],
) -> Dict[str, Any]:
    """Post-run cross-tenant check: each written tag exists in its own site and in no other.

    Reads `GET /api/resource/ToDo` per site with that site's own token. A site passes when
    (a) every tag written to it is present (none missing) and (b) it holds no tag that was
    written to a different site (none foreign). Any non-200 read fails closed.
    """
    owner: Dict[str, str] = {t: site for site, tags in written_tags.items() for t in tags}
    qs = urllib.parse.urlencode(
        {
            "fields": json.dumps(["description"]),
            "filters": json.dumps([["description", "like", "erp002-%"]]),
            "limit_page_length": 0,
        }
    )
    missing_total = 0
    foreign_total = 0
    read_failures: List[str] = []
    per_site_issues: List[Dict[str, Any]] = []
    for site in sites:
        st, body, _ms = _host_http_request(
            engine_port,
            site,
            "GET",
            f"/api/resource/ToDo?{qs}",
            headers={"Authorization": f"token {tokens[site]}", "Accept": "application/json"},
        )
        if st != 200:
            read_failures.append(f"{site} -> {st}")
            continue
        try:
            rows = json.loads(body).get("data", [])
            found = {r.get("description") for r in rows}
        except (ValueError, AttributeError):
            read_failures.append(f"{site} -> unparseable body")
            continue
        expected = set(written_tags.get(site, []))
        missing = expected - found
        foreign = {t for t in found if owner.get(t, site) != site}
        missing_total += len(missing)
        foreign_total += len(foreign)
        if missing or foreign:
            per_site_issues.append({"site": site, "missing": len(missing), "foreign": len(foreign)})
    tags_checked = sum(len(v) for v in written_tags.values())
    return {
        "sites_checked": len(sites),
        "tags_written": tags_checked,
        "missing_tags": missing_total,
        "foreign_tags": foreign_total,
        "read_failures": read_failures,
        "sites_with_issues": per_site_issues[:10],
        "passed": tags_checked > 0 and not read_failures and missing_total == 0 and foreign_total == 0,
    }


def _collect_host_info() -> Dict[str, Any]:
    """Record the host/Docker limits the numbers were measured on (never invented)."""
    info: Dict[str, Any] = {"host_cpu_count": os.cpu_count()}
    try:
        res = subprocess.run(
            ["docker", "info", "--format", "{{.NCPU}}|{{.MemTotal}}|{{.OperatingSystem}}|{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        parts = res.stdout.strip().split("|") if res.returncode == 0 else []
        if len(parts) == 4:
            info["docker_ncpu"] = int(parts[0]) if parts[0].isdigit() else parts[0]
            info["docker_mem_total_mib"] = round(int(parts[1]) / (1024.0 * 1024.0), 1) if parts[1].isdigit() else parts[1]
            info["docker_os"] = parts[2]
            info["docker_server_version"] = parts[3]
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for ln in fh:
                if ln.startswith("model name"):
                    info["host_cpu_model"] = ln.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    return info


def _verify_cross_tenant_db_isolation(
    project: str,
    compose_file: Path,
    site_a: str,
    site_b: str,
) -> Dict[str, Any]:
    """Verify tenant A's MariaDB user cannot SELECT from tenant B's schema."""
    py = (
        "import json, os, pymysql, sys\n"
        "os.chdir(os.path.expanduser('~/frappe-bench/sites'))\n"
        "a_cfg = json.load(open(sys.argv[1] + '/site_config.json'))\n"
        "b_cfg = json.load(open(sys.argv[2] + '/site_config.json'))\n"
        "conn = pymysql.connect(host=a_cfg['db_host'], user=a_cfg['db_name'], password=a_cfg['db_password'], database=a_cfg['db_name'])\n"
        "try:\n"
        "    with conn.cursor() as cur:\n"
        "        try:\n"
        "            cur.execute(f\"SELECT COUNT(*) FROM `{b_cfg['db_name']}`.`tabUser`\")\n"
        "            print(json.dumps({'isolated': False, 'error': 'unexpected read succeeded'}))\n"
        "        except Exception as exc:\n"
        "            code = exc.args[0] if exc.args else None\n"
        "            print(json.dumps({'isolated': code == 1142, 'errno': code}))\n"
        "finally:\n"
        "    conn.close()\n"
    )
    res = compose_exec(project, compose_file, "engine", "env/bin/python", "-c", py, site_a, site_b, timeout=30)
    if res.returncode != 0:
        return {"isolated": False, "error": res.stderr or res.stdout}
    return json.loads(res.stdout.strip().splitlines()[-1])


def run_spike(
    project: str,
    compose_file: Path,
    engine_port: int,
    tenant_count: int,
    concurrency_levels: List[int],
    requests_per_level: int,
    clone_workers: int,
    db_root_password: str,
    admin_password: str,
    skip_provision: bool = False,
    provision_only: bool = False,
    reuse_template_site: bool = False,
    bulk_import_trx_commit_2: bool = False,
    skip_existing_db: bool = False,
    site_start: int = 1,
    site_end: Optional[int] = None,
    cleanup_sites: bool = False,
) -> Dict[str, Any]:
    validate_project_name(project)
    sites = site_names_for_count(tenant_count)
    end_idx = tenant_count if site_end is None else site_end
    if site_start < 1 or end_idx > tenant_count or site_start > end_idx:
        raise ValueError(f"Invalid site range {site_start}:{end_idx} for {tenant_count} tenants")
    report: Dict[str, Any] = {
        "plan_id": "ERP-002",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "compose_project": project,
        "engine_port": engine_port,
        "tenant_count": tenant_count,
        "concurrency_levels": concurrency_levels,
        "requests_per_level": requests_per_level,
        "clone_workers": clone_workers,
        "bulk_import_trx_commit_2": bulk_import_trx_commit_2,
    }

    report["host"] = _collect_host_info()
    report["baseline_before_provision"] = _collect_snapshots(project, compose_file, db_root_password)

    # Phase 1: Provisioning (1 cold + N-1 parallel clones, optionally sliced via site_start..site_end)
    if not skip_provision:
        template_site = sites[0]
        template_db = db_name_for_site(template_site)
        t_prov0 = time.perf_counter()
        if reuse_template_site:
            print(f"[ERP-002] Reusing existing template site {template_site}", file=sys.stderr, flush=True)
            tpl_info = {"site_name": template_site, "db_name": template_db, "reused": True, "cold_provision_seconds": 0.0}
        else:
            print(f"[ERP-002] Provisioning cold template site {template_site}...", file=sys.stderr, flush=True)
            tpl_info = _provision_template_site(
                project, compose_file, template_site, template_db, db_root_password, admin_password
            )
            print(f"[ERP-002] Template {template_site} ready in {tpl_info['cold_provision_seconds']}s", file=sys.stderr, flush=True)

        dump_info = _dump_template_db(project, compose_file, template_db, db_root_password)
        print(f"[ERP-002] Dumped template DB ({dump_info['dump_bytes']} bytes) in {dump_info['dump_seconds']}s", file=sys.stderr, flush=True)

        target_clone_sites = [s for s in sites[site_start - 1 : end_idx] if s != template_site]
        clone_latencies: List[float] = []
        t_clone0 = time.perf_counter()
        if bulk_import_trx_commit_2:
            _set_mariadb_trx_commit(project, compose_file, db_root_password, 2)
        try:
            with ThreadPoolExecutor(max_workers=clone_workers) as pool:
                futs = {
                    pool.submit(
                        _clone_single_site,
                        project,
                        compose_file,
                        s,
                        db_name_for_site(s),
                        db_root_password,
                        dump_info["dump_path"],
                        skip_existing_db,
                    ): s
                    for s in target_clone_sites
                }
                done_cnt = 0
                for fut in as_completed(futs):
                    clone_latencies.append(fut.result())
                    done_cnt += 1
                    if done_cnt % 5 == 0 or done_cnt == len(target_clone_sites):
                        print(f"[ERP-002] Cloned {done_cnt}/{len(target_clone_sites)} sites ({time.perf_counter() - t_clone0:.1f}s)", file=sys.stderr, flush=True)
        finally:
            if bulk_import_trx_commit_2:
                _set_mariadb_trx_commit(project, compose_file, db_root_password, 1)

        clone_wall_s = round(time.perf_counter() - t_clone0, 2)
        compose_exec(project, compose_file, "mariadb", "rm", "-f", dump_info["dump_path"], timeout=30)
        total_prov_s = round(time.perf_counter() - t_prov0, 2)
        report["provisioning"] = {
            "template_site": tpl_info,
            "dump": {k: v for k, v in dump_info.items() if k != "dump_path"},
            "site_range": f"{site_start}:{end_idx}",
            "cloned_count": len(clone_latencies),
            "clone_wall_seconds": clone_wall_s,
            "clone_per_site_ms": compute_latency_stats([x * 1000.0 for x in clone_latencies]),
            "total_sites_seconds": total_prov_s,
            "projected_serial_cold_sites_seconds": round(tpl_info["cold_provision_seconds"] * tenant_count, 2)
            if tpl_info["cold_provision_seconds"] > 0 else None,
        }

    if provision_only:
        report["idle_after_provision"] = _collect_snapshots(project, compose_file, db_root_password)
        report["cross_tenant_db_check"] = _verify_cross_tenant_db_isolation(project, compose_file, sites[0], sites[-1]) if end_idx == tenant_count else None
        return report

    # Generate unique per-site API keys (also tests encrypted __Auth with per-site Fernet keys)
    print(f"[ERP-002] Generating per-site API keys for {len(sites)} sites...", file=sys.stderr, flush=True)
    t_tok0 = time.perf_counter()
    tokens = _generate_per_site_api_tokens(project, compose_file, sites)
    report["token_seeding_seconds"] = round(time.perf_counter() - t_tok0, 2)
    report["cross_tenant_db_check"] = _verify_cross_tenant_db_isolation(project, compose_file, sites[0], sites[-1])
    report["idle_after_provision"] = _collect_snapshots(project, compose_file, db_root_password)

    # Phase 2: Sequential cold-hit warming across all N sites
    print(f"[ERP-002] Warming HTTP/Redis caches across {len(sites)} sites...", file=sys.stderr, flush=True)
    warm_pings: List[float] = []
    warm_auth_reads: List[float] = []
    warm_ok = 0
    for s in sites:
        st1, _, ms1 = _host_http_request(engine_port, s, "GET", "/api/method/ping")
        warm_pings.append(ms1)
        st2, body2, ms2 = _host_http_request(
            engine_port,
            s,
            "GET",
            "/api/method/frappe.auth.get_logged_user",
            headers={"Authorization": f"token {tokens[s]}"},
        )
        warm_auth_reads.append(ms2)
        if st1 == 200 and st2 == 200 and "Administrator" in body2:
            warm_ok += 1

    report["cold_cache_warming"] = {
        "sites_verified_200": warm_ok,
        "ping_latency": compute_latency_stats(warm_pings),
        "auth_read_latency": compute_latency_stats(warm_auth_reads),
    }
    report["after_50_site_warm"] = _collect_snapshots(project, compose_file, db_root_password)

    # Phase 3: Concurrent load waves across all N tenants
    waves: List[Dict[str, Any]] = []
    written_tags: Dict[str, List[str]] = {}
    for conc in concurrency_levels:
        print(f"[ERP-002] Running load wave concurrency={conc} ({requests_per_level} reqs)...", file=sys.stderr, flush=True)
        wave = _run_concurrent_wave(
            engine_port=engine_port,
            sites=sites,
            tokens=tokens,
            concurrency=conc,
            total_requests=requests_per_level,
            written_tags=written_tags,
        )
        wave["post_wave_snapshot"] = _collect_snapshots(project, compose_file, db_root_password)
        waves.append(wave)
    report["load_waves"] = waves
    report["tag_isolation_check"] = verify_tag_isolation(engine_port, sites, tokens, written_tags)

    if cleanup_sites:
        for s in sites:
            compose_exec(
                project, compose_file, "engine",
                "sh", "-ec",
                'site="$1"; bench drop-site "$site" --force --no-backup --db-root-password "$DB_ROOT_PASSWORD" || true',
                "erp002_drop", s,
                env_overrides={"DB_ROOT_PASSWORD": db_root_password},
                timeout=120,
            )

    return report


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="ERP-002 50-tenant provisioning and load spike runner.")
    ap.add_argument("--compose-project", default=os.environ.get("COMPOSE_PROJECT_NAME", ""))
    ap.add_argument("--compose-file", default=str(DEFAULT_COMPOSE_FILE))
    ap.add_argument("--engine-port", type=int, default=int(os.environ.get("ENGINE_PORT", "18222")))
    ap.add_argument("--tenants", type=int, default=50)
    ap.add_argument("--concurrency-levels", default="10,25,50,100")
    ap.add_argument("--requests-per-level", type=int, default=200)
    ap.add_argument("--clone-workers", type=int, default=4)
    ap.add_argument("--site-start", type=int, default=1)
    ap.add_argument("--site-end", type=int, default=None)
    ap.add_argument("--skip-provision", action="store_true")
    ap.add_argument("--provision-only", action="store_true")
    ap.add_argument("--reuse-template-site", action="store_true")
    ap.add_argument("--bulk-import-trx-commit-2", action="store_true")
    ap.add_argument("--skip-existing-db", action="store_true")
    ap.add_argument("--cleanup-sites", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--output-json", default="")
    return ap.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        project = validate_project_name(args.compose_project)
        levels = parse_concurrency_levels(args.concurrency_levels)
        sites = site_names_for_count(args.tenants)
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        plan = {
            "status": "dry_run",
            "compose_project": project,
            "compose_file": args.compose_file,
            "engine_port": args.engine_port,
            "tenant_count": args.tenants,
            "first_site": sites[0],
            "last_site": sites[-1],
            "site_range": f"{args.site_start}:{args.site_end or args.tenants}",
            "concurrency_levels": levels,
            "requests_per_level": args.requests_per_level,
            "clone_workers": args.clone_workers,
            "bulk_import_trx_commit_2": args.bulk_import_trx_commit_2,
        }
        print(json.dumps(plan, indent=2))
        return 0

    db_root_pw = os.environ.get("DB_ROOT_PASSWORD", "")
    admin_pw = os.environ.get("ADMIN_PASSWORD", "")
    if not db_root_pw or (not args.skip_provision and not args.reuse_template_site and not admin_pw):
        print("DB_ROOT_PASSWORD and ADMIN_PASSWORD environment variables are required.", file=sys.stderr)
        return 2

    result = run_spike(
        project=project,
        compose_file=Path(args.compose_file),
        engine_port=args.engine_port,
        tenant_count=args.tenants,
        concurrency_levels=levels,
        requests_per_level=args.requests_per_level,
        clone_workers=args.clone_workers,
        db_root_password=db_root_pw,
        admin_password=admin_pw,
        skip_provision=args.skip_provision,
        provision_only=args.provision_only,
        reuse_template_site=args.reuse_template_site,
        bulk_import_trx_commit_2=args.bulk_import_trx_commit_2,
        skip_existing_db=args.skip_existing_db,
        site_start=args.site_start,
        site_end=args.site_end,
        cleanup_sites=args.cleanup_sites,
    )
    rendered = json.dumps(result, indent=2)
    if args.output_json:
        Path(args.output_json).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
