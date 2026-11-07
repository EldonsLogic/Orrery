import json
import subprocess
import sys
from pathlib import Path

import pytest

from bpdiff.__main__ import main
from bpdiff import diff_validated
import bpdiff_helpers as h

DIFF_DIR = h.BLUEPRINT / "diff"


def write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return str(p)


def test_exit_codes(tmp_path, capsys):
    a, b = h.make_pair("add_field")
    pa, pb = write(tmp_path, "a.json", a), write(tmp_path, "b.json", b)
    assert main([pa, pa]) == 0
    assert main([pa, pb, "--apply-check"]) == 1
    out = capsys.readouterr().out
    assert "BPD-FIELD-ADDED" in out and "apply check: ok" in out and "needsDdlPlanGate=true" in out
    assert main([pa, pb, "--json"]) == 1
    d = json.loads(capsys.readouterr().out)
    assert d["ops"][0]["code"] == "BPD-FIELD-ADDED"
    assert main([pa, str(tmp_path / "missing.json")]) == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert main([pa, str(bad)]) == 2
    arr = write(tmp_path, "arr.json", [1])
    assert main([pa, arr]) == 2
    assert "BPD-INPUT-003" in capsys.readouterr().err


def test_module_entry_point(tmp_path):
    a, b = h.make_pair("change_branding_colour")
    pa, pb = write(tmp_path, "a.json", a), write(tmp_path, "b.json", b)
    r = subprocess.run([sys.executable, "-B", "-m", "bpdiff", pa, pb], cwd=DIFF_DIR, capture_output=True, text=True)
    assert r.returncode == 1 and "BPD-BRANDING-COLOUR-CHANGED" in r.stdout


def test_diff_validated_flags_invalid_revisions():
    a, b = h.make_pair("add_field")
    v = diff_validated(a, b)
    assert v.base_report.ok and v.target_report.ok and not v.invalid
    assert v.diff["ops"] and v.to_dict()["baseReport"]["ok"] is True
    bad = json.loads(json.dumps(b))
    bad["roles"][0]["id"] = bad["roles"][1]["id"]  # duplicate role id
    v = diff_validated(a, bad)
    assert v.invalid and [f["code"] for f in v.flags] == ["BPD-VALID-002"]
    assert not v.target_report.ok and v.diff["ops"]
    v = diff_validated(bad, a)
    assert [f["code"] for f in v.flags] == ["BPD-VALID-001"]
    json.dumps(v.to_dict())
