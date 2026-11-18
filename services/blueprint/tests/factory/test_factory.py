import json
import os
import sys

from conftest import codes
from factory import check, write_report
from factory.__main__ import main
from factory.scan import Limits


def test_valid_static_only_reaches_draft(make):
    rep = check(make())
    assert rep.ok and rep.level_reached == "draft" and not rep.tests_run


def test_valid_with_tests_reaches_tested(make):
    rep = check(make(), run_tests=True, trusted_source=True, timeout=60)
    assert rep.ok and rep.level_reached == "tested" and rep.tests[0]["passed"], rep.findings


def test_refuses_tests_without_trusted_flag(make):
    d = make(test_body="open('ran.txt','w').write('x')\ndef test_x():\n    pass\n")
    rep = check(d, run_tests=True)
    assert "FAC-012" in codes(rep) and not rep.tests_run and not rep.ok
    assert rep.level_reached == "draft"


def test_bad_manifest(make):
    rep = check(make(lambda m: m.pop("licence")))
    assert "REG-001" in codes(rep) and rep.level_reached == "none" and not rep.ok


def test_missing_and_non_json_manifest(make):
    d = make()
    (d / "manifest.json").write_text("{nope", encoding="utf-8")
    assert "FAC-002" in codes(check(d))
    (d / "manifest.json").unlink()
    assert "FAC-002" in codes(check(d))


def test_missing_candidate(tmp_path):
    assert "FAC-001" in codes(check(tmp_path / "nope"))


def test_symlink_file_rejected(make, tmp_path):
    d = make()
    secret = tmp_path / "outside.txt"
    secret.write_text("data")
    os.symlink(secret, d / "link.txt")
    rep = check(d)
    assert "FAC-003" in codes(rep) and rep.level_reached == "none"


def test_symlink_folder_and_candidate_rejected(make, tmp_path):
    d = make()
    os.symlink(tmp_path, d / "dirlink")
    assert "FAC-003" in codes(check(d))
    assert "FAC-001" in codes(check(_link_to(d, tmp_path / "lnk")))


def _link_to(target, link):
    os.symlink(target, link)
    return link


def test_traversal_in_test_path(make):
    def edit(m):
        m["tests"][0]["path"] = "../../etc/passwd"
    rep = check(make(edit), run_tests=True, trusted_source=True)
    assert "FAC-004" in codes(rep) and rep.level_reached == "draft" and not rep.ok


def test_absolute_test_path(make):
    def edit(m):
        m["tests"][0]["path"] = "/etc/hosts"
    assert "FAC-004" in codes(check(make(edit), run_tests=True, trusted_source=True))


def test_missing_test_file(make):
    def edit(m):
        m["tests"][0]["path"] = "tests/absent.py"
    rep = check(make(edit), run_tests=True, trusted_source=True)
    assert "FAC-007" in codes(rep) and rep.level_reached == "draft"


def test_too_many_files(make):
    d = make()
    for i in range(5):
        (d / f"f{i}.txt").write_text("x")
    assert "FAC-005" in codes(check(d, limits=Limits(max_files=3)))


def test_oversized(make):
    d = make()
    (d / "big.bin").write_bytes(b"0" * 2000)
    assert "FAC-006" in codes(check(d, limits=Limits(max_file_bytes=1000)))
    assert "FAC-006" in codes(check(d, limits=Limits(max_total_bytes=1500)))


def test_timeout_kills_slow_command(make):
    d = make()
    slow = {"pytest": [sys.executable, "-c", "import time; time.sleep(30)", "{path}"]}
    rep = check(d, run_tests=True, trusted_source=True, timeout=1, allowed=slow)
    assert "FAC-008" in codes(rep) and rep.level_reached == "draft" and not rep.ok


def test_env_is_scrubbed(make, monkeypatch):
    canary = "CANARY_" + "SECRET_" + "VALUE"
    monkeypatch.setenv("FACTORY_CANARY", canary)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid")
    prog = "import os,sys;print('HOME='+os.environ['HOME']);print('C='+repr(os.environ.get('FACTORY_CANARY')));print('P='+repr(os.environ.get('HTTPS_PROXY')))"
    rep = check(make(), run_tests=True, trusted_source=True, allowed={"pytest": [sys.executable, "-c", prog, "{path}"]})
    tail = rep.tests[0]["outputTail"]
    assert "C=None" in tail and "P=None" in tail and canary not in tail
    assert "HOME=" in tail and os.path.expanduser("~") not in tail.split("HOME=")[1].splitlines()[0]


def test_failing_blocking_test_stays_draft(make):
    rep = check(make(test_body="def test_x():\n    assert False\n"), run_tests=True, trusted_source=True, timeout=60)
    assert "FAC-009" in codes(rep) and rep.level_reached == "draft" and not rep.ok


def test_never_above_tested(make):
    def edit(m):
        m["certification"] = {"level": "reviewed", "reviewedBy": ["someone"]}
    rep = check(make(edit), run_tests=True, trusted_source=True, timeout=60)
    assert "FAC-011" in codes(rep) and rep.level_reached == "tested" and rep.as_dict()["maxGrantable"] == "tested"


def test_unlisted_command_refused(make):
    rep = check(make(), run_tests=True, trusted_source=True, allowed={})
    assert "FAC-014" in codes(rep) and not rep.ok


def test_candidate_not_modified_and_report_outside(make, tmp_path):
    d = make(test_body="open('written.txt','w').write('x')\ndef test_x():\n    pass\n")
    before = sorted(p.name for p in d.rglob("*"))
    rep = check(d, run_tests=True, trusted_source=True, timeout=60)
    assert sorted(p.name for p in d.rglob("*")) == before and rep.level_reached == "tested"
    out = tmp_path / "report.json"
    write_report(rep, out, d)
    assert json.loads(out.read_text())["levelReached"] == "tested"
    try:
        write_report(rep, d / "r.json", d)
        raise AssertionError("should refuse")
    except Exception as exc:
        assert "FAC-013" in str(exc)


def test_cli(make, tmp_path, capsys):
    d = make()
    assert main(["check", str(d), "--out", str(tmp_path / "r.json")]) == 0
    assert json.loads(capsys.readouterr().out)["levelReached"] == "draft"
    assert main(["check", str(d), "--run-tests"]) == 1
    assert main(["check", str(d), "--out", str(d / "r.json")]) == 1
