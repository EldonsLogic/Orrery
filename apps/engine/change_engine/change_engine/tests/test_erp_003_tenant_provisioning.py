"""
Unit tests for ERP-003: Scripted site-per-tenant creation.

Validates:
1. Tenant configuration validation (tenant_id, site_name, db_name, country).
2. Regional market defaults (SA, AE, EG, QA per ADR-0024).
3. Plan generation with headless engine invisibility (ADR-0016).
4. Automated app installation list (erpnext, hrms, change_engine).
5. Deterministic DB name hashing and security parameters.
6. Execution flow with mocked bench runner and error resilience.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

# Add scripts directory to path to import provision_tenant_site
SCRIPTS_DIR = Path(__file__).resolve().parents[5] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from provision_tenant_site import (
    DEFAULT_IN_SCOPE_APPS,
    SUPPORTED_COUNTRIES,
    ProvisioningError,
    TenantConfig,
    TenantProvisioner,
)


class TestERP003TenantProvisioning(unittest.TestCase):
    def test_01_valid_tenant_config_defaults(self):
        """Standard valid tenant_id defaults to Saudi Arabia (SAR), Arabic, and localhost domain."""
        cfg = TenantConfig(tenant_id="acme-corp")
        self.assertEqual(cfg.tenant_id, "acme-corp")
        self.assertEqual(cfg.country, "SA")
        self.assertEqual(cfg.currency, "SAR")
        self.assertEqual(cfg.language, "ar")
        self.assertEqual(cfg.time_zone, "Asia/Riyadh")
        self.assertEqual(cfg.site_name, "acme-corp.localhost")
        self.assertTrue(cfg.db_name.startswith("_t_"))
        self.assertTrue(cfg.db_user.startswith("u_"))
        self.assertEqual(cfg.apps, DEFAULT_IN_SCOPE_APPS)
        self.assertTrue(cfg.headless)

    def test_02_invalid_tenant_id_rejection(self):
        """Invalid tenant IDs (too short, spaces, special chars) are rejected."""
        invalid_ids = ["a", "ac", "acme corp", "acme$corp", "-invalid", "invalid-", "UPPERCASE!"]
        for bad_id in invalid_ids:
            with self.subTest(tenant_id=bad_id):
                with self.assertRaises(ProvisioningError):
                    TenantConfig(tenant_id=bad_id)

    def test_03_four_phase_1_markets(self):
        """All four ADR-0024 markets (SA, AE, EG, QA) configure correct currencies and timezones."""
        expected = {
            "SA": ("SAR", "Asia/Riyadh"),
            "AE": ("AED", "Asia/Dubai"),
            "EG": ("EGP", "Africa/Cairo"),
            "QA": ("QAR", "Asia/Qatar"),
        }
        for country_code, (exp_cur, exp_tz) in expected.items():
            cfg = TenantConfig(tenant_id=f"tenant-{country_code.lower()}", country=country_code)
            self.assertEqual(cfg.currency, exp_cur)
            self.assertEqual(cfg.time_zone, exp_tz)
            self.assertEqual(cfg.language, "ar")

    def test_04_unsupported_country_rejection(self):
        """Non-Phase-1 markets raise ProvisioningError."""
        with self.assertRaises(ProvisioningError) as ctx:
            TenantConfig(tenant_id="tenant-us", country="US")
        self.assertIn("Unsupported country", str(ctx.exception))

    def test_05_plan_generation_commands_and_headless_flags(self):
        """Plan generates exact bench new-site commands and sets ADR-0016 headless invisibility."""
        cfg = TenantConfig(
            tenant_id="riyadh-trading",
            country="SA",
            site_name="riyadh.tenants.local",
            headless=True,
        )
        provisioner = TenantProvisioner(
            config=cfg,
            container_name="ce-engine-dev",
            mariadb_root_password="mock_root_pwd",
        )
        plan = provisioner.build_provisioning_plan()

        self.assertEqual(plan["action"], "provision_tenant_site")
        self.assertEqual(plan["site_name"], "riyadh.tenants.local")

        cmd = plan["commands"]["new_site"]
        self.assertEqual(cmd[0], "bench")
        self.assertEqual(cmd[1], "new-site")
        self.assertEqual(cmd[2], "riyadh.tenants.local")
        self.assertIn("--mariadb-root-password", cmd)
        self.assertIn("--no-mariadb-socket", cmd)

        # In-scope apps must be installed during site creation
        for app in DEFAULT_IN_SCOPE_APPS:
            self.assertIn(app, cmd)

        # Headless overrides
        overrides = plan["site_config_overrides"]
        self.assertEqual(overrides["engine_invisibility"], 1)
        self.assertEqual(overrides["disable_website"], 1)
        self.assertEqual(overrides["currency"], "SAR")
        self.assertEqual(overrides["country"], "Saudi Arabia")

    def test_06_mocked_successful_provisioning_flow(self):
        """Simulates full provisioning lifecycle with a mock executor."""
        calls = []

        def mock_executor(cmd):
            calls.append(cmd)
            # When list-apps is called, return simulated installed apps
            if len(cmd) >= 4 and cmd[0] == "bench" and cmd[3] == "list-apps":
                return 0, "frappe\nerpnext\nhrms\nchange_engine\n", ""
            return 0, "OK", ""

        cfg = TenantConfig(tenant_id="dubai-logistics", country="AE")
        provisioner = TenantProvisioner(
            config=cfg,
            mariadb_root_password="secret_root_pwd",
            executor=mock_executor,
        )
        result = provisioner.provision(dry_run=False)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["tenant_id"], "dubai-logistics")
        self.assertEqual(result["country"], "AE")
        self.assertEqual(result["currency"], "AED")
        self.assertEqual(result["installed_apps"], ["frappe", "erpnext", "hrms", "change_engine"])

        # Check call sequence: 1. new-site, 2. set config, 3. list-apps
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0][1], "new-site")
        self.assertEqual(calls[1][0], "python")
        self.assertEqual(calls[2][1], "--site")

    def test_07_provisioning_failure_fail_closed(self):
        """bench new-site failure raises ProvisioningError fail-closed."""
        def failing_executor(cmd):
            return 1, "", "Access denied for user 'root'@'localhost'"

        cfg = TenantConfig(tenant_id="cairo-retail", country="EG")
        provisioner = TenantProvisioner(
            config=cfg,
            mariadb_root_password="wrong_password",
            executor=failing_executor,
        )
        with self.assertRaises(ProvisioningError) as ctx:
            provisioner.provision(dry_run=False)
        self.assertIn("Access denied", str(ctx.exception))

    def test_08_cli_dry_run_json_output(self):
        """CLI dry-run produces parseable JSON plan."""
        cli_script = SCRIPTS_DIR / "provision_tenant_site.py"
        res = subprocess.run(
            [
                sys.executable, str(cli_script),
                "--tenant-id", "doha-traders",
                "--country", "QA",
                "--dry-run",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "dry_run")
        self.assertEqual(data["plan"]["currency"], "QAR")
        self.assertEqual(data["plan"]["country"], "QA")


if __name__ == "__main__":
    unittest.main()
