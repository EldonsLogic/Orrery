#!/usr/bin/env python3
"""
Tenant Site Provisioning for the platform Engine Runtime (ERP-003).

Implements scripted site-per-tenant creation (ADR-0006) on the Frappe/ERPNext v15
Compose dev bench (ERP-001) with:
- Strict input validation for tenant IDs, RFC 1123 hostnames, DB identifiers, and apps
- Automated installation of core in-scope apps (erpnext, hrms, change_engine)
- Country-specific locale and currency defaults (SA, AE, EG, QA per ADR-0024)
- Safe site_config.json writes via `bench --site <site> set-config` (no code-string eval)
- Fail-closed app verification via `bench --site <site> list-apps --format json`
- Redacted dry-run plans and env-forwarded credentials (no secrets on host CLI argv)

Notes and unverified surfaces:
- ADR-0016 engine invisibility is enforced by network isolation and the API gateway,
  NOT by site_config.json keys in this script. This script defaults developer_mode to 0
  unless explicitly enabled, and does not claim to disable Desk or default web routes.
- Upstream Frappe v15 `bench new-site` exposes no envvar or stdin options for
  `--db-root-password`, `--admin-password`, or `--db-password`. Host CLI argv never
  contains secrets (forwarded via `docker compose exec -T -e`), though the ephemeral
  `bench new-site` process inside the isolated engine container receives them as flags.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import hashlib
import inspect
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Regional Country Defaults (ADR-0024)
SUPPORTED_COUNTRIES: Dict[str, Dict[str, str]] = {
    "SA": {
        "name": "Saudi Arabia",
        "currency": "SAR",
        "time_zone": "Asia/Riyadh",
        "default_language": "ar",
    },
    "AE": {
        "name": "United Arab Emirates",
        "currency": "AED",
        "time_zone": "Asia/Dubai",
        "default_language": "ar",
    },
    "EG": {
        "name": "Egypt",
        "currency": "EGP",
        "time_zone": "Africa/Cairo",
        "default_language": "ar",
    },
    "QA": {
        "name": "Qatar",
        "currency": "QAR",
        "time_zone": "Asia/Qatar",
        "default_language": "ar",
    },
}

DEFAULT_IN_SCOPE_APPS = ["erpnext", "hrms", "change_engine"]
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COMPOSE_FILE = REPO_ROOT / "infra" / "dev" / "docker" / "docker-compose.dev.yml"

_TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_TLD_RE = re.compile(r"^[a-z]{2,63}$")
_DB_IDENT_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")
_APP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_LANGUAGE_RE = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$")
_TIMEZONE_RE = re.compile(r"^(?:UTC|[A-Za-z_]+(?:/[A-Za-z0-9_+-]+)+)$")
_COMPOSE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_DB_HOST_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?$")

_NEW_SITE_POSIX_SH = (
    'site="$1"; db_host="$2"; db_name="$3"; shift 3; '
    'for app in "$@"; do set -- "$@" --install-app "$app"; shift; done; '
    'exec bench new-site "$site" '
    '--db-host "$db_host" '
    '--mariadb-user-host-login-scope=% '
    '--db-root-password "$DB_ROOT_PASSWORD" '
    '--admin-password "$ADMIN_PASSWORD" '
    '--db-name "$db_name" '
    '--db-password "$DB_PASSWORD" "$@"'
)

# BPL-046: Frappe's MariaDBTable.create() never adds the `creation` index that alter() adds to every table whose
# sort_field is creation (frappe/database/mariadb/schema.py:84 on the pinned bench), nor a missing search_index index
# (schema.py:78). A fresh site therefore lacks indexes that the engine's first schema sync of such a table adds next
# to an approved ADD COLUMN, and the DDL gate refuses it. This program runs Frappe's own sync (frappe.db.updatedb)
# on every table once. Frappe's alter() joins its clauses into one statement, so each statement is split into its
# top-level clauses (outside parentheses, backticks and quotes): only ADD INDEX clauses that match Frappe's exact index
# shape run, rebuilt into one statement; MODIFY clauses (Frappe's re-emits) are counted and never sent; a `;`, an
# unbalanced statement, any other clause kind, any UNIQUE in a MODIFY or any ADD INDEX clause with extra text (a comment
# included) fails closed. Idempotent: a second run adds nothing (checked by hand on the pinned bench, BPL-046; the
# stand-in frappe of the unit tests cannot show it). Run from the bench directory with the site as its one argument.
INDEX_SYNC_PY = r'''
import json, re, sys, frappe
frappe.init(site=sys.argv[1], sites_path=".")
frappe.connect()
try:
    run_ddl, added, skipped = frappe.db.sql_ddl, [], [0]
    def clauses(body):
        parts, cur, depth, tick, quote = [], "", 0, False, False
        for ch in body:
            if ch == "`" and not quote:
                tick = not tick
            elif ch == "'" and not tick:
                quote = not quote
            elif not tick and not quote:
                if ch == ";":
                    return None
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth < 0:
                        return None
                elif ch == "," and depth == 0:
                    parts.append(cur.strip())
                    cur = ""
                    continue
            cur += ch
        if tick or quote or depth:
            return None
        parts.append(cur.strip())
        return parts
    # The only clause ever sent: exactly what Frappe's alter() emits for an index, one plain name and one plain column
    # (all 62 additions on a fresh pinned site have this shape). A comment, quote or anything else inside an ADD INDEX
    # clause fails the full match, so no text can ride along with a sent clause (#381 re-review).
    INDEX_CLAUSE = re.compile(r"ADD INDEX `[A-Za-z0-9_]+`\(`[A-Za-z0-9_]+`\)")
    def bad(part):
        if part.startswith("ADD INDEX "):
            return not INDEX_CLAUSE.fullmatch(part)
        bare = re.sub(r"`[^`]*`", "", part)
        return not re.match(r"MODIFY \S", part) or re.search(r"\bUNIQUE\b", bare, re.I)
    def admit(query, debug=False):
        stmt = " ".join(str(query).split())
        m = re.fullmatch(r"ALTER TABLE (`[^`]+`) (.+)", stmt)
        parts = clauses(m.group(2)) if m else None
        if not parts or any(bad(p) for p in parts):
            raise SystemExit("index sync refused DDL: " + stmt[:200])
        adds = [p for p in parts if p.startswith("ADD INDEX ")]
        skipped[0] += len(parts) - len(adds)
        if not adds:
            return None
        rebuilt = "ALTER TABLE " + m.group(1) + " " + ", ".join(adds)
        added.append(rebuilt)
        return run_ddl(rebuilt, debug=debug)
    frappe.db.sql_ddl = admit
    doctypes = frappe.get_all("DocType", filters={"issingle": 0, "is_virtual": 0}, pluck="name", order_by="name")
    for doctype in doctypes:
        frappe.db.updatedb(doctype)
    print(json.dumps({"tables": len(doctypes), "indexes_added": added, "modify_not_sent": skipped[0]}))
finally:
    frappe.destroy()
'''


def index_sync_command(site_name: str) -> List[str]:
    """The in-container command that runs INDEX_SYNC_PY on one site (BPL-046)."""
    return ["sh", "-ec", 'cd sites && exec ../env/bin/python -c "$1" "$2"', "provision_tenant_site",
            INDEX_SYNC_PY, validate_site_name(site_name)]


class ProvisioningError(Exception):
    """Raised when tenant site provisioning fails."""


def validate_site_name(site_name: str) -> str:
    """Validate and normalize a strict multi-label RFC 1123 hostname for Frappe site_name."""
    if not isinstance(site_name, str):
        raise ProvisioningError("site_name must be a string.")
    if any(ch.isspace() for ch in site_name):
        raise ProvisioningError(f"Invalid site_name '{site_name!r}': whitespace is not allowed.")
    normalized = site_name.lower()
    if not normalized or len(normalized) > 253:
        raise ProvisioningError(
            f"Invalid site_name '{normalized}': must be 1-253 characters."
        )
    labels = normalized.split(".")
    if len(labels) < 2:
        raise ProvisioningError(
            f"Invalid site_name '{normalized}': must be a multi-label domain or <tenant>.localhost."
        )
    for label in labels:
        if not _HOST_LABEL_RE.fullmatch(label):
            raise ProvisioningError(
                f"Invalid site_name '{normalized}': label '{label}' violates hostname rules."
            )
    if not _TLD_RE.fullmatch(labels[-1]):
        raise ProvisioningError(
            f"Invalid site_name '{normalized}': top-level label '{labels[-1]}' must be alphabetic."
        )
    return normalized


def _redact_secrets(text: str, secrets_to_mask: List[str]) -> str:
    """Mask any known secret values before surfacing command output or errors."""
    masked = text
    for secret in secrets_to_mask:
        if secret:
            masked = masked.replace(secret, "<REDACTED>")
    return masked


@dataclasses.dataclass
class TenantConfig:
    tenant_id: str
    country: str = "SA"
    site_name: Optional[str] = None
    currency: Optional[str] = None
    language: Optional[str] = None
    time_zone: Optional[str] = None
    apps: List[str] = dataclasses.field(default_factory=lambda: list(DEFAULT_IN_SCOPE_APPS))
    db_name: Optional[str] = None
    db_host: str = "mariadb"
    db_password: Optional[str] = None
    admin_password: Optional[str] = None
    developer_mode: bool = False

    def __post_init__(self) -> None:
        # Validate tenant_id strictly (DNS-label safe: lowercase alphanumeric + internal hyphens only)
        if not isinstance(self.tenant_id, str):
            raise ProvisioningError("tenant_id must be a string.")
        if any(ch.isspace() for ch in self.tenant_id):
            raise ProvisioningError(f"Invalid tenant_id '{self.tenant_id!r}': whitespace is not allowed.")
        self.tenant_id = self.tenant_id.lower()
        if not _TENANT_ID_RE.fullmatch(self.tenant_id):
            raise ProvisioningError(
                f"Invalid tenant_id '{self.tenant_id}': must be 3-63 lowercase alphanumeric "
                f"characters with internal hyphens only (no underscores or special characters)."
            )

        # Validate country (ADR-0024)
        if not isinstance(self.country, str):
            raise ProvisioningError("country must be a string.")
        self.country = self.country.strip().upper()
        if self.country not in SUPPORTED_COUNTRIES:
            supported = ", ".join(SUPPORTED_COUNTRIES.keys())
            raise ProvisioningError(
                f"Unsupported country '{self.country}'. Supported markets: {supported} (ADR-0024)."
            )

        # Country defaults and validation
        country_meta = SUPPORTED_COUNTRIES[self.country]
        self.currency = (self.currency or country_meta["currency"]).strip().upper()
        if not _CURRENCY_RE.fullmatch(self.currency):
            raise ProvisioningError(f"Invalid currency '{self.currency}': must be a 3-letter ISO code.")

        self.language = (self.language or country_meta["default_language"]).strip().lower()
        if not _LANGUAGE_RE.fullmatch(self.language):
            raise ProvisioningError(f"Invalid language '{self.language}'.")

        self.time_zone = (self.time_zone or country_meta["time_zone"]).strip()
        if not _TIMEZONE_RE.fullmatch(self.time_zone):
            raise ProvisioningError(f"Invalid time_zone '{self.time_zone}'.")

        # Site hostname
        if self.site_name is None or self.site_name == "":
            self.site_name = validate_site_name(f"{self.tenant_id}.localhost")
        else:
            self.site_name = validate_site_name(self.site_name)

        # Deterministic, safe DB name (Frappe v15 also uses db_name as the MariaDB user)
        if not self.db_name:
            h = hashlib.sha256(self.tenant_id.encode("utf-8")).hexdigest()[:12]
            self.db_name = f"_t_{h}"
        else:
            if not _DB_IDENT_RE.fullmatch(self.db_name):
                raise ProvisioningError(
                    f"Invalid db_name '{self.db_name}': must be 3-32 alphanumeric or underscore characters."
                )

        # DB host
        self.db_host = self.db_host.strip()
        if not _DB_HOST_RE.fullmatch(self.db_host):
            raise ProvisioningError(f"Invalid db_host '{self.db_host}'.")

        # Apps
        if not self.apps:
            raise ProvisioningError("At least one app must be specified in apps.")
        validated_apps: List[str] = []
        seen = set()
        for raw_app in self.apps:
            app = raw_app.strip()
            if not _APP_NAME_RE.fullmatch(app):
                raise ProvisioningError(f"Invalid app name '{raw_app}'.")
            if app not in seen:
                seen.add(app)
                validated_apps.append(app)
        self.apps = validated_apps


class TenantProvisioner:
    """Orchestrates scripted tenant site creation on Frappe v15 Compose bench."""

    def __init__(
        self,
        config: TenantConfig,
        compose_project: Optional[str] = None,
        compose_file: Optional[Path] = None,
        service_name: str = "engine",
        mariadb_root_password: Optional[str] = None,
        executor: Optional[Callable[..., Tuple[int, str, str]]] = None,
    ) -> None:
        self.config = config
        if compose_project is not None:
            if not _COMPOSE_NAME_RE.fullmatch(compose_project):
                raise ProvisioningError(
                    f"Invalid compose_project '{compose_project}': must match [a-z0-9][a-z0-9_-]*."
                )
        self.compose_project = compose_project
        self.compose_file = Path(compose_file) if compose_file else DEFAULT_COMPOSE_FILE
        if not _COMPOSE_NAME_RE.fullmatch(service_name):
            raise ProvisioningError(f"Invalid service_name '{service_name}'.")
        self.service_name = service_name
        self.mariadb_root_password = (
            mariadb_root_password if mariadb_root_password is not None else os.environ.get("DB_ROOT_PASSWORD", "")
        )
        self.executor = executor or self._default_executor

    def _run(
        self,
        cmd: List[str],
        env_overrides: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, str, str]:
        """Dispatch command to executor, forwarding env_overrides when supported."""
        if self.executor == self._default_executor:
            return self._default_executor(cmd, env_overrides=env_overrides)

        sig = inspect.signature(self.executor)
        params = list(sig.parameters.values())
        accepts_env = (
            len(params) >= 2
            or any(p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD) for p in params)
        )
        if accepts_env:
            return self.executor(cmd, env_overrides)
        return self.executor(cmd)

    def _default_executor(
        self,
        cmd: List[str],
        env_overrides: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, str, str]:
        """Run a command locally or via `docker compose exec -T` without CLI secret args."""
        proc_env = os.environ.copy()
        if env_overrides:
            proc_env.update(env_overrides)

        if self.compose_project:
            # docker-compose.dev.yml requires DB_ROOT_PASSWORD and ADMIN_PASSWORD for config parsing;
            if not proc_env.get("DB_ROOT_PASSWORD"):
                proc_env["DB_ROOT_PASSWORD"] = self.mariadb_root_password or "compose-exec-placeholder"
            if not proc_env.get("ADMIN_PASSWORD"):
                proc_env["ADMIN_PASSWORD"] = self.config.admin_password or "compose-exec-placeholder"
            compose_cmd = [
                "docker", "compose",
                "--project-name", self.compose_project,
                "--env-file", os.devnull,
                "-f", str(self.compose_file),
                "exec", "-T",
            ]
            for key in sorted((env_overrides or {}).keys()):
                compose_cmd.extend(["-e", key])
            compose_cmd.append(self.service_name)
            compose_cmd.extend(cmd)
            try:
                proc = subprocess.run(
                    compose_cmd,
                    cwd=str(self.compose_file.parent),
                    env=proc_env,
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ProvisioningError(f"Docker Compose execution failed: {exc}") from exc
        else:
            try:
                proc = subprocess.run(
                    cmd,
                    env=proc_env,
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ProvisioningError(f"Command execution failed: {exc}") from exc
        return proc.returncode, proc.stdout, proc.stderr

    def _site_config_overrides(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.config.tenant_id,
            "country": SUPPORTED_COUNTRIES[self.config.country]["name"],
            "country_code": self.config.country,
            "currency": self.config.currency,
            "language": self.config.language,
            "time_zone": self.config.time_zone,
            "developer_mode": 1 if self.config.developer_mode else 0,
        }

    def _set_config_commands(self) -> List[List[str]]:
        cmds: List[List[str]] = []
        for key, value in self._site_config_overrides().items():
            if isinstance(value, (bool, int, float, dict, list)):
                cmds.append([
                    "bench", "--site", self.config.site_name,
                    "set-config", "--parse", key, json.dumps(value),
                ])
            else:
                cmds.append([
                    "bench", "--site", self.config.site_name,
                    "set-config", key, str(value),
                ])
        return cmds

    def build_provisioning_plan(self) -> Dict[str, Any]:
        """Build a declarative, secret-redacted execution plan without making changes."""
        redacted_new_site = [
            "bench", "new-site", self.config.site_name,
            "--db-host", self.config.db_host,
            "--mariadb-user-host-login-scope=%",
            "--db-root-password", "<REDACTED:DB_ROOT_PASSWORD>",
            "--admin-password", "<REDACTED:ADMIN_PASSWORD>",
            "--db-name", self.config.db_name,
            "--db-password", "<REDACTED:DB_PASSWORD>",
        ]
        for app in self.config.apps:
            redacted_new_site.extend(["--install-app", app])

        set_config_cmds = self._set_config_commands()
        list_apps_cmd = ["bench", "--site", self.config.site_name, "list-apps", "--format", "json"]

        return {
            "action": "provision_tenant_site",
            "tenant_id": self.config.tenant_id,
            "site_name": self.config.site_name,
            "country": self.config.country,
            "currency": self.config.currency,
            "language": self.config.language,
            "time_zone": self.config.time_zone,
            "db_name": self.config.db_name,
            "db_user": self.config.db_name,
            "db_host": self.config.db_host,
            "apps": list(self.config.apps),
            "developer_mode": self.config.developer_mode,
            "compose_project": self.compose_project,
            "service": self.service_name if self.compose_project else None,
            "commands": {
                "new_site": redacted_new_site,
                "index_sync": index_sync_command(self.config.site_name),
                "set_config": set_config_cmds,
                "list_apps": list_apps_cmd,
            },
            "site_config_overrides": self._site_config_overrides(),
        }

    def provision(self, dry_run: bool = False) -> Dict[str, Any]:
        """Execute tenant site creation or return the redacted dry-run plan."""
        plan = self.build_provisioning_plan()
        if dry_run:
            return {
                "status": "dry_run",
                "plan": plan,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

        if not self.mariadb_root_password:
            raise ProvisioningError(
                "MariaDB root password is required for live site provisioning. "
                "Set the DB_ROOT_PASSWORD environment variable."
            )

        admin_password = (
            self.config.admin_password
            or os.environ.get("ADMIN_PASSWORD")
            or secrets.token_urlsafe(24)
        )
        db_password = self.config.db_password or secrets.token_urlsafe(24)
        secrets_to_mask = [self.mariadb_root_password, admin_password, db_password]

        # 1. Execute bench new-site with credentials passed via environment variables (never on host CLI argv)
        new_site_cmd = [
            "sh", "-ec", _NEW_SITE_POSIX_SH,
            "provision_tenant_site",
            self.config.site_name,
            self.config.db_host,
            self.config.db_name,
            *self.config.apps,
        ]
        new_site_env = {
            "DB_ROOT_PASSWORD": self.mariadb_root_password,
            "ADMIN_PASSWORD": admin_password,
            "DB_PASSWORD": db_password,
        }
        rc, stdout, stderr = self._run(new_site_cmd, env_overrides=new_site_env)
        if rc != 0:
            detail = _redact_secrets(stderr or stdout, secrets_to_mask)
            raise ProvisioningError(f"bench new-site failed (code {rc}): {detail}")

        # 1b. BPL-046: add the indexes the engine's own schema sync expects, before any apply (fail closed)
        rc_idx, out_idx, err_idx = self._run(index_sync_command(self.config.site_name))
        try:
            index_sync = json.loads((out_idx or "").strip().splitlines()[-1])
        except (IndexError, ValueError):
            index_sync = None
        if (rc_idx != 0 or not isinstance(index_sync, dict) or not isinstance(index_sync.get("tables"), int)
                or index_sync["tables"] < 1 or not isinstance(index_sync.get("indexes_added"), list)):
            detail = _redact_secrets(err_idx or out_idx or "", secrets_to_mask)[-500:]
            raise ProvisioningError(f"Index sync failed (code {rc_idx}): {detail}")

        # 2. Apply site_config.json overrides via supported `bench set-config` (no python -c)
        for cfg_cmd in self._set_config_commands():
            rc_cfg, out_cfg, err_cfg = self._run(cfg_cmd)
            if rc_cfg != 0:
                detail = _redact_secrets(err_cfg or out_cfg, secrets_to_mask)
                raise ProvisioningError(
                    f"Failed applying site_config key '{cfg_cmd[-2]}': {detail}"
                )

        # 3. Verify installed apps fail-closed via `bench --site <site> list-apps --format json`
        list_apps_cmd = ["bench", "--site", self.config.site_name, "list-apps", "--format", "json"]
        rc_list, out_list, err_list = self._run(list_apps_cmd)
        if rc_list != 0:
            detail = _redact_secrets(err_list or out_list, secrets_to_mask)
            raise ProvisioningError(f"bench list-apps failed (code {rc_list}): {detail}")

        try:
            parsed = json.loads(out_list)
        except (TypeError, ValueError) as exc:
            raise ProvisioningError(f"bench list-apps returned invalid JSON: {exc}") from exc

        if not isinstance(parsed, dict) or not isinstance(parsed.get(self.config.site_name), list):
            raise ProvisioningError(
                f"bench list-apps output missing site entry '{self.config.site_name}'."
            )

        installed = [str(app).strip() for app in parsed[self.config.site_name] if str(app).strip()]
        if not installed:
            raise ProvisioningError(
                f"bench list-apps reported zero installed apps for '{self.config.site_name}'."
            )

        missing_apps = [app for app in self.config.apps if app not in installed]
        if missing_apps:
            raise ProvisioningError(
                f"Site '{self.config.site_name}' is missing requested apps after provisioning: "
                f"{', '.join(missing_apps)}"
            )

        return {
            "status": "success",
            "tenant_id": self.config.tenant_id,
            "site_name": self.config.site_name,
            "country": self.config.country,
            "currency": self.config.currency,
            "language": self.config.language,
            "time_zone": self.config.time_zone,
            "db_name": self.config.db_name,
            "db_user": self.config.db_name,
            "db_host": self.config.db_host,
            "installed_apps": installed,
            "index_sync": index_sync,
            "developer_mode": self.config.developer_mode,
            "admin_user": "Administrator",
            "admin_password": admin_password,
            "db_password": db_password,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }


def _reserve_credentials_file(path: Path) -> int:
    """Exclusively reserve a 0600 credentials file before provisioning starts."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(str(path), flags, 0o600)
    except OSError as exc:
        raise ProvisioningError(f"Cannot reserve credentials file '{path}': {exc}") from exc


def _write_reserved_credentials_file(fd: int, payload: Dict[str, Any]) -> None:
    """Write sensitive provisioning credentials to an already reserved file descriptor."""
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _write_credentials_file(path: Path, payload: Dict[str, Any]) -> None:
    """Write sensitive provisioning credentials to disk with mode 0600."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(path), flags, 0o600)
    _write_reserved_credentials_file(fd, payload)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scripted site-per-tenant provisioning for the platform engine runtime (ERP-003)."
    )
    parser.add_argument("--tenant-id", required=True, help="Unique tenant identifier (e.g. acme-trading).")
    parser.add_argument("--site-name", help="Tenant domain/site name (defaults to <tenant_id>.localhost).")
    parser.add_argument(
        "--country", default="SA", choices=list(SUPPORTED_COUNTRIES.keys()),
        help="Tenant country code (SA, AE, EG, QA per ADR-0024)."
    )
    parser.add_argument("--currency", help="ISO-4217 currency code (defaults by country).")
    parser.add_argument("--language", choices=["ar", "en"], help="Default language (defaults to ar).")
    parser.add_argument("--apps", help="Comma-separated Frappe apps (default: erpnext,hrms,change_engine).")
    parser.add_argument("--db-name", help="Dedicated database name (default: generated _t_<hash>).")
    parser.add_argument("--db-host", default="mariadb", help="MariaDB host for new-site (default: mariadb).")
    parser.add_argument(
        "--compose-project",
        default=None,
        help="Docker Compose project name (defaults to COMPOSE_PROJECT_NAME env var if set).",
    )
    parser.add_argument(
        "--compose-file",
        default=str(DEFAULT_COMPOSE_FILE),
        help="Path to docker-compose.dev.yml.",
    )
    parser.add_argument("--service", default="engine", help="Compose service name (default: engine).")
    parser.add_argument(
        "--developer-mode",
        action="store_true",
        help="Enable Frappe developer_mode=1 on the tenant site (defaults to 0).",
    )
    parser.add_argument(
        "--credentials-file",
        help="Write generated admin/DB credentials to a 0600 JSON file and omit them from stdout.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print redacted execution plan without making changes.")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    apps_list = (
        [a.strip() for a in args.apps.split(",") if a.strip()]
        if args.apps is not None
        else list(DEFAULT_IN_SCOPE_APPS)
    )
    compose_project = args.compose_project or os.environ.get("COMPOSE_PROJECT_NAME") or None

    creds_fd: Optional[int] = None
    creds_path: Optional[Path] = None
    try:
        config = TenantConfig(
            tenant_id=args.tenant_id,
            site_name=args.site_name,
            country=args.country,
            currency=args.currency,
            language=args.language,
            apps=apps_list,
            db_name=args.db_name,
            db_host=args.db_host,
            admin_password=os.environ.get("ADMIN_PASSWORD"),
            developer_mode=args.developer_mode,
        )
        provisioner = TenantProvisioner(
            config=config,
            compose_project=compose_project,
            compose_file=Path(args.compose_file),
            service_name=args.service,
        )

        if not args.dry_run and args.credentials_file:
            creds_path = Path(args.credentials_file)
            creds_fd = _reserve_credentials_file(creds_path)

        try:
            result = provisioner.provision(dry_run=args.dry_run)
        except Exception:
            if creds_fd is not None:
                try:
                    os.close(creds_fd)
                except OSError:
                    pass
                creds_fd = None
                if creds_path is not None:
                    try:
                        creds_path.unlink()
                    except OSError:
                        pass
            raise

        if creds_fd is not None and creds_path is not None:
            _write_reserved_credentials_file(
                creds_fd,
                {
                    "tenant_id": result["tenant_id"],
                    "site_name": result["site_name"],
                    "admin_user": result["admin_user"],
                    "admin_password": result["admin_password"],
                    "db_name": result["db_name"],
                    "db_user": result["db_user"],
                    "db_password": result["db_password"],
                },
            )
            creds_fd = None
            result.pop("admin_password", None)
            result.pop("db_password", None)
            result["credentials_file"] = str(creds_path)

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            status = str(result.get("status", "")).upper()
            print(f"=== Tenant Site Provisioning [{status}] ===")
            print(f"Tenant ID     : {config.tenant_id}")
            print(f"Site Name     : {config.site_name}")
            print(f"Country       : {config.country} ({SUPPORTED_COUNTRIES[config.country]['name']})")
            print(f"Currency      : {config.currency}")
            print(f"Database Name : {config.db_name}")
            print(f"Database Host : {config.db_host}")
            print(f"Developer Mode: {1 if config.developer_mode else 0}")
            print(f"Apps          : {', '.join(config.apps)}")
            if compose_project:
                print(f"Compose Target: {compose_project}/{args.service}")
            if args.dry_run:
                print("\n[Dry Run Plan - Secrets Redacted]")
                print("New-site cmd  :", " ".join(result["plan"]["commands"]["new_site"]))
                print("Index sync    : Frappe updatedb on every table, ADD INDEX only (BPL-046)")
                for cfg_cmd in result["plan"]["commands"]["set_config"]:
                    print("Set-config cmd:", " ".join(cfg_cmd))
                print("Verify cmd    :", " ".join(result["plan"]["commands"]["list_apps"]))
            else:
                sync = result["index_sync"]
                print(f"Index sync    : {sync['tables']} tables, {len(sync['indexes_added'])} indexes added")
                for stmt in sync["indexes_added"]:
                    print(f"  {stmt}")
                if "credentials_file" in result:
                    print(f"Credentials   : written to {result['credentials_file']} (mode 0600)")
                else:
                    print(f"Admin User    : {result['admin_user']}")
                    print(f"Admin Password: {result['admin_password']}")
        return 0
    except ProvisioningError as pe:
        if args.json:
            print(json.dumps({"status": "error", "error": str(pe)}))
        else:
            print(f"Error: {pe}", file=sys.stderr)
        return 1
    except Exception as ex:
        if args.json:
            print(json.dumps({"status": "error", "error": f"Unexpected failure: {ex}"}))
        else:
            print(f"Unexpected error: {ex}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
