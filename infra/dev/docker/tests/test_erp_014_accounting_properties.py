"""Run the ERP-014 accounting property tests from the dev bench test step.

The suite lives with the engine tests (apps/engine/.../tests/test_erp_014_accounting_properties.py).
CI already runs ``unittest discover`` here, so this loader brings the pure layer into CI; the live layer
skips unless ERP014_COMPOSE_PROJECT and ERP014_SITE name a disposable synthetic site.
"""
import importlib.util
from pathlib import Path

_SUITE = (Path(__file__).resolve().parents[4] / "apps" / "engine" / "change_engine" / "change_engine"
          / "tests" / "test_erp_014_accounting_properties.py")


def load_tests(loader, tests, pattern):
    spec = importlib.util.spec_from_file_location("erp_014_accounting_properties", _SUITE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tests.addTests(loader.loadTestsFromModule(module))
    return tests
