"""Deterministic sandbox runner (BPL-015). LOGICAL sandbox only: see services/blueprint/README.md.

Copies a candidate into a fresh temp folder, validates its manifest with the registry admission rules, and (only
for a trusted source) runs the declared tests through the allow-list. Reaches 'draft' or 'tested', never higher.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from registry.admission import admit
from registry.store import RawManifest

from . import commands, errors as E
from .errors import Finding
from .scan import Limits, check_relpath, copy_component

MAX_LEVEL = "tested"
DEFAULT_TIMEOUT = 120.0
MAX_MANIFEST_BYTES = 1_000_000


@dataclass
class Report:
    component: str | None = None
    declared_level: str | None = None
    level_reached: str = "none"
    trusted_source: bool = False
    tests_run: bool = False
    files: int = 0
    findings: list = field(default_factory=list)
    tests: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.is_error for f in self.findings) and self.level_reached != "none"

    def as_dict(self) -> dict:
        return {"component": self.component, "declaredLevel": self.declared_level, "levelReached": self.level_reached,
                "maxGrantable": MAX_LEVEL, "trustedSource": self.trusted_source, "testsRun": self.tests_run,
                "files": self.files, "ok": self.ok, "tests": self.tests,
                "findings": [f.as_dict() for f in self.findings]}


def _read_manifest(workdir: Path) -> dict:
    p = workdir / "manifest.json"
    try:
        if not p.is_file() or p.stat().st_size > MAX_MANIFEST_BYTES:
            raise E.FacError(E.MANIFEST, "manifest.json missing or over 1 MB")
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise E.FacError(E.MANIFEST, f"manifest.json unreadable or not JSON ({type(exc).__name__})")
    if not isinstance(data, dict):
        raise E.FacError(E.MANIFEST, "manifest.json is not an object")
    return data


def _static(rep: Report, manifest: dict) -> bool:
    cert = manifest.get("certification")
    rep.declared_level = cert.get("level") if isinstance(cert, dict) else None
    cid, ver = manifest.get("id"), manifest.get("version")
    rep.component = f"{cid}@{ver}" if isinstance(cid, str) and isinstance(ver, str) else None
    if rep.declared_level not in (None, "draft", "tested"):
        rep.findings.append(Finding(E.LEVEL_CAPPED, E.WARNING, f"declared level '{rep.declared_level}' is not granted here; "
                                    f"the sandbox never goes above '{MAX_LEVEL}' (ADR-0034: named reviewer)"))
    _, issues = admit([RawManifest("manifest.json", manifest)])
    rep.findings.extend(Finding(i.code, i.severity, i.message) for i in issues)
    return not any(i.is_error for i in issues)


def _run_tests(rep: Report, manifest: dict, workdir: Path, home: Path, timeout: float, allowed: dict | None) -> None:
    deadline = time.monotonic() + timeout
    entries = []
    for t in manifest["tests"]:
        try:
            rel = check_relpath(t["path"])
            if not (workdir / rel).exists():
                raise E.FacError(E.TEST_MISSING, f"test path '{rel}' ({t['id']}) not found in the component")
        except E.FacError as exc:
            rep.findings.append(Finding(exc.code, E.ERROR, exc.message))
            return
        entries.append((t, rel))
    rep.tests_run = True
    for t, rel in entries:
        left = deadline - time.monotonic()
        if left <= 0:
            rep.findings.append(Finding(E.TIMEOUT, E.ERROR, f"wall-clock limit {timeout}s used up before '{t['id']}'"))
            return
        try:
            res = commands.run_allowed("pytest", rel, workdir, home, left, allowed)
        except E.FacError as exc:
            rep.findings.append(Finding(exc.code, E.ERROR, exc.message))
            return
        passed = res.returncode == 0
        rep.tests.append({"id": t["id"], "path": rel, "blocking": t["blocking"], "passed": passed,
                          "timedOut": res.timed_out, "returncode": res.returncode, "outputTail": res.tail})
        if res.timed_out:
            rep.findings.append(Finding(E.TIMEOUT, E.ERROR, f"test '{t['id']}' killed at the wall-clock limit"))
            return
        if not passed:
            code, sev = (E.BLOCKING_FAIL, E.ERROR) if t["blocking"] else (E.TEST_FAIL, E.WARNING)
            rep.findings.append(Finding(code, sev, f"{'blocking ' if t['blocking'] else ''}test '{t['id']}' failed"))


def check(candidate: str | os.PathLike, run_tests: bool = False, trusted_source: bool = False,
          timeout: float = DEFAULT_TIMEOUT, limits: Limits = Limits(), allowed: dict | None = None) -> Report:
    """Never raises for bad input; every failure is a finding and the level stays 'none' or 'draft'."""
    rep = Report(trusted_source=trusted_source)
    try:
        with tempfile.TemporaryDirectory(prefix="factory-sbx-") as tmp:
            work, home = Path(tmp) / "component", Path(tmp) / "home"
            work.mkdir()
            home.mkdir()
            rep.files = copy_component(candidate, work, limits)
            manifest = _read_manifest(work)
            if not _static(rep, manifest):
                return rep
            rep.level_reached = "draft"
            if run_tests and not trusted_source:
                rep.findings.append(Finding(E.UNTRUSTED, E.ERROR, "tests not run: candidate commands need --trusted-source. "
                                            "This is a logical sandbox; an OS-level sandbox (INF-014) is required for "
                                            "third-party or customer-influenced code"))
            elif run_tests:
                _run_tests(rep, manifest, work, home, timeout, allowed)
                if rep.tests_run and not any(f.is_error for f in rep.findings):
                    rep.level_reached = MAX_LEVEL
    except E.FacError as exc:
        rep.level_reached = "none"
        rep.findings.append(Finding(exc.code, E.ERROR, exc.message))
    except Exception as exc:  # fail closed
        rep.level_reached = "none"
        rep.findings.append(Finding(E.COMMAND, E.ERROR, f"internal error ({type(exc).__name__})"))
    return rep


def write_report(rep: Report, out: str | os.PathLike, candidate: str | os.PathLike) -> None:
    """Write the JSON report. Refuses a path inside the candidate folder."""
    o, c = Path(out).resolve(), Path(candidate).resolve()
    if o == c or c in o.parents:
        raise E.FacError(E.REPORT_PATH, "report must be written outside the component folder")
    try:
        o.write_text(json.dumps(rep.as_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as exc:
        raise E.FacError(E.REPORT_PATH, f"cannot write report ({type(exc).__name__})")
