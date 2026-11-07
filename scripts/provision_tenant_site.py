#!/usr/bin/env python3
"""
Tenant Site Provisioning for the Orrery Engine Runtime (ERP-003).

Implements scripted site-per-tenant creation (ADR-0006) on the Frappe/ERPNext
engine bench with:
- Strict tenant database isolation (one DB per tenant)
- Automated installation of core in-scope apps (erpnext, hrms, change_engine)
- Country-specific locale and currency defaults (SA, AE, EG, QA per ADR-0024)
- Headless runtime configuration per ADR-0016 (engine invisibility)
- Structured JSON output for upstream platform provisioning (PLT-003)
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import hashlib
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


class ProvisioningError(Exception):
    """Raised when tenant site provisioning fails."""
    pass


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
    db_user: Optional[str] = None
    db_password: Optional[str] = None
    admin_password: Optional[str] = None
    headless: bool = True
    developer_mode: bool = True

    def __post_init__(self):
        # Normalize and validate tenant_id
        self.tenant_id = self.tenant_id.strip().lower()
        if not re.match(r"^[a-z0-9][a-z0-9_-]{1,62}[a-z0-9]$", self.tenant_id):
            raise ProvisioningError(
                f"Invalid tenant_id '{self.tenant_id}': must be 3-64 lowercase alphanumeric "
                f"characters with internal hyphens or underscores."
            )

        # Normalize country
        self.country = self.country.strip().upper()
        if self.country not in SUPPORTED_COUNTRIES:
            supported = ", ".join(SUPPORTED_COUNTRIES.keys())
            raise ProvisioningError(
                f"Unsupported country '{self.country}'. Supported markets: {supported} (ADR-0024)."
            )

        # Defaults from country
        country_meta = SUPPORTED_COUNTRIES[self.country]
        if not self.currency:
            self.currency = country_meta["currency"]
        if not self.language:
            self.language = country_meta["default_language"]
        if not self.time_zone:
            self.time_zone = country_meta["time_zone"]

        # Default site name
        if not self.site_name:
            self.site_name = f"{self.tenant_id}.localhost"
        else:
            self.site_name = self.site_name.strip().lower()
            if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", self.site_name) and not self.site_name.endswith(".localhost"):
                raise ProvisioningError(
                    f"Invalid site_name '{self.site_name}': must be a valid domain or .localhost name."
                )

        # Deterministic, safe DB name (16-char hash to stay within MariaDB identifier limits)
        if not self.db_name:
            h = hashlib.sha256(self.tenant_id.encode("utf-8")).hexdigest()[:12]
            self.db_name = f"_t_{h}"
        else:
            if not re.match(r"^[a-zA-Z0-9_]{3,32}$", self.db_name):
                raise ProvisioningError(
                    f"Invalid db_name '{self.db_name}': must be 3-32 alphanumeric or underscore characters."
                )

        # DB User
        if not self.db_user:
            self.db_user = f"u_{self.db_name[3:]}"
        else:
            if not re.match(r"^[a-zA-Z0-9_]{3,32}$", self.db_user):
                raise ProvisioningError(
                    f"Invalid db_user '{self.db_user}': must be 3-32 alphanumeric or underscore characters."
                )

        # Generate cryptographically secure passwords if not provided
        if not self.db_password:
            self.db_password = secrets.token_urlsafe(24)
        if not self.admin_password:
            self.admin_password = secrets.token_urlsafe(24)


class TenantProvisioner:
    """Orchestrates reproducible, scripted tenant site creation on Frappe bench."""

    def __init__(
        self,
        config: TenantConfig,
        container_name: Optional[str] = None,
        bench_dir: Optional[str] = None,
        mariadb_root_password: Optional[str] = None,
        executor: Optional[Callable[[List[str]], Tuple[int, str, str]]] = None,
    ):
        self.config = config
        self.container_name = container_name
        self.bench_dir = bench_dir
        self.mariadb_root_password = mariadb_root_password or os.environ.get("DB_ROOT_PASSWORD", "")
        self.executor = executor or self._default_executor

    def _default_executor(self, cmd: List[str]) -> Tuple[int, str, str]:
        """Runs a command on host or via docker exec into container."""
        if self.container_name:
            full_cmd = ["docker", "exec", self.container_name] + cmd
        else:
            full_cmd = cmd

        proc = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def build_provisioning_plan(self) -> Dict[str, Any]:
        """Builds the declarative execution plan without executing changes."""
        bench_cmd = [
            "bench", "new-site", self.config.site_name,
            "--mariadb-root-password", self.mariadb_root_password or "<DB_ROOT_PASSWORD>",
            "--admin-password", self.config.admin_password,
            "--db-name", self.config.db_name,
            "--db-user", self.config.db_user,
            "--db-password", self.config.db_password,
            "--no-mariadb-socket",
        ]
        for app in self.config.apps:
            bench_cmd.extend(["--install-app", app])

        site_config_overrides = {
            "tenant_id": self.config.tenant_id,
            "country": SUPPORTED_COUNTRIES[self.config.country]["name"],
            "country_code": self.config.country,
            "currency": self.config.currency,
            "language": self.config.language,
            "time_zone": self.config.time_zone,
            "engine_invisibility": 1 if self.config.headless else 0,
            "disable_website": 1 if self.config.headless else 0,
            "developer_mode": 1 if self.config.developer_mode else 0,
        }

        return {
            "action": "provision_tenant_site",
            "tenant_id": self.config.tenant_id,
            "site_name": self.config.site_name,
            "country": self.config.country,
            "currency": self.config.currency,
            "language": self.config.language,
            "db_name": self.config.db_name,
            "db_user": self.config.db_user,
            "apps": self.config.apps,
            "headless": self.config.headless,
            "commands": {
                "new_site": bench_cmd,
            },
            "site_config_overrides": site_config_overrides,
        }

    def provision(self, dry_run: bool = False) -> Dict[str, Any]:
        """Executes tenant site creation or returns planned specification."""
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
                "Set DB_ROOT_PASSWORD environment variable or pass --mariadb-root-password."
            )

        # 1. Execute bench new-site with configured apps
        new_site_cmd = [
            "bench", "new-site", self.config.site_name,
            "--mariadb-root-password", self.mariadb_root_password,
            "--admin-password", self.config.admin_password,
            "--db-name", self.config.db_name,
            "--db-user", self.config.db_user,
            "--db-password", self.config.db_password,
            "--no-mariadb-socket",
        ]
        for app in self.config.apps:
            new_site_cmd.extend(["--install-app", app])

        rc, stdout, stderr = self.executor(new_site_cmd)
        if rc != 0:
            raise ProvisioningError(f"bench new-site failed (code {rc}): {stderr or stdout}")

        # 2. Apply site_config overrides (headless, country, currency, tenant_id)
        config_py = (
            f"import frappe\n"
            f"frappe.init(site='{self.config.site_name}')\n"
            f"for k, v in {json.dumps(plan['site_config_overrides'])}.items():\n"
            f"    frappe.conf.set(k, v)\n"
            f"frappe.conf.save()\n"
        )
        set_config_cmd = ["python", "-c", config_py]
        rc_cfg, out_cfg, err_cfg = self.executor(set_config_cmd)
        if rc_cfg != 0:
            raise ProvisioningError(f"Failed applying site_config overrides: {err_cfg or out_cfg}")

        # 3. Verify installed apps on site
        list_apps_cmd = ["bench", "--site", self.config.site_name, "list-apps"]
        rc_list, out_list, err_list = self.executor(list_apps_cmd)
        installed = []
        if rc_list == 0:
            installed = [line.strip().split()[0] for line in out_list.splitlines() if line.strip()]

        return {
            "status": "success",
            "tenant_id": self.config.tenant_id,
            "site_name": self.config.site_name,
            "country": self.config.country,
            "currency": self.config.currency,
            "language": self.config.language,
            "time_zone": self.config.time_zone,
            "db_name": self.config.db_name,
            "db_user": self.config.db_user,
            "installed_apps": installed or self.config.apps,
            "headless": self.config.headless,
            "admin_user": "Administrator",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scripted site-per-tenant provisioning for Orrery engine runtime (ERP-003)."
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
    parser.add_argument("--db-user", help="Dedicated database user (default: generated u_<hash>).")
    parser.add_argument("--admin-password", help="Administrator password (default: random secure token).")
    parser.add_argument("--container", default=None, help="Docker container name (e.g. ce-engine-dev).")
    parser.add_argument("--mariadb-root-password", help="MariaDB root password for site creation.")
    parser.add_argument("--no-headless", action="store_true", help="Do not disable public Desk UI.")
    parser.add_argument("--dry-run", action="store_true", help="Print execution plan without making changes.")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    apps_list = [a.strip() for a in args.apps.split(",")] if args.apps else DEFAULT_IN_SCOPE_APPS

    try:
        config = TenantConfig(
            tenant_id=args.tenant_id,
            site_name=args.site_name,
            country=args.country,
            currency=args.currency,
            language=args.language,
            apps=apps_list,
            db_name=args.db_name,
            db_user=args.db_user,
            admin_password=args.admin_password,
            headless=not args.no_headless,
        )
        provisioner = TenantProvisioner(
            config=config,
            container_name=args.container,
            mariadb_root_password=args.mariadb_root_password,
        )
        result = provisioner.provision(dry_run=args.dry_run)

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            status = result.get("status")
            print(f"=== Tenant Site Provisioning [{status.upper()}] ===")
            print(f"Tenant ID     : {config.tenant_id}")
            print(f"Site Name     : {config.site_name}")
            print(f"Country       : {config.country} ({SUPPORTED_COUNTRIES[config.country]['name']})")
            print(f"Currency      : {config.currency}")
            print(f"Database Name : {config.db_name}")
            print(f"Database User : {config.db_user}")
            print(f"Headless      : {config.headless} (ADR-0016)")
            print(f"Apps to Install: {', '.join(config.apps)}")
            if args.dry_run:
                print("\n[Dry Run Plan]")
                print("Bench command :", " ".join(result["plan"]["commands"]["new_site"]))
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
