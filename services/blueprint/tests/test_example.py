import json
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator

from fixture_registry import COMPONENT_SCHEMA, REPO, assets, load_example, manifests, registry
from validator import ValidationContext, validate


def full_ctx(**over):
    base = dict(registry=registry(), metrics={
        "sales.revenue", "sales.order_count", "sales.revenue_by_customer", "finance.receivables_aging", "sales.order_list"},
        connectors={"file.excel_upload"}, assets=assets(), entitlements=set())
    base.update(over)
    return ValidationContext(**base)


def test_example_passes_with_zero_errors():
    rep = validate(load_example(), full_ctx())
    assert rep.errors == [], [str(e) for e in rep.errors]
    assert rep.ok


def test_example_only_warns_about_colour_adjustment():
    rep = validate(load_example(), full_ctx())
    assert {w.code for w in rep.warnings} <= {"BP-BRAND-002"}


def test_fixture_manifests_are_valid_against_manifest_schema():
    v = Draft202012Validator(json.loads(COMPONENT_SCHEMA.read_text(encoding="utf-8")))
    for m in manifests():
        assert list(v.iter_errors(m)) == [], m["id"]


def test_without_ctx_example_passes_with_not_checked_warnings():
    rep = validate(load_example())
    assert rep.ok
    assert {"BP-REF-002", "BP-CMP-005", "BP-FN-002", "BP-ASSET-003"} <= rep.codes()


def test_cli_ok_and_failing(tmp_path):
    reg = tmp_path / "reg"
    reg.mkdir()
    for m in manifests():
        (reg / (m["id"] + ".json")).write_text(json.dumps(m), encoding="utf-8")
    bad = load_example()
    bad["roles"][0]["isAdmin"] = False
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    run = lambda *a: subprocess.run([sys.executable, str(REPO / "services/blueprint/validator/__main__.py"), *a],
                                    capture_output=True, text=True, cwd=tmp_path)
    ok = run(str(REPO / "contracts/examples/blueprint-trading-minimal.json"), "--registry", str(reg))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    res = run(str(bad_path), "--registry", str(reg))
    assert res.returncode == 1
    assert "ERROR BP-ROLE-002 /roles:" in res.stdout
    assert run(str(tmp_path / "missing.json")).returncode == 1
