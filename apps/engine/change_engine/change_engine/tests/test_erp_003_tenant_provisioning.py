"""
Unit tests for ERP-003: Scripted site-per-tenant creation.

Validates:
1. Tenant configuration validation (DNS-safe tenant_id, strict RFC 1123 site_name, apps, db_name, country).
2. Rejection of injection payloads (including payloads ending in .localhost) and invalid hostnames.
3. Regional market defaults (SA, AE, EG, QA per ADR-0024).
4. Plan generation with redacted credentials, v15-compatible flags, and developer_mode=0 default.
5. Absence of fabricated engine-invisibility keys (ADR-0016 is gateway/network-enforced, not site_config).
6. Safe site_config writes via `bench --site <site> set-config` (no `python -c` or `frappe.conf.save()`).
7. Secret handling: no secrets on host CLI argv, env forwarding via docker compose exec, admin password returned or written to 0600 credentials file, secret masking on errors.
8. Fail-closed verification on missing root password, new-site failure, set-config failure, and list-apps failure/mismatch.
9. Compose runtime targeting (`docker compose exec -T` via provision_tenant_site.py and provision_tenant.sh; no `ce-engine-dev`).
"""

import json
import os
import secrets
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[5]
SCRIPTS_DIR = REPO_ROOT / "scripts"
DOCKER_DIR = REPO_ROOT / "infra" / "dev" / "docker"
sys.path.insert(0, str(SCRIPTS_DIR))

from provision_tenant_site import (  # noqa: E402
    DEFAULT_IN_SCOPE_APPS,
    ProvisioningError,
    TenantConfig,
    TenantProvisioner,
)


class TestERP003TenantProvisioning(unittest.TestCase):
    def test_01_valid_tenant_config_defaults(self):
        """Standard valid tenant_id defaults to SA (SAR), Arabic, .localhost domain, and developer_mode=False."""
        cfg = TenantConfig(tenant_id="acme-corp")
        self.assertEqual(cfg.tenant_id, "acme-corp")
        self.assertEqual(cfg.country, "SA")
        self.assertEqual(cfg.currency, "SAR")
        self.assertEqual(cfg.language, "ar")
        self.assertEqual(cfg.time_zone, "Asia/Riyadh")
        self.assertEqual(cfg.site_name, "acme-corp.localhost")
        self.assertTrue(cfg.db_name.startswith("_t_"))
        self.assertEqual(cfg.apps, DEFAULT_IN_SCOPE_APPS)
        self.assertFalse(cfg.developer_mode)

    def test_02_invalid_tenant_id_rejection_including_underscores(self):
        """Invalid tenant IDs (underscores, too short, whitespace, injection chars) are rejected."""
        invalid_ids = [
            "a",
            "ac",
            "acme_corp",
            "tenant_01",
            "acme corp",
            "acme\n",
            "acme$corp",
            "-invalid",
            "invalid-",
            "upper;id",
            "a" * 64,
        ]
        for bad_id in invalid_ids:
            with self.subTest(tenant_id=bad_id):
                with self.assertRaises(ProvisioningError):
                    TenantConfig(tenant_id=bad_id)

    def test_03_strict_site_name_validation_and_injection_rejection(self):
        """Reject injection payloads ending in .localhost and all malformed hostnames."""
        valid_sites = [
            "acme-corp.localhost",
            "riyadh.tenants.local",
            "sub-1.tenant-a.example",
        ]
        for site in valid_sites:
            with self.subTest(valid_site=site):
                cfg = TenantConfig(tenant_id="valid-tenant", site_name=site)
                self.assertEqual(cfg.site_name, site)

        invalid_sites = [
            "'; import os; os.system('id'); '.localhost",
            "\"`id`\".localhost",
            "$(whoami).localhost",
            "bad\nname.localhost",
            "bad name.localhost",
            "bad_host.localhost",
            ".localhost",
            "localhost",
            "foo..localhost",
            "-bad.localhost",
            "bad-.localhost",
            "127.0.0.1",
            ("a" * 64) + ".localhost",
            ("ab." * 85) + "com",
        ]
        for bad_site in invalid_sites:
            with self.subTest(invalid_site=bad_site):
                with self.assertRaises(ProvisioningError):
                    TenantConfig(tenant_id="valid-tenant", site_name=bad_site)

    def test_04_other_input_validation_guards(self):
        """Reject invalid country, apps, db_name, db_host, compose_project, and service_name."""
        with self.assertRaises(ProvisioningError):
            TenantConfig(tenant_id="tenant-us", country="US")
        with self.assertRaises(ProvisioningError):
            TenantConfig(tenant_id="tenant-sa", apps=[])
        with self.assertRaises(ProvisioningError):
            TenantConfig(tenant_id="tenant-sa", apps=["erpnext; rm -rf /"])
        with self.assertRaises(ProvisioningError):
            TenantConfig(tenant_id="tenant-sa", db_name="bad-db-name")
        with self.assertRaises(ProvisioningError):
            TenantConfig(tenant_id="tenant-sa", db_host="mariadb;id")

        cfg = TenantConfig(tenant_id="tenant-sa")
        with self.assertRaises(ProvisioningError):
            TenantProvisioner(config=cfg, compose_project="bad project!")
        with self.assertRaises(ProvisioningError):
            TenantProvisioner(config=cfg, service_name="engine;id")

    def test_05_four_phase_1_markets(self):
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

    def test_06_plan_redacts_secrets_uses_v15_flags_and_omits_fake_invisibility_keys(self):
        """Dry-run plan redacts passwords, uses v15 flags, sets developer_mode=0, and omits fake keys."""
        root_secret = "test-root-" + secrets.token_hex(8)
        admin_secret = "test-admin-" + secrets.token_hex(8)
        db_secret = "test-db-" + secrets.token_hex(8)

        cfg = TenantConfig(
            tenant_id="riyadh-trading",
            country="SA",
            site_name="riyadh.tenants.local",
            admin_password=admin_secret,
            db_password=db_secret,
        )
        provisioner = TenantProvisioner(
            config=cfg,
            compose_project="platform-local",
            mariadb_root_password=root_secret,
        )
        result = provisioner.provision(dry_run=True)
        serialized = json.dumps(result)

        # No secrets leaked in dry-run plan
        self.assertNotIn(root_secret, serialized)
        self.assertNotIn(admin_secret, serialized)
        self.assertNotIn(db_secret, serialized)

        plan = result["plan"]
        cmd = plan["commands"]["new_site"]
        self.assertEqual(cmd[:3], ["bench", "new-site", "riyadh.tenants.local"])
        self.assertIn("--db-host", cmd)
        self.assertIn("--mariadb-user-host-login-scope=%", cmd)
        self.assertIn("--db-root-password", cmd)
        self.assertNotIn("--mariadb-root-password", cmd)
        self.assertNotIn("--no-mariadb-socket", cmd)
        self.assertNotIn("--db-user", cmd)

        for app in DEFAULT_IN_SCOPE_APPS:
            self.assertIn(app, cmd)

        # No fabricated engine-invisibility keys; developer_mode defaults to 0
        overrides = plan["site_config_overrides"]
        self.assertNotIn("engine_invisibility", overrides)
        self.assertNotIn("disable_website", overrides)
        self.assertEqual(overrides["developer_mode"], 0)
        self.assertEqual(overrides["currency"], "SAR")
        self.assertEqual(overrides["country"], "Saudi Arabia")

        # set_config plan uses `bench --site ... set-config`, never python -c
        set_cfg_cmds = plan["commands"]["set_config"]
        self.assertTrue(all(c[:4] == ["bench", "--site", "riyadh.tenants.local", "set-config"] for c in set_cfg_cmds))
        self.assertNotIn("frappe.conf.save", serialized)
        self.assertNotIn("python", serialized)

    def test_07_live_provisioning_uses_set_config_env_secrets_and_returns_admin_password(self):
        """Live flow keeps secrets off command argv, uses bench set-config, and returns admin_password."""
        calls = []
        root_secret = "test-root-" + secrets.token_hex(8)

        def mock_executor(cmd, env_overrides=None):
            calls.append((cmd, env_overrides or {}))
            if cmd[:4] == ["bench", "--site", "dubai-logistics.localhost", "list-apps"]:
                return 0, json.dumps({"dubai-logistics.localhost": ["frappe", "erpnext", "hrms", "change_engine"]}), ""
            return 0, "OK", ""

        cfg = TenantConfig(tenant_id="dubai-logistics", country="AE")
        provisioner = TenantProvisioner(
            config=cfg,
            mariadb_root_password=root_secret,
            executor=mock_executor,
        )
        result = provisioner.provision(dry_run=False)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["installed_apps"], ["frappe", "erpnext", "hrms", "change_engine"])
        self.assertTrue(result["admin_password"])
        self.assertFalse(result["developer_mode"])

        # First call: sh -ec invoking bench new-site with secrets strictly in env_overrides, NOT in cmd argv
        new_site_cmd, new_site_env = calls[0]
        self.assertEqual(new_site_cmd[:2], ["sh", "-ec"])
        self.assertEqual(new_site_env["DB_ROOT_PASSWORD"], root_secret)
        self.assertEqual(new_site_env["ADMIN_PASSWORD"], result["admin_password"])
        self.assertEqual(new_site_env["DB_PASSWORD"], result["db_password"])
        flat_cmd = " ".join(new_site_cmd)
        self.assertNotIn(root_secret, flat_cmd)
        self.assertNotIn(result["admin_password"], flat_cmd)
        self.assertNotIn(result["db_password"], flat_cmd)

        # Middle calls: bench --site <site> set-config (no python -c or frappe.conf.save)
        cfg_calls = [cmd for cmd, _ in calls[1:-1]]
        self.assertEqual(len(cfg_calls), 7)
        for cmd in cfg_calls:
            self.assertEqual(cmd[:4], ["bench", "--site", "dubai-logistics.localhost", "set-config"])
        self.assertIn(
            ["bench", "--site", "dubai-logistics.localhost", "set-config", "--parse", "developer_mode", "0"],
            cfg_calls,
        )

        # Final call: bench --site <site> list-apps --format json
        self.assertEqual(
            calls[-1][0],
            ["bench", "--site", "dubai-logistics.localhost", "list-apps", "--format", "json"],
        )

    def test_08_fail_closed_behaviors_and_error_secret_masking(self):
        """Missing root password, failed set-config, failed/mismatched list-apps all fail closed."""
        cfg = TenantConfig(tenant_id="cairo-retail", country="EG")

        # 1. Missing root password fails closed without calling executor
        called = []
        no_pwd_prov = TenantProvisioner(
            config=cfg,
            mariadb_root_password="",
            executor=lambda cmd: called.append(cmd) or (0, "", ""),
        )
        with self.assertRaises(ProvisioningError):
            no_pwd_prov.provision(dry_run=False)
        self.assertEqual(called, [])

        # 2. bench new-site error redacts leaked passwords
        root_secret = "test-root-" + secrets.token_hex(8)
        fail_new_site = TenantProvisioner(
            config=cfg,
            mariadb_root_password=root_secret,
            executor=lambda cmd: (1, "", f"failed with {root_secret}"),
        )
        with self.assertRaises(ProvisioningError) as ctx:
            fail_new_site.provision(dry_run=False)
        self.assertNotIn(root_secret, str(ctx.exception))
        self.assertIn("<REDACTED>", str(ctx.exception))

        # 3. set-config failure raises ProvisioningError
        def fail_on_set_config(cmd):
            if "set-config" in cmd:
                return 1, "", "config write error"
            return 0, "OK", ""

        fail_cfg_prov = TenantProvisioner(
            config=cfg,
            mariadb_root_password=root_secret,
            executor=fail_on_set_config,
        )
        with self.assertRaises(ProvisioningError) as ctx_cfg:
            fail_cfg_prov.provision(dry_run=False)
        self.assertIn("Failed applying site_config", str(ctx_cfg.exception))

        # 4. list-apps failure does NOT fall back to requested apps (must fail closed)
        def fail_on_list_apps(cmd):
            if "list-apps" in cmd:
                return 1, "", "site missing"
            return 0, "OK", ""

        fail_list_prov = TenantProvisioner(
            config=cfg,
            mariadb_root_password=root_secret,
            executor=fail_on_list_apps,
        )
        with self.assertRaises(ProvisioningError) as ctx_list:
            fail_list_prov.provision(dry_run=False)
        self.assertIn("list-apps failed", str(ctx_list.exception))

        # 5. list-apps missing a requested app fails closed
        def missing_app_list(cmd):
            if "list-apps" in cmd:
                return 0, json.dumps({"cairo-retail.localhost": ["frappe", "erpnext"]}), ""
            return 0, "OK", ""

        missing_app_prov = TenantProvisioner(
            config=cfg,
            mariadb_root_password=root_secret,
            executor=missing_app_list,
        )
        with self.assertRaises(ProvisioningError) as ctx_missing:
            missing_app_prov.provision(dry_run=False)
        self.assertIn("missing requested apps", str(ctx_missing.exception))

        # 6. list-apps invalid JSON fails closed
        def bad_json_list(cmd):
            if "list-apps" in cmd:
                return 0, "not-json", ""
            return 0, "OK", ""

        bad_json_prov = TenantProvisioner(
            config=cfg,
            mariadb_root_password=root_secret,
            executor=bad_json_list,
        )
        with self.assertRaises(ProvisioningError):
            bad_json_prov.provision(dry_run=False)

    def test_09_docker_compose_exec_targets_project_without_cli_secrets(self):
        """_default_executor uses `docker compose exec -T -e VAR` and never targets ce-engine-dev."""
        root_secret = "test-root-" + secrets.token_hex(8)
        admin_secret = "test-admin-" + secrets.token_hex(8)
        cfg = TenantConfig(tenant_id="doha-traders", country="QA", admin_password=admin_secret)
        provisioner = TenantProvisioner(
            config=cfg,
            compose_project="platform-test",
            mariadb_root_password=root_secret,
        )

        recorded = []

        def fake_subprocess_run(cmd, **kwargs):
            recorded.append((cmd, kwargs))
            proc = mock.MagicMock()
            proc.returncode = 0
            if "list-apps" in cmd:
                proc.stdout = json.dumps({"doha-traders.localhost": ["frappe", "erpnext", "hrms", "change_engine"]})
            else:
                proc.stdout = "OK"
            proc.stderr = ""
            return proc

        with mock.patch("provision_tenant_site.subprocess.run", side_effect=fake_subprocess_run):
            result = provisioner.provision(dry_run=False)

        self.assertEqual(result["status"], "success")
        first_cmd, first_kwargs = recorded[0]
        self.assertEqual(first_cmd[:2], ["docker", "compose"])
        self.assertIn("--project-name", first_cmd)
        self.assertIn("platform-test", first_cmd)
        self.assertIn("exec", first_cmd)
        self.assertIn("-T", first_cmd)
        self.assertIn("engine", first_cmd)
        self.assertNotIn("ce-engine-dev", " ".join(first_cmd))
        # Forwarded via -e VARNAME only; secret values are in env, never in argv
        self.assertIn("-e", first_cmd)
        self.assertNotIn(root_secret, " ".join(first_cmd))
        self.assertNotIn(admin_secret, " ".join(first_cmd))
        self.assertNotIn(result["db_password"], " ".join(first_cmd))
        self.assertEqual(first_kwargs["env"]["DB_ROOT_PASSWORD"], root_secret)
        self.assertEqual(first_kwargs["env"]["ADMIN_PASSWORD"], admin_secret)

    def test_10_cli_dry_run_and_credentials_file_permissions(self):
        """CLI dry-run redacts secrets; live CLI with --credentials-file writes 0600 file and omits secrets from stdout."""
        cli_script = SCRIPTS_DIR / "provision_tenant_site.py"
        secret_probe = "test-probe-" + secrets.token_hex(8)

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
            check=False,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn(secret_probe, res.stdout)
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "dry_run")
        self.assertEqual(data["plan"]["currency"], "QAR")
        self.assertEqual(data["plan"]["country"], "QA")
        self.assertEqual(data["plan"]["site_config_overrides"]["developer_mode"], 0)

        # Verify main() --credentials-file writes mode 0600 file and omits secrets from stdout JSON
        import io
        from contextlib import redirect_stdout
        from provision_tenant_site import main as cli_main

        def fake_subprocess_run(cmd, **kwargs):
            proc = mock.MagicMock()
            proc.returncode = 0
            if "list-apps" in cmd:
                proc.stdout = json.dumps({"doha-traders.localhost": ["frappe", "erpnext", "hrms", "change_engine"]})
            else:
                proc.stdout = "OK"
            proc.stderr = ""
            return proc

        with tempfile.TemporaryDirectory() as tmpdir:
            creds_path = Path(tmpdir) / "tenant-creds.json"
            stdout_buf = io.StringIO()
            with mock.patch("provision_tenant_site.subprocess.run", side_effect=fake_subprocess_run), \
                 mock.patch.dict(os.environ, {"DB_ROOT_PASSWORD": secret_probe}), \
                 redirect_stdout(stdout_buf):
                rc = cli_main([
                    "--tenant-id", "doha-traders",
                    "--country", "QA",
                    "--compose-project", "platform-test",
                    "--credentials-file", str(creds_path),
                    "--json",
                ])
            self.assertEqual(rc, 0)
            out_json = json.loads(stdout_buf.getvalue())
            self.assertEqual(out_json["status"], "success")
            self.assertNotIn("admin_password", out_json)
            self.assertNotIn("db_password", out_json)
            self.assertEqual(out_json["credentials_file"], str(creds_path))
            mode = stat.S_IMODE(os.stat(creds_path).st_mode)
            self.assertEqual(mode, 0o600)
            written = json.loads(creds_path.read_text(encoding="utf-8"))
            self.assertTrue(written["admin_password"])
            self.assertTrue(written["db_password"])

    def test_credentials_file_refuses_existing_files_and_symlinks(self):
        """Credential storage never overwrites an existing file or follows a symlink."""
        from provision_tenant_site import _write_credentials_file
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "existing"
            target.write_text("preserve", encoding="utf-8")
            link = Path(tmpdir) / "link"
            link.symlink_to(target)
            for path in (target, link):
                with self.assertRaises(FileExistsError):
                    _write_credentials_file(path, {"password": "secret"})
            self.assertEqual(target.read_text(encoding="utf-8"), "preserve")

    def test_cli_rejects_password_arguments(self):
        """Callers supply passwords in the environment, not process arguments."""
        from provision_tenant_site import parse_args
        for option in ("--admin-password", "--mariadb-root-password"):
            with self.assertRaises(SystemExit):
                parse_args(["--tenant-id", "tenant-one", option, "secret"])

    def test_11_wrapper_script_targets_compose_project_and_rejects_missing_project(self):
        """infra/dev/docker/provision_tenant.sh requires COMPOSE_PROJECT_NAME and has no ce-engine-dev reference."""
        wrapper = DOCKER_DIR / "provision_tenant.sh"
        wrapper_text = wrapper.read_text(encoding="utf-8")
        self.assertNotIn("ce-engine-dev", wrapper_text)
        self.assertIn("COMPOSE_PROJECT_NAME", wrapper_text)

        env_no_project = os.environ.copy()
        env_no_project.pop("COMPOSE_PROJECT_NAME", None)
        missing_res = subprocess.run(
            ["bash", str(wrapper), "doha-traders", "QA"],
            env=env_no_project,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(missing_res.returncode, 0)
        self.assertIn("COMPOSE_PROJECT_NAME", missing_res.stderr)

        env_with_project = os.environ.copy()
        env_with_project["COMPOSE_PROJECT_NAME"] = "platform-test"
        dry_res = subprocess.run(
            ["bash", str(wrapper), "doha-traders", "QA", "", "--dry-run", "--json"],
            env=env_with_project,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(dry_res.returncode, 0, dry_res.stderr)
        payload = json.loads(dry_res.stdout)
        self.assertEqual(payload["status"], "dry_run")
        self.assertEqual(payload["plan"]["compose_project"], "platform-test")
        self.assertEqual(payload["plan"]["service"], "engine")
        self.assertEqual(payload["plan"]["site_name"], "doha-traders.localhost")


if __name__ == "__main__":
    unittest.main()
