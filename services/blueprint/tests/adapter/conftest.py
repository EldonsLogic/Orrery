"""Fixtures for the engine adapter conformance suite (contracts/engine-adapter.md section 14, BPL-025).

`h` is a fresh harness per test. By default it wraps the in-memory fake; set ADAPTER_HARNESS=module:factory to run
the same suite against another adapter (the real one, BPL-012). Every response of every test is validated against its
schema (ADP-C-001), checked for error shape (ADP-C-005) and scanned for engine leaks (ADP-C-006); events are scanned
when the test ends.
"""
import json
import re

import pytest

from adapter.contract import canon, response_validator
from adapter.harness import make_harness

DENYLIST = [r"(?i)frappe|erpnext", r"Traceback", r"(?i)\b(alter|drop|create)\s+table\b", r"(?i)\bselect\s.+\bfrom\b",
            r"\.py\b", r"/home/", r"/var/"]
RETRYABLE = {"site_not_ready", "plan_token_invalid", "concurrent_change", "timeout", "engine_unavailable"}  # section 6
DETAIL_KEYS = {"stepSeq", "pointer", "postConditionId", "reasonCode", "fields", "limit", "allowed", "actual", "supported"}


def scrub(value):
    """Drop the internal ids section 12 excludes from the scan: adapterId and engineTarget.adapter."""
    if isinstance(value, dict):
        return {k: ("<internal>" if k == "adapterId" or (k == "adapter" and isinstance(v, str)) else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def leaks(value, extra=()) -> list[str]:
    text = json.dumps(scrub(value), ensure_ascii=False)
    return [p for p in [*DENYLIST, *extra] if re.search(p, text)]


def check_error(err: dict):
    code = err["code"]
    assert err["messageKey"] == "errors.adapter." + code
    assert set(err.get("details", {})) <= DETAIL_KEYS
    if code != "internal_error":
        assert err["retryable"] == (code in RETRYABLE), code


class CheckedHarness:
    """Delegates to the harness and checks every response (ADP-C-001, 005, 006)."""

    def __init__(self, inner):
        self.inner, self.violations = inner, []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def call(self, operation, context, input):  # noqa: A002
        resp = self.inner.call(operation, context, input)
        errors = list(response_validator(operation).iter_errors(resp))
        assert not errors, f"{operation} response breaks its schema: {errors[0].message[:200]}"
        err = resp["error"] if not resp["ok"] else resp["result"].get("error") if isinstance(resp["result"], dict) else None
        if err:
            check_error(err)
        found = leaks(resp)
        assert not found, f"{operation} response leaks {found}"
        return resp


@pytest.fixture
def h():
    harness = CheckedHarness(make_harness())
    yield harness
    for event in harness.events():
        assert not leaks(event), event
        assert "tenant" not in json.dumps(event["data"]).lower()
    harness.reset()


def optional(fn, *args, **kwargs):
    """Call a harness extension the conformance run needs. A harness that lacks it FAILS the run: a missing
    capability must never turn a required test into a skip (README.md lists the extensions)."""
    try:
        return fn(*args, **kwargs)
    except NotImplementedError:
        pytest.fail(f"INCOMPLETE CONFORMANCE RUN: the harness does not implement {getattr(fn, '__name__', 'an extension')}, "
                    "which a required ADP-C test needs", pytrace=False)


_skipped: list[str] = []


def pytest_runtest_logreport(report):
    if report.skipped and "adapter/" in report.nodeid.replace("\\", "/"):
        _skipped.append(report.nodeid)


def pytest_sessionfinish(session, exitstatus):
    """A conformance run with any skipped test is not a pass: it is explicitly incomplete."""
    if _skipped and session.exitstatus == 0:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        print(f"\nINCOMPLETE CONFORMANCE RUN: {len(_skipped)} test(s) skipped, so this run does not count as a pass: {_skipped[:5]}")


def event_types(h, since=0):
    return [e["type"] for e in h.events()[since:]]


def assert_no_effect(h, tenant, before, events_before, expect=()):
    """Section 14 'no effect': no change to engine data (export hash, retained, site status), and the events are exactly
    the ones 8.2 lists for the case (`expect`, in order, each once): none, one permission.denied or one apply_failed."""
    from adapter import testkit as t
    assert t.snapshot(h, tenant) == before
    assert event_types(h, events_before) == list(expect)
