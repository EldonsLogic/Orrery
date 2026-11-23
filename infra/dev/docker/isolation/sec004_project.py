"""SEC-004 harness only: the one rule for which Compose project names the isolation bench may use.

Shared by `run_isolation_suite.py` (host) and `raw_engine_wsgi.py` (inside the engine container, where it
is mounted next to it). Standard library only, so it imports in both places and offline tests.

The name must be exactly `sec004` or `sec004-<words>` (`-` or `_` separated, lower-case letters and
digits): the SEC-004 harness's own default (`sec004-isolation`) and CI (`sec004-ci-isolation`) match.
A name that merely contains the token (`prod-sec004`, `sec004prod`) does not, so a shared or production
stack can never be taken for the throwaway bench.
"""

import re

PROJECT_RE = re.compile(r"^sec004(?:[-_][a-z0-9]+)*$")


def is_sec004_project(name: str) -> bool:
    return bool(PROJECT_RE.fullmatch(name or ""))
