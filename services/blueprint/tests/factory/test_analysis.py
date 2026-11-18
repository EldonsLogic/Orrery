"""SEC-010 static analyser: malicious and benign fixtures. Dangerous or secret-looking literals are built at run time."""
import json
import os

import pytest

from conftest import codes
from factory import check
from factory.analysis import analyse_component
from factory.analysis.pyscan import Declared, scan_python
from factory.analysis.textscan import scan_json

D = Declared(requires=("core.trading_ar",), sends_to_models=False, local=frozenset({"loader"}), own_id="core.demo")
FAKE_KEY = "AK" + "IA" + "ABCDEFGHIJKLMNOP"          # runtime-built, never a literal
PEM = "-----" + "BEGIN RSA PRIVATE " + "KEY-----"


def run(src, declared=D):
    return scan_python(src, "m.py", declared)


def has(src, code, sev="high", declared=D):
    return any(i.code == code and i.severity == sev for i in run(src, declared))


@pytest.mark.parametrize("src,code", [
    ("import socket\ns = socket.socket()\n", "SA-001"),
    ("import requests\nrequests.get(u)\n", "SA-001"),
    ("from urllib.request import urlopen\n", "SA-001"),
    ("import subprocess\nsubprocess.run(['ls'])\n", "SA-003"),
    ("import os\nos.system('ls')\n", "SA-003"),
    ("from os import popen\n", "SA-003"),
    ("eval('1+1')\n", "SA-004"),
    ("exec('x=1')\n", "SA-004"),
    ("compile('x', 'f', 'exec')\n", "SA-004"),
    ("__import__('os')\n", "SA-005"),
    ("import importlib\nimportlib.import_module(n)\n", "SA-005"),
    ("import os\nk = os.environ['X']\n", "SA-006"),
    ("import os as o\nk = o.getenv('X')\n", "SA-006"),
    ("from os import environ\nk = environ['X']\n", "SA-006"),
    ("open('/etc/passwd')\n", "SA-002"),
    ("open('../up/file.txt')\n", "SA-002"),
    ("from pathlib import Path\nPath('/tmp/x').read_text()\n", "SA-002"),
    ("from pathlib import Path\nPath.home()\n", "SA-002"),
    ("import shutil\nshutil.rmtree('d')\n", "SA-002"),
    ("import os\nos.chdir('x')\n", "SA-002"),
    ("import frappe\n", "SA-007"),
    ("from frappe.model import document\n", "SA-007"),
    ("import erpnext.accounts\n", "SA-007"),
    ("import anthropic\n", "SA-008"),
    ("x = 'a'\ngetattr(x, name)()\n", "SA-009"),
    ("getattr(m, 'system')('ls')\n", "SA-009"),
    ("().__class__.__bases__[0].__subclasses__()\n", "SA-010"),
    ("f.__globals__['x']\n", "SA-010"),
    ("import pickle\npickle.loads(b)\n", "SA-011"),
    ("import yaml\nyaml.load(s)\n", "SA-011"),
    ("x = (\n", "SA-012"),
    ("token = '" + "a1b2c3d4e5f6g7h8" + "'\n", "SA-014"),
    ("k = '" + FAKE_KEY + "'\n", "SA-014"),
    ("k = '" + PEM + "'\n", "SA-014"),
    ("p = '~/.ssh/id_" + "rsa'\n", "SA-006"),
])
def test_malicious_patterns_flagged_high(src, code):
    assert has(src, code), [str(i) for i in run(src)]


def test_findings_carry_file_and_line():
    iss = run("x = 1\n\nimport subprocess\n")
    i = [i for i in iss if i.code == "SA-003"][0]
    assert (i.path, i.line, i.severity) == ("m.py", 3, "high") and str(i).startswith("m.py:3 SA-003 high")


def test_undeclared_component_and_third_party_are_medium():
    assert has("import components.core.pricing\n", "SA-008", "medium")
    assert has("import numpy\n", "SA-008", "medium")
    assert not run("import components.core.trading_ar.loader\n")        # declared in requires
    assert not run("import loader\n")                                    # provided by the component
    assert not run("import pytest\n")


def test_model_sdk_allowed_when_declared():
    d = Declared(sends_to_models=True)
    assert not [i for i in run("import anthropic\n", d) if i.severity == "high"]


def test_obfuscation_variants():
    blob = "QUJD" * 50
    assert has(f"x = '{blob}'\n", "SA-009", "medium")
    assert has("import base64\nb = base64.b64decode(s)\n", "SA-009", "medium")
    assert has("s = chr(101)+chr(118)+chr(97)+chr(108)\n", "SA-009", "medium")
    assert has("x = 1;" + " y = 2;" * 400 + "\n", "SA-009", "medium")
    assert has("аdmin = 1\n", "SA-009", "medium")  # Cyrillic a
    assert has("globals()[name]()\n", "SA-009")


def test_decode_then_exec_is_high():
    src = "import base64\nexec(base64.b64decode(s))\n"
    assert has(src, "SA-004") and has(src, "SA-009", "medium")


def test_url_literal_medium_but_reserved_hosts_ok():
    assert has("u = 'https://evil.net/x'\n", "SA-001", "medium")
    assert not run("u = 'https://docs.example/x'\n")


@pytest.mark.parametrize("src", [
    "from __future__ import annotations\nimport json, re\nfrom pathlib import Path\n"
    "def load(p):\n    return json.loads(Path(p).read_text(encoding='utf-8'))\n",
    "import dataclasses, decimal, datetime\nfrom typing import Any\n"
    "def total(rows):\n    return sum(decimal.Decimal(r['amount']) for r in rows)\n",
    "import os\nname = os.path.join('data', 'x.json')\nopen('data/x.json')\n",
    "import unittest\nclass T(unittest.TestCase):\n    def test(self):\n        self.assertEqual(1, 1)\n",
    "password = ''\napi_key = 'changeme'\nopen('data/rows.csv')\n",
    "x = getattr(obj, 'name')\nlabel = 'sk-learn style text'\n",
])
def test_benign_code_has_no_findings(src):
    assert run(src) == [], [str(i) for i in run(src)]


# JSON and server-script style files
def jscan(obj, manifest=False):
    return scan_json(json.dumps(obj, indent=2), "x.json", D, is_manifest=manifest)


def test_json_embedded_server_script_scanned_with_line():
    doc = {"name": "n", "scripts": [{"id": "a", "script": "import os\nv = os.getenv('K')\n"}]}
    iss = jscan(doc)
    hit = [i for i in iss if i.code == "SA-006"]
    assert hit and hit[0].severity == "high" and hit[0].line >= 5


def test_json_expression_and_url_and_secret_and_invalid():
    assert [i for i in jscan({"condition": "eval(x)"}) if i.code == "SA-004"]
    assert [i for i in jscan({"webhook": "https://evil.net/h"}) if i.code == "SA-001"]
    assert not [i for i in jscan({"label": "see https://evil.net/h"}) if i.code == "SA-001"]
    assert [i for i in jscan({"k": FAKE_KEY}) if i.code == "SA-014"]
    assert scan_json("{nope", "x.json", D)[0].code == "SA-012"
    assert scan_json('{"a": NaN}', "x.json", D)[0].code == "SA-012"


def test_json_duplicate_script_keys_both_scanned():
    iss = scan_json('{"script": "x = 1", "script": "import os\\nos.system(c)"}', "x.json", D)
    assert any(i.code == "SA-003" for i in iss)


def test_json_benign_translations():
    doc = {"Learn more": "تعلم المزيد", "script": "total = a + b"}
    assert jscan(doc) == []


# component level
def _comp(make, files):
    d = make()
    for rel, body in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body if isinstance(body, bytes) else body.encode("utf-8"))
    return d


def test_unsupported_and_binary_files_fail_closed(make):
    d = _comp(make, {"run.sh": "echo hi\n", "lib.so": b"\x7fELF", "mod.pyc": b"\x00\x01", "x.js": "1"})
    res = analyse_component(d)
    assert {i.path for i in res.issues if i.code == "SA-013"} == {"run.sh", "lib.so", "mod.pyc", "x.js"} and res.blocked
    (d / "bad.py").write_bytes(b"\xff\xfe\x00")
    assert any(i.code == "SA-013" for i in analyse_component(d).issues)
    (d / "bad.py").write_bytes(b"\xff\xfe")
    assert any(i.code == "SA-012" for i in analyse_component(d).issues)


def test_manifest_requires_and_models_flag_cross_check(make):
    d = make(lambda m: m.__setitem__("dataHandling", {"sendsDataToModels": True}))
    (d / "x.py").write_text("import anthropic\n")
    assert not analyse_component(d, json.loads((d / "manifest.json").read_text())).blocked
    m = json.loads((d / "manifest.json").read_text())
    m["dataHandling"] = {"sendsDataToModels": False}
    assert analyse_component(d, m).blocked


def test_deterministic_output(make):
    d = _comp(make, {"a.py": "import socket\nimport subprocess\neval(x)\n", "b.py": "import pickle\n"})
    a, b = analyse_component(d).as_dict(), analyse_component(d).as_dict()
    assert a == b and a["blocked"] and a["counts"]["high"] >= 4


def test_symlink_never_followed(make, tmp_path):
    d = make()
    os.symlink(tmp_path, d / "lnk")
    assert "FAC-003" in codes(check(d))  # rejected by the copier before analysis


# factory wiring: HIGH findings can never reach 'tested'
def test_high_finding_blocks_tested_and_tests_not_run(make):
    marker = "ran"
    body = "import subprocess\ndef test_x():\n    open('%s.txt', 'w').write('x')\n" % marker
    d = make(test_body=body)
    rep = check(d, run_tests=True, trusted_source=True, timeout=60)
    assert rep.level_reached == "draft" and not rep.ok and not rep.tests_run and not rep.tests
    assert {"SA-003", "FAC-015"} <= codes(rep)
    assert rep.as_dict()["analysis"]["blocked"] is True
    f = [f for f in rep.findings if f.code == "SA-003"][0]
    assert f.is_error and f.message.startswith("tests/test_ok.py:1 ")


def test_medium_finding_is_warning_and_does_not_block(make):
    d = make(test_body="import numpy\ndef test_ok():\n    assert True\n")
    rep = check(d, run_tests=True, trusted_source=True, timeout=60)
    f = [f for f in rep.findings if f.code == "SA-008"]
    assert f and not f[0].is_error
    assert rep.analysis["blocked"] is False


def test_clean_component_still_reaches_tested(make):
    rep = check(make(), run_tests=True, trusted_source=True, timeout=60)
    assert rep.level_reached == "tested" and rep.analysis["counts"]["high"] == 0, rep.findings


def test_high_in_static_only_mode_holds_at_draft(make):
    rep = check(_comp(make, {"x.py": "exec(s)\n"}))
    assert rep.level_reached == "draft" and not rep.ok and "SA-004" in codes(rep)


def test_analyser_crash_fails_closed(make, monkeypatch):
    import factory.analysis.analyse as A
    monkeypatch.setattr(A, "_file", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    rep = check(make(), run_tests=True, trusted_source=True, timeout=60)
    assert "SA-015" in codes(rep) and rep.level_reached == "draft" and not rep.ok
