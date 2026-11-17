import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from migrate import CURRENT_SCHEMA_VERSION, Registry, migrate
from migrate.__main__ import main

BP = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((BP / "fixtures" / "trading-distribution.blueprint.json").read_text(encoding="utf-8"))


def fake_registry(chain=True):
    """Test-only: 0.1.0 -> 0.2.0 (renames company.name key) and 0.2.0 -> 0.3.0 (adds a marker)."""
    reg = Registry(latest="0.1.0")

    @reg.register("0.1.0", "0.2.0")
    def s1(d):
        d["x_marker"] = "a"
        return d

    if chain:
        @reg.register("0.2.0", "0.3.0")
        def s2(d):
            d["x_marker"] = d["x_marker"] + "b"
            return d
    return reg


def codes(r):
    return [i.code for i in r.errors]


def fx():
    return copy.deepcopy(FIXTURE)


def test_default_is_noop_at_current_and_validates():
    d = fx()
    r = migrate(d)
    assert r.ok and r.noop and r.to_version == CURRENT_SCHEMA_VERSION
    assert r.blueprint == FIXTURE and r.blueprint is not d


def test_single_and_chained_path_with_change_list():
    r = migrate(fx(), "0.2.0", registry=fake_registry(), validate_result=False)
    assert r.ok and [(s.from_version, s.to_version) for s in r.steps] == [("0.1.0", "0.2.0")]
    paths = [c["path"] for c in r.steps[0].changes]
    assert paths == ["/meta/schemaVersion", "/x_marker"]
    r = migrate(fx(), registry=fake_registry(), validate_result=False)  # default target = latest 0.3.0
    assert r.to_version == "0.3.0" and r.blueprint["x_marker"] == "ab" and len(r.steps) == 2
    assert r.blueprint["meta"]["schemaVersion"] == "0.3.0"


def test_idempotent_and_input_unmutated_and_deterministic():
    reg, d = fake_registry(), fx()
    r1 = migrate(d, registry=reg, validate_result=False)
    assert d == FIXTURE
    r2 = migrate(r1.blueprint, registry=reg, validate_result=False)
    assert r2.noop and r2.blueprint == r1.blueprint
    r3 = migrate(fx(), registry=reg, validate_result=False)
    assert json.dumps(r3.blueprint, sort_keys=True) == json.dumps(r1.blueprint, sort_keys=True)
    assert r3.steps == r1.steps


def test_revision_and_business_content_untouched():
    r = migrate(fx(), registry=fake_registry(), validate_result=False)
    assert r.blueprint["meta"]["revision"] == FIXTURE["meta"]["revision"]
    assert r.blueprint["company"] == FIXTURE["company"]


def test_step_must_not_touch_revision_or_set_version():
    reg = Registry()

    @reg.register("0.1.0", "0.2.0")
    def bump(d):
        d["meta"]["revision"] += 1
        return d
    assert codes(migrate(fx(), "0.2.0", registry=reg)) == ["MIG-STEP-002"]
    reg = Registry()

    @reg.register("0.1.0", "0.2.0")
    def setv(d):
        d["meta"]["schemaVersion"] = "0.2.0"
        return d
    assert codes(migrate(fx(), "0.2.0", registry=reg)) == ["MIG-STEP-003"]
    reg = Registry()

    @reg.register("0.1.0", "0.2.0")
    def boom(d):
        raise KeyError("x")
    assert codes(migrate(fx(), "0.2.0", registry=reg)) == ["MIG-STEP-001"]


def test_refusals():
    reg = fake_registry()
    d = fx()
    d["meta"]["schemaVersion"] = "0.3.0"
    assert codes(migrate(d, "0.1.0", registry=reg)) == ["MIG-VER-004"]
    d["meta"]["schemaVersion"] = "9.0.0"
    assert codes(migrate(d, registry=reg)) == ["MIG-VER-003"]
    d["meta"]["schemaVersion"] = "0.1.5"
    assert codes(migrate(d, registry=reg)) == ["MIG-VER-002"]
    for bad in ("1.0", "v0.1.0", "01.0.0", None, 1, "0.1.0-rc1"):
        d["meta"]["schemaVersion"] = bad
        assert codes(migrate(d, registry=reg)) == ["MIG-VER-001"]
    for bad in (None, [], {}, {"meta": []}, {"meta": {}}, "x"):
        assert codes(migrate(bad)) == ["MIG-INPUT-001"]
    assert codes(migrate(fx(), "x", registry=reg)) == ["MIG-VER-001"]
    assert codes(migrate(fx(), "0.9.0", registry=reg)) == ["MIG-VER-003"]
    assert codes(migrate(fx(), "0.1.1", registry=reg)) == ["MIG-VER-002"]


def test_gap_refused():
    reg = Registry(latest="0.1.0")

    @reg.register("0.2.0", "0.3.0")
    def s(d):
        return d
    # 0.1.0 is known (latest) but 0.3.0 is the latest; no step leaves 0.1.0
    assert codes(migrate(fx(), registry=reg)) == ["MIG-PATH-001"]


def test_registration_rules():
    reg = Registry()
    with pytest.raises(ValueError, match="MIG-REG-001"):
        reg.register("0.2.0", "0.1.0")
    with pytest.raises(ValueError, match="MIG-REG-001"):
        reg.register("0.1", "0.2.0")
    reg.register("0.1.0", "0.2.0")(lambda d: d)
    with pytest.raises(ValueError, match="MIG-REG-002"):
        reg.register("0.1.0", "0.3.0")


def test_non_draft_refused_unless_flag():
    d = fx()
    d["meta"]["buildState"] = "owner_approved"
    reg = fake_registry()
    assert codes(migrate(d, "0.2.0", registry=reg, validate_result=False)) == ["MIG-STATE-001"]
    r = migrate(d, "0.2.0", registry=reg, validate_result=False, allow_non_draft=True)
    assert r.ok and r.blueprint["meta"]["buildState"] == "owner_approved"
    assert migrate(d).ok  # current already: nothing to migrate, no refusal


def test_result_revalidated_at_current_version():
    reg = Registry()  # latest 0.1.0, add a step into the current version from a fake older one

    @reg.register("0.0.9", "0.1.0")
    def up(d):
        del d["company"]  # produces an invalid 0.1.0 document
        return d
    d = fx()
    d["meta"]["schemaVersion"] = "0.0.9"
    assert "MIG-VALID-001" in codes(migrate(d, registry=reg))
    ok = Registry()
    ok.register("0.0.9", "0.1.0")(lambda d: d)
    r = migrate(d, registry=ok)
    assert r.ok and r.blueprint["meta"]["schemaVersion"] == "0.1.0"


def test_cli(tmp_path, capsys):
    f = tmp_path / "b.json"
    f.write_text(json.dumps(FIXTURE))
    assert main([str(f)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and out["steps"] == [] and out["to"] == "0.1.0"
    assert main([str(f), "--to", "9.9.9"]) == 1
    assert json.loads(capsys.readouterr().out)["errors"][0]["code"] == "MIG-VER-003"
    assert main([str(tmp_path / "missing.json")]) == 1
    capsys.readouterr()
    p = subprocess.run([sys.executable, "-m", "migrate", str(f)], cwd=BP, capture_output=True, text=True)
    assert p.returncode == 0 and json.loads(p.stdout)["ok"]
