"""Go-live gate tests for the country pack loader (CMP-034, review of PR #255 item 1).

Outside sandbox and test, a pack below `certified` or with `evidenceStatus: unverified` is refused.
`allow_test_packs` stays orthogonal: `testOnly` packs are refused unless allowed, in every environment.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from components.compliance.country_pack import (
    CountryPackError,
    PackValidationError,
    load_country_pack,
    resolve_country_pack,
)

SAMPLE_PACKS_DIR = Path(__file__).resolve().parent / "sample_packs"
BELOW_CERTIFIED = ("draft", "tested", "reviewed")
GO_LIVE_STATUSES = ("certified", "regulated")


class TestCountryPackGoLiveGate(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.packs_dir = Path(self._tmp.name)
        self.base = load_country_pack(
            "SA", SAMPLE_PACKS_DIR, version="0.1.0", allow_test_packs=True, environment="test"
        )
        self._next_minor = 1

    def _write(self, status: str, evidence: str, test_only: bool = False) -> str:
        """Write an in-memory variant of the sample pack to a temp packs root; return its version."""
        version = f"0.{self._next_minor}.0"
        self._next_minor += 1
        pack = copy.deepcopy(self.base)
        pack.update({"status": status, "evidenceStatus": evidence, "testOnly": test_only, "version": version})
        pdir = self.packs_dir / "sa" / version
        pdir.mkdir(parents=True)
        (pdir / "pack.json").write_text(json.dumps(pack), encoding="utf-8")
        return version

    def _assert_refused(self, version: str, **kwargs) -> None:
        with self.assertRaises(PackValidationError):
            load_country_pack("SA", self.packs_dir, version=version, **kwargs)
        with self.assertRaises(PackValidationError):
            resolve_country_pack("SA", self.packs_dir, version=version, **kwargs)

    def _assert_loads(self, version: str, **kwargs) -> None:
        self.assertEqual(load_country_pack("SA", self.packs_dir, version=version, **kwargs)["version"], version)
        self.assertEqual(resolve_country_pack("SA", self.packs_dir, version=version, **kwargs)["version"], version)

    def test_production_refuses_below_certified(self) -> None:
        for status in BELOW_CERTIFIED:
            with self.subTest(status=status):
                v = self._write(status, "verified_official")
                self._assert_refused(v, environment="production")
                self._assert_refused(v)  # default environment is production

    def test_production_refuses_unverified_evidence(self) -> None:
        for status in GO_LIVE_STATUSES:
            with self.subTest(status=status):
                v = self._write(status, "unverified")
                self._assert_refused(v, environment="production")
                self._assert_refused(v)

    def test_production_refusal_message_names_the_reason(self) -> None:
        v = self._write("draft", "unverified")
        with self.assertRaises(PackValidationError) as ctx:
            load_country_pack("SA", self.packs_dir, version=v)
        msg = str(ctx.exception)
        self.assertIn("production", msg)
        self.assertIn("draft", msg)
        self.assertIn("unverified", msg)

    def test_production_accepts_certified_verified_pack(self) -> None:
        for status in GO_LIVE_STATUSES:
            for evidence in ("verified_official", "secondary"):
                with self.subTest(status=status, evidence=evidence):
                    v = self._write(status, evidence)
                    self._assert_loads(v, environment="production")
                    self._assert_loads(v)

    def test_sandbox_and_test_accept_draft_tested_unverified(self) -> None:
        for env in ("sandbox", "test"):
            for status in BELOW_CERTIFIED:
                with self.subTest(environment=env, status=status):
                    v = self._write(status, "unverified")
                    self._assert_loads(v, environment=env)

    def test_unknown_environment_refused(self) -> None:
        v = self._write("certified", "verified_official")
        for env in ("prod", "PRODUCTION", "staging", "", None, 1):
            with self.subTest(environment=env):
                with self.assertRaises(CountryPackError):
                    load_country_pack("SA", self.packs_dir, version=v, environment=env)
                with self.assertRaises(CountryPackError):
                    resolve_country_pack("SA", self.packs_dir, version=v, environment=env)

    def test_allow_test_packs_unchanged_and_orthogonal(self) -> None:
        certified_test_only = self._write("certified", "verified_official", test_only=True)
        draft_test_only = self._write("draft", "unverified", test_only=True)
        for env in ("sandbox", "test", "production"):
            with self.subTest(environment=env):
                # testOnly is refused unless allowed, in every environment.
                self._assert_refused(certified_test_only, environment=env)
                self._assert_refused(draft_test_only, environment=env)
                self._assert_loads(certified_test_only, environment=env, allow_test_packs=True)
        self._assert_loads(draft_test_only, environment="sandbox", allow_test_packs=True)
        # allow_test_packs does not open the go-live gate.
        self._assert_refused(draft_test_only, environment="production", allow_test_packs=True)

    def test_unpinned_production_load_does_not_fall_back_past_a_draft(self) -> None:
        self._write("certified", "verified_official")  # 0.1.0
        self._write("draft", "unverified")  # 0.2.0, highest
        with self.assertRaises(PackValidationError):
            load_country_pack("SA", self.packs_dir)
        self.assertEqual(load_country_pack("SA", self.packs_dir, environment="sandbox")["version"], "0.2.0")


if __name__ == "__main__":
    unittest.main()
