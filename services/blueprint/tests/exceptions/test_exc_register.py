import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from exceptions import ExceptionsError, append, read_rows, reconcile, summary, validate_row

BP = Path(__file__).resolve().parents[2]


def row(**kw):
    base = {"date": "2026-11-18", "tenant": "acme-01", "blueprint_rev": 3, "element_pointer": "/entities/invoice/fields/vat",
            "edited_by_hand": "Changed VAT field default", "reason": "Library field has no zero-rated default",
            "class": "component_gap", "proposed_automation": "Add zero-rated default to the VAT component",
            "owner": "eldon"}
    base.update(kw)
    return base


@pytest.fixture
def reg(tmp_path):
    return tmp_path / "acme.jsonl"


def code(fn, *a, **k):
    with pytest.raises(ExceptionsError) as e:
        fn(*a, **k)
    return e.value.code


def test_valid_append_assigns_sequential_ids(reg):
    a = append(reg, row())
    b = append(reg, row(follow_up="PLAN BPL-099"))
    assert (a["id"], b["id"]) == (1, 2) and a["blueprint_rev"] == "3"
    assert [r["id"] for r in read_rows(reg)] == [1, 2]
    assert len(reg.read_bytes().splitlines()) == 2


def test_append_only_prefix_unchanged(reg):
    append(reg, row())
    before = reg.read_bytes()
    append(reg, row(tenant="beta"))
    after = reg.read_bytes()
    assert after.startswith(before) and len(after) > len(before)


def test_refused_row_writes_nothing(reg):
    append(reg, row())
    before = reg.read_bytes()
    assert code(append, reg, row(reason="mail me at a@b.com")) == "EXC-DATA-001"
    assert reg.read_bytes() == before


def test_correction_rows(reg):
    append(reg, row())
    c = append(reg, row(corrects=1, **{"class": "mapping_gap"}))
    assert c["corrects"] == 1 and c["id"] == 2
    assert code(append, reg, row(corrects=9)) == "EXC-ROW-003"
    assert code(append, reg, row(corrects=1, tenant="other")) == "EXC-ROW-003"
    assert code(append, reg, row(corrects=0)) == "EXC-ROW-001"
    s = summary(reg)
    assert s["effective_rows"] == 1 and s["corrections"] == 1 and s["by_class"]["mapping_gap"] == 1
    assert s["by_class"]["component_gap"] == 0


@pytest.mark.parametrize("text,expected", [
    ("contact john@example.com", "EXC-DATA-001"),
    ("call +966 50 123 4567", "EXC-DATA-001"),
    ("call 0501234567", "EXC-DATA-001"),
    ("iban 123456789012345", "EXC-DATA-001"),
    ("digits ١٢٣٤٥٦٧٨٩٠", "EXC-DATA-001"),
    ("see https://user:pw@host.example/x", "EXC-DATA-002"),
    ("password: hunter2", "EXC-DATA-002"),
    ("key sk-abc1def2ghi3jkl4mno5pqr", "EXC-DATA-002"),
    ("AKIAIOSFODNN7EXAMPLE1", "EXC-DATA-002"),
    ("value Zk3Jd9Qw2Lp8Vx5Rt7Yn4Bm6Hc1Ga0S", "EXC-DATA-002"),
    ("-----BEGIN " + "PRIVATE KEY-----", "EXC-DATA-002"),
])
def test_personal_and_secret_refusals(reg, text, expected):
    assert code(append, reg, row(reason=text)) == expected
    assert not reg.exists()


def test_other_refusals(reg):
    assert code(validate_row, "x") == "EXC-ROW-001"
    assert code(validate_row, {**row(), "extra": 1}) == "EXC-ROW-001"
    assert code(validate_row, {**row(), "id": 5}) == "EXC-ROW-001"
    r = row()
    del r["owner"]
    assert code(validate_row, r) == "EXC-ROW-001"
    assert code(validate_row, row(date="2026-13-40")) == "EXC-ROW-002"
    assert code(validate_row, row(date="18/11/2026")) == "EXC-ROW-002"
    assert code(validate_row, row(**{"class": "nope"})) == "EXC-ROW-002"
    assert code(validate_row, row(reason="x" * 501)) == "EXC-ROW-002"
    assert code(validate_row, row(reason="  ")) == "EXC-ROW-002"
    assert code(validate_row, row(reason=5)) == "EXC-ROW-001"
    assert code(validate_row, row(element_pointer="entities/x")) == "EXC-ROW-002"
    assert code(validate_row, row(tenant="a b")) == "EXC-ROW-002"
    assert code(validate_row, row(blueprint_rev=True)) == "EXC-ROW-001"


def test_hostile_strings_are_cleaned_not_run(reg):
    v = validate_row(row(reason="ok‮ txet​ hidden\x00\x1b[31m \n {0.__class__} $(rm -rf /) ; DROP"))
    assert all(ord(c) >= 32 and c not in "‮​\x7f" for c in v["reason"])
    assert "$(rm -rf /)" in v["reason"] and "{0.__class__}" in v["reason"]  # kept as inert text
    # zero-width characters cannot be used to hide an email from the scan
    assert code(validate_row, row(reason="a​@​b.com")) == "EXC-DATA-001"
    assert code(validate_row, row(element_pointer="/a‮b")) == "EXC-ROW-002"
    assert code(validate_row, row(reason="a" * 5000)) == "EXC-ROW-002"
    assert row()["reason"] == "Library field has no zero-rated default"  # input untouched


def test_path_rules(tmp_path):
    assert code(append, BP / "register.jsonl", row()) == "EXC-FILE-001"
    assert not (BP / "register.jsonl").exists()
    real = tmp_path / "r.jsonl"
    link = tmp_path / "l.jsonl"
    link.symlink_to(real)
    assert code(append, link, row()) == "EXC-FILE-001"
    assert code(append, tmp_path / "nodir" / "r.jsonl", row()) == "EXC-FILE-001"


def test_corrupt_file(reg):
    reg.write_text('{"id": 2}\n')
    assert code(read_rows, reg) == "EXC-FILE-002"
    reg.write_text("not json\n")
    assert code(append, reg, row()) == "EXC-FILE-002"
    reg.write_text('{"id": 1}')
    assert code(read_rows, reg) == "EXC-FILE-002"


def test_summary_counts_deterministic(reg):
    append(reg, row(tenant="zed"))
    append(reg, row(**{"class": "client_specific"}))
    append(reg, row(**{"class": "client_specific"}))
    s = summary(reg)
    assert s["by_class"] == {"missing_component": 0, "component_gap": 1, "mapping_gap": 0, "client_specific": 2,
                             "error_in_draft": 0}
    assert list(s["by_tenant"].items()) == [("acme-01", 2), ("zed", 1)]
    assert s["by_tenant_class"]["acme-01"]["client_specific"] == 2 and s["total_rows"] == 3
    assert json.dumps(summary(reg), sort_keys=True) == json.dumps(s, sort_keys=True)
    assert summary(reg.with_name("none.jsonl"))["total_rows"] == 0


def test_reconcile(reg):
    append(reg, row(element_pointer="/entities/invoice"))
    append(reg, row(element_pointer="/roles/clerk"))
    append(reg, row(tenant="other", element_pointer="/roles/zzz"))
    ok = reconcile(reg, ["/entities/invoice", "/roles/clerk"], "acme-01", 3)
    assert ok["ok"] and ok["rows"] == 2 and ok["edits"] == 2
    bad = reconcile(reg, ["/entities/invoice", "/roles/clerk", "/reports/sales"], "acme-01", "3")
    assert not bad["ok"] and bad["edits_without_row"] == ["/reports/sales"]
    bad = reconcile(reg, ["/entities/invoice"], "acme-01", 3)
    assert bad["rows_without_edit"] == [2] and not bad["ok"]
    assert reconcile(reg, ["/entities/invoice"], "acme-01", 4)["edits_without_row"] == ["/entities/invoice"]
    assert code(reconcile, reg, "x", "acme-01", 3) == "EXC-IN-001"
    assert code(reconcile, reg, [1], "acme-01", 3) == "EXC-IN-001"


def run(*args, stdin=None):
    env = {**os.environ, "PYTHONPATH": str(BP)}
    return subprocess.run([sys.executable, "-m", "exceptions", *args], capture_output=True, text=True, env=env,
                          input=stdin, cwd=BP.parent.parent)


CLI_ROW = ["--date", "2026-11-18", "--tenant", "acme-01", "--rev", "3", "--pointer", "/roles/clerk", "--edit", "Added role",
           "--reason", "Library lacks clerk", "--class", "missing_component", "--automation", "Add clerk role",
           "--owner", "eldon"]


def test_cli_exit_codes(reg, tmp_path):
    r = run("append", str(reg), *CLI_ROW)
    assert r.returncode == 0 and json.loads(r.stdout)["id"] == 1
    r = run("append", str(reg), "--json", "-", stdin=json.dumps(row(reason="mail a@b.com")))
    assert r.returncode == 2 and "EXC-DATA-001" in r.stderr
    r = run("summary", str(reg))
    assert r.returncode == 0 and json.loads(r.stdout)["by_class"]["missing_component"] == 1
    m = tmp_path / "m.json"
    m.write_text(json.dumps({"tenant": "acme-01", "revision": 3, "manual": ["/roles/clerk"], "removed": []}))
    assert run("reconcile", str(reg), "--metrics", str(m)).returncode == 0
    m.write_text(json.dumps({"tenant": "acme-01", "revision": 3, "manual": ["/roles/clerk"], "removed": ["/reports/x"]}))
    r = run("reconcile", str(reg), "--metrics", str(m))
    assert r.returncode == 1 and json.loads(r.stdout)["edits_without_row"] == ["/reports/x"]
    m.write_text("nope")
    assert run("reconcile", str(reg), "--metrics", str(m)).returncode == 2
    reg.write_text("garbage\n")
    assert run("summary", str(reg)).returncode == 1
    assert run("append", str(BP / "x.jsonl"), *CLI_ROW).returncode == 1
    assert not (BP / "x.jsonl").exists()
