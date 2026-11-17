"""Snapshot tests for the compiler (QA-004). See snap_helpers.py for the case table and the update switch.

Provenance of the first snapshot of each valid fixture (snapshots are never generated blindly):
- valid--trading-distribution.sandbox: the artifact is compared for equality with the existing golden file
  services/blueprint/tests/compiler/fixtures/trading-distribution.expected-artifact.json (derived independently
  from the contract) and validated against contracts/compiled-artifact.schema.json, in
  test_valid_snapshot, before the snapshot is compared or written.
- A production compile (synthetic certified manifests, verified mapping) has no snapshot of its own because its
  artifact is byte-identical to the sandbox one (250 KB each; the size budget is 400 KB). test_production_artifact_
  equals_the_sandbox_snapshot compares it with the stored sandbox snapshot and validates it against the schema.
Refusal snapshots hold stable (code, path) pairs only; each case is a named edit of the fixture or mapping.
"""
from __future__ import annotations

import getpass
import json
import os
import re
import socket
import tempfile
from pathlib import Path

import pytest

import snap_helpers as S

H = S.H

VALID = sorted(S.VALID_CASES)
REFUSALS = sorted(S.REFUSAL_CASES)


# ------------------------------------------------------------------ the snapshots themselves
@pytest.mark.parametrize("name", VALID)
def test_valid_snapshot(name):
    result, i = S.run_case(S.VALID_CASES[name])
    assert result.ok, [str(e) for e in result.errors]
    art = result.artifact
    errors = sorted(H.ARTIFACT_VALIDATOR.iter_errors(art), key=str)
    assert not errors, errors[:3]
    assert art == S.resolve_golden(H.load(H.EXPECTED), H.blueprint())
    S.assert_matches_snapshot(S.snapshot_file("valid", name), S.render_valid(result))


def test_production_artifact_equals_the_sandbox_snapshot():
    bp, reg, mp = H.production_inputs()
    result = S.compile_blueprint(bp, reg, mp, environment="production")
    assert result.ok, [str(e) for e in result.errors]
    assert not sorted(H.ARTIFACT_VALIDATOR.iter_errors(result.artifact), key=str)
    stored = S.snapshot_file("valid", "trading-distribution.sandbox").read_bytes()
    assert S.render_valid(result) == stored


@pytest.mark.parametrize("name", REFUSALS)
def test_refusal_snapshot(name):
    result, i = S.run_case(S.REFUSAL_CASES[name])
    S.assert_matches_snapshot(S.snapshot_file("refusal", name), S.render_refusal(result, i["env"]))


def test_plan_view_is_part_of_each_valid_snapshot():
    for name in VALID:
        data = json.loads(S.snapshot_file("valid", name).read_bytes())
        assert [r["seq"] for r in data["planView"]] == [s["seq"] for s in data["artifact"]["steps"]]


def test_refusal_snapshots_hold_only_codes_and_paths():
    for name in REFUSALS:
        data = json.loads(S.snapshot_file("refusal", name).read_bytes())
        assert set(data) == {"environment", "errors"} and data["errors"]
        assert all(set(e) == {"code", "path"} and re.fullmatch(r"[A-Z]+-[A-Z]+-\d{3}", e["code"]) for e in data["errors"])


# ------------------------------------------------------------------ determinism
@pytest.mark.parametrize("kind,name", [("valid", n) for n in VALID] + [("refusal", n) for n in REFUSALS])
def test_compiling_twice_gives_identical_output(kind, name):
    builder = (S.VALID_CASES if kind == "valid" else S.REFUSAL_CASES)[name]
    assert S.render_case(kind, builder) == S.render_case(kind, builder)


# ------------------------------------------------------------------ update switch and failure messages
def test_update_switch_is_off_by_default():
    # Run under UPDATE_SNAPSHOTS=1 to refresh snapshots; this test only checks the code default, not your shell.
    assert S.UPDATE_ENV == "UPDATE_SNAPSHOTS"
    saved = os.environ.pop(S.UPDATE_ENV, None)
    try:
        assert S.update_enabled() is False
        for off in ("", "0", "true", "yes", "11"):
            os.environ[S.UPDATE_ENV] = off
            assert S.update_enabled() is False
        os.environ[S.UPDATE_ENV] = "1"
        assert S.update_enabled() is True
    finally:
        os.environ.pop(S.UPDATE_ENV, None)
        if saved is not None:
            os.environ[S.UPDATE_ENV] = saved


def test_missing_snapshot_fails_and_is_not_created(tmp_path, monkeypatch):
    monkeypatch.delenv(S.UPDATE_ENV, raising=False)
    target = tmp_path / "snapshots" / "x.json"
    with pytest.raises(AssertionError) as e:
        S.assert_matches_snapshot(target, b"{}\n")
    assert "snapshot missing" in str(e.value) and S.UPDATE_COMMAND in str(e.value)
    assert not target.exists() and not target.parent.exists()


def test_difference_fails_without_writing_and_prints_unified_diff(tmp_path, monkeypatch):
    monkeypatch.delenv(S.UPDATE_ENV, raising=False)
    target = tmp_path / "x.json"
    old = b'{\n  "a": 1,\n  "b": 2\n}\n'
    target.write_bytes(old)
    with pytest.raises(AssertionError) as e:
        S.assert_matches_snapshot(target, b'{\n  "a": 1,\n  "b": 3\n}\n')
    msg = str(e.value)
    assert "snapshot differs" in msg and '-  "b": 2' in msg and '+  "b": 3' in msg and "@@" in msg
    assert S.UPDATE_COMMAND in msg
    assert target.read_bytes() == old


def test_update_switch_rewrites_only_when_on(tmp_path, monkeypatch):
    target = tmp_path / "s" / "x.json"
    monkeypatch.setenv(S.UPDATE_ENV, "1")
    S.assert_matches_snapshot(target, b"{}\n")
    assert target.read_bytes() == b"{}\n"
    S.assert_matches_snapshot(target, b'{"a": 1}\n')
    assert target.read_bytes() == b'{"a": 1}\n'


def test_diff_shows_only_the_first_region():
    old = "\n".join(str(i) for i in range(100))
    new = old.replace("\n5\n", "\nfive\n").replace("\n90\n", "\nninety\n")
    out = S.diff_message(old, new, "n")
    assert "+five" in out and "ninety" not in out and "further differences" in out


# ------------------------------------------------------------------ the snapshot folder
def _files():
    return sorted(S.SNAPSHOT_DIR.iterdir())


def _is_sorted(value) -> bool:
    if isinstance(value, dict):
        return list(value) == sorted(value) and all(_is_sorted(v) for v in value.values())
    if isinstance(value, list):
        return all(_is_sorted(v) for v in value)
    return True


def test_every_case_has_exactly_one_snapshot_and_every_snapshot_has_a_case():
    names = [p.name for p in _files()]
    assert len(names) == len(set(names))
    assert set(names) == S.SNAPSHOT_NAMES, (sorted(set(names) - S.SNAPSHOT_NAMES), sorted(S.SNAPSHOT_NAMES - set(names)))
    assert all(p.is_file() and p.suffix == ".json" for p in _files())


def test_every_blueprint_fixture_file_is_covered_by_a_valid_case():
    fixtures = sorted(p.name for p in S.FIXTURE_DIR.glob("*.blueprint.json"))
    assert fixtures == [S.FIXTURE_NAME]
    covered = {S.FIXTURE_NAME for _ in VALID}  # all valid cases compile H.FIXTURE
    assert set(fixtures) <= covered and VALID


def test_snapshot_files_are_sorted_stable_and_newline_terminated():
    for p in _files():
        raw = p.read_bytes()
        assert raw.endswith(b"\n") and not raw.endswith(b"\n\n"), p.name
        assert b"\r" not in raw and b"\t" not in raw, p.name
        data = json.loads(raw)
        assert _is_sorted(data), f"{p.name}: keys not sorted"
        assert raw == (json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


_PATH = re.compile(r"(?:/Users/|/home/|/private/|/var/folders/|/tmp/|/mnt/|file://|[A-Za-z]:\\\\|~/)")
_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def test_snapshots_contain_no_machine_specific_values():
    fixture_text = S.H.FIXTURE.read_text(encoding="utf-8")
    fixture_stamps = set(_STAMP.findall(fixture_text))
    machine = {getpass.getuser(), socket.gethostname().split(".")[0], Path.home().name, str(S.H.REPO),
               str(Path.home()), tempfile.gettempdir(), os.getcwd()}
    machine = {m for m in machine if m and len(m) >= 4 and m.lower() not in fixture_text.lower()}
    for p in _files():
        text = p.read_text(encoding="utf-8")
        assert not _PATH.search(text), f"{p.name}: absolute path"
        # A timestamp is allowed only where it was copied verbatim from the (fixed) fixture.
        assert set(_STAMP.findall(text)) <= fixture_stamps, f"{p.name}: timestamp not from the fixture"
        for m in machine:
            assert m not in text, f"{p.name}: machine-specific value {m!r}"


def test_total_snapshot_size_stays_under_400_kb():
    assert sum(p.stat().st_size for p in _files()) < S.MAX_TOTAL_BYTES
