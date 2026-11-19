"""Allow-listed commands, scrubbed environment, wall-clock timeout. Candidate text never becomes a command line.

The allow-list maps a fixed name to a fixed argv template; the only candidate-controlled part is one validated
relative test path. Tests may replace the allow-list (the injection point) to run a fake command.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import errors as E

# name -> argv template; "{path}" is replaced by the validated relative test path.
# pytest is isolated from anything the component ships (SEC-010 review H8): an empty config file (-c devnull) so
# pytest.ini, tox.ini, setup.cfg and pyproject.toml are never read, no addopts, no conftest.py, no doctest
# collection of text files, no cache, and no plugin auto-loading (see scrubbed_env).
ALLOWED = {
    "pytest": [sys.executable, "-m", "pytest", "-q", "-c", os.devnull, "--rootdir", ".", "--noconftest",
               "-o", "addopts=", "-p", "no:cacheprovider", "-p", "no:doctest", "{path}"],
}
OUTPUT_TAIL = 2000
MAX_WRITE_BYTES = 10_000_000


@dataclass(frozen=True)
class CmdResult:
    returncode: int | None
    timed_out: bool
    tail: str


def scrubbed_env(home: Path, workdir: Path) -> dict:
    """Only what a test run needs. No inherited variables: no secrets, tokens, proxies or network settings."""
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "TMPDIR": str(home),
        "LANG": "C.UTF-8",
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(workdir),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }


def _limits() -> None:  # runs in the child before exec (POSIX only)
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_WRITE_BYTES, MAX_WRITE_BYTES))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ImportError, ValueError, OSError):
        pass


def run_allowed(name: str, rel_path: str, workdir: Path, home: Path, timeout: float,
                allowed: dict | None = None) -> CmdResult:
    table = ALLOWED if allowed is None else allowed
    template = table.get(name)
    if template is None:
        raise E.FacError(E.COMMAND, f"command '{name}' is not in the allow-list")
    argv = [a.replace("{path}", rel_path) for a in template]
    with tempfile.TemporaryFile(dir=home) as out:
        try:
            proc = subprocess.Popen(argv, cwd=workdir, env=scrubbed_env(home, workdir), stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=subprocess.STDOUT, shell=False, start_new_session=True,
                                    preexec_fn=_limits if os.name == "posix" else None)
        except OSError as exc:
            raise E.FacError(E.COMMAND, f"command could not start ({type(exc).__name__})")
        timed_out = False
        try:
            proc.wait(timeout=max(timeout, 0.1))
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
            proc.wait()
        size = out.seek(0, os.SEEK_END)
        out.seek(max(0, size - OUTPUT_TAIL))
        tail = out.read().decode("utf-8", "replace")
    return CmdResult(None if timed_out else proc.returncode, timed_out, tail)
