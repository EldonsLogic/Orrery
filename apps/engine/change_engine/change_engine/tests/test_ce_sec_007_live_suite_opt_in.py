"""Verify that live MariaDB Suite B requires opt-in and explicit credentials."""

import os
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch

import pymysql


SUITE_PATH = Path(__file__).with_name("test_live_mariadb_suite_b.py")


class TestLiveSuiteOptIn(unittest.TestCase):
    """Exercise Suite B with its real loader and a blocked database connection."""

    def test_suite_skips_without_opt_in(self):
        with patch.dict(os.environ, clear=True), patch.object(
            pymysql, "connect", side_effect=AssertionError("Unexpected database connection")
        ) as connect:
            live_case = runpy.run_path(str(SUITE_PATH))["TestLiveMariaDBSuiteB"]
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(live_case)
            expected_skips = suite.countTestCases()
            result = suite.run(unittest.TestResult())

        connect.assert_not_called()
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
        self.assertGreater(expected_skips, 0)
        self.assertEqual(len(result.skipped), expected_skips)

    def test_opted_in_suite_requires_both_credentials(self):
        for supplied, missing in (("DB_USER", "DB_PASS"), ("DB_PASS", "DB_USER")):
            with self.subTest(missing=missing), patch.dict(
                os.environ, {"CE_LIVE_MARIADB_SUITE_B": "1", supplied: "test-value"}, clear=True
            ), patch.object(
                pymysql, "connect", side_effect=AssertionError("Unexpected database connection")
            ) as connect:
                live_case = runpy.run_path(str(SUITE_PATH))["TestLiveMariaDBSuiteB"]
                with self.assertRaisesRegex(RuntimeError, rf"\b{missing}\b"):
                    live_case.setUpClass()
                connect.assert_not_called()
