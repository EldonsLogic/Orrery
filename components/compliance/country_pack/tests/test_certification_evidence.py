"""Production evidence regressions from CMP-035 review round 3; all approvals are synthetic."""

import unittest

from components.compliance.country_pack import PackValidationError, load_country_pack
from components.compliance.country_pack.tests import test_country_pack_go_live_gate as gate_tests


class TestCertificationEvidence(unittest.TestCase):
    """Exercise the public loader with the existing signed-pack fixture and isolated mutations."""

    def setUp(self) -> None:
        """Reuse synthetic companion writers without inheriting and rerunning the gate suite."""
        self.fixture = gate_tests.TestCountryPackGoLiveGate()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()

    def _refuse(self, version: str, reason: str) -> None:
        """Require a specific production diagnostic while preserving sandbox/test acceptance."""
        with self.assertRaisesRegex(PackValidationError, reason):
            load_country_pack("SA", self.fixture.packs_dir, version=version)
        for environment in ("sandbox", "test"):
            self.fixture._assert_loads(version, environment=environment)

    def test_official_locked_fact_requires_sources_in_signed_secondary_pack(self) -> None:
        f = self.fixture
        v = f._write("certified", "secondary")
        record = f._record(v, "evidence.json")
        record["facts"][0]["status"] = "VERIFIED-OFFICIAL"
        del record["facts"][0]["sources"]
        f._save(v, "evidence.json", record)
        self._refuse(v, "needs a read source")

    def test_official_locked_fact_refuses_future_access_date(self) -> None:
        f = self.fixture
        # Pin the date diagnostic independently of URL validation, then cover the review repro.
        for url in ("https://example.org/synthetic", "http://x"):
            with self.subTest(url=url):
                v = f._write("certified", "secondary")
                record = f._record(v, "evidence.json")
                record["facts"][0].update(status="VERIFIED-OFFICIAL", sources=[
                    {"url": url, "accessed": "9999-01-01"},
                ])
                f._save(v, "evidence.json", record)
                self._refuse(v, "access date in the future")

    def test_sourced_facts_refuse_invalid_calendar_access_dates(self) -> None:
        f = self.fixture
        for label in ("VERIFIED-OFFICIAL", "SECONDARY"):
            with self.subTest(label=label):
                v = f._write("certified", "secondary")
                record = f._record(v, "evidence.json")
                record["facts"][0].update(status=label, sources=[
                    {"url": "https://example.org/synthetic", "accessed": "2026-02-30"},
                ])
                f._save(v, "evidence.json", record)
                self._refuse(v, "access date")

    def test_official_locked_fact_uses_full_shared_source_rule(self) -> None:
        f = self.fixture
        for source in (
            {"url": "http://example.org/synthetic", "accessed": "2026-01-01"},
            {"url": "https://", "accessed": "2026-01-01"},
            {"url": "https://example.org/synthetic", "read": False, "note": "not read"},
            {"url": "https://example.org/synthetic", "read": False, "accessed": "2026-01-01"},
            {"url": "https://example.org/synthetic", "read": True, "accessed": "2026-01-01"},
            {"url": "https://example.org/synthetic", "accessed": "2026-01-01", "note": "snippet"},
        ):
            with self.subTest(source=source):
                v = f._write("certified", "secondary")
                record = f._record(v, "evidence.json")
                record["facts"][0].update(status="VERIFIED-OFFICIAL", sources=[source])
                f._save(v, "evidence.json", record)
                self._refuse(v, "evidence.json.facts")

    def test_unlocked_sourced_facts_use_shared_source_rule(self) -> None:
        f = self.fixture
        for label in ("VERIFIED-OFFICIAL", "SECONDARY"):
            with self.subTest(label=label):
                v = f._write("certified", "secondary")
                record = f._record(v, "evidence.json")
                record["facts"].append({"paths": ["localeDefaults.week.startDay"], "status": label})
                f._save(v, "evidence.json", record)
                self._refuse(v, "needs a read source")

    def test_platform_default_locked_coverage_requires_ref(self) -> None:
        f = self.fixture
        v = f._write("certified", "secondary")
        record = f._record(v, "evidence.json")
        record["facts"][0] = {"paths": record["facts"][0]["paths"], "status": "PLATFORM-DEFAULT"}
        f._save(v, "evidence.json", record)
        self._refuse(v, "PLATFORM-DEFAULT needs a ref")
        # A ref must be a string that is not blank (re-review round 3, Low): truthy non-strings and blanks are refused.
        for bad_ref in (" ", "\t\n", True, ["x"], {"a": 1}, 7):
            with self.subTest(ref=bad_ref):
                record["facts"][0]["ref"] = bad_ref
                f._save(v, "evidence.json", record)
                self._refuse(v, "PLATFORM-DEFAULT needs a ref")
        # Keep current eligibility with a ref; statutory eligibility awaits a founder decision.
        record["facts"][0]["ref"] = "synthetic-platform-choice"
        f._save(v, "evidence.json", record)
        f._assert_loads(v)

    def test_production_refuses_unresolved_policy_lock(self) -> None:
        f = self.fixture
        v = f._write("certified", "secondary")
        pack = f._record(v, "pack.json")
        pack["overridesPolicy"]["lockedPaths"].append("holiday.calendarRefx")
        f._save(v, "pack.json", pack)
        self._refuse(v, "locked path .*holiday.calendarRefx does not exist")

    def test_production_refuses_unverified_index_of_locked_array(self) -> None:
        f = self.fixture
        v = f._write("certified", "secondary")
        pack = f._record(v, "pack.json")
        pack["overridesPolicy"]["overridablePaths"].remove("week.weekendDays")
        pack["overridesPolicy"]["lockedPaths"].append("week.weekendDays")
        f._save(v, "pack.json", pack)
        record = f._record(v, "evidence.json")
        # Valid whole-array evidence isolates the indexed UNVERIFIED refusal from coverage.
        record["facts"][0]["paths"].append("localeDefaults.week.weekendDays")
        f._save(v, "evidence.json", record)
        f._assert_loads(v)
        record["facts"].append({"paths": ["localeDefaults.week.weekendDays[0]"], "status": "UNVERIFIED"})
        f._save(v, "evidence.json", record)
        self._refuse(v, "UNVERIFIED fact on locked path")


if __name__ == "__main__":
    unittest.main()
