"""SEC-010 evasion corpus from the Tier 3 review of PR #172. Every case here produced no HIGH finding before the
allow-list rewrite; each must now produce at least one HIGH finding. Secret-looking literals are built at run time."""
import sys

import pytest

from factory import commands
from factory.analysis import analyse_component
from factory.analysis.pyscan import Declared, scan_python
from factory.analysis.textscan import scan_json

D = Declared(requires=("core.trading_ar",), local=frozenset({"loader"}), own_id="core.demo")
SYS = "sys" + "tem"

EVASIONS = {
    # H2 builtin referenced without a call
    "alias_eval": "e = eval\ne(s)\n",
    "alias_import": "i = __import__\ni('o' + 's')\n",
    "lambda_returns_eval": "(lambda: eval)()(s)\n",
    "exec_as_decorator": "d = exec\n@d\nclass C:\n    pass\n",
    "alias_open": "f = open\nf('out.txt', 'w')\n",
    # H3 builtins reached through __self__ and __dict__
    "self_eval": "len.__self__.eval(s)\n",
    "self_dict_exec": "len.__self__.__dict__['ex' + 'ec'](s)\n",
    "module_dict": f"import os\nos.__dict__['{SYS[:3]}' + '{SYS[3:]}']('id')\n",
    # H4 shadowing by an import that fails at run time
    "shadow_by_import": "try:\n    from json import nope as eval\nexcept ImportError:\n    pass\neval(s)\n",
    # H5 aliasing and star imports
    "module_alias": f"import os\nx = os\nx.{SYS}('id')\n",
    "module_in_tuple": f"import os\n(os,)[0].{SYS}('id')\n",
    "star_import": f"from os import *\n{SYS}('id')\n",
    "getattr_module": "import os\ngetattr(os, 'execvp')\n",
    "attrgetter": f"import operator, os\noperator.attrgetter('{SYS[:3]}' + '{SYS[3:]}')(os)('id')\n",
    # H6 os process and environment families
    **{f"os_{n}": f"import os\nos.{n}\n" for n in (
        "spawnl", "spawnv", "posix_spawnp", "environb", "execvpe", "execle", "execlpe", "forkpty", "putenv")},
    # H7 stdlib modules that reach os or run code
    "os_path_os": f"import os\nos.path.os.{SYS}('id')\n",
    "logging_os": f"import logging\nlogging.os.{SYS}('id')\n",
    "timeit": "import timeit\ntimeit.timeit(s)\n",
    "pdb": "import pdb\npdb.run(s)\n",
    "cprofile": "import cProfile\ncProfile.run(s)\n",
    "logging_dictconfig": f"import logging.config\nlogging.config.dictConfig({{'()': 'os.{SYS}'}})\n",
    "logging_http": "import logging.handlers\nlogging.handlers.HTTPHandler('h', '/u')\n",
    "asyncio_connection": "import asyncio\nasyncio.get_event_loop().create_connection(P, 'h', 1)\n",
    "process_pool": "from concurrent.futures import ProcessPoolExecutor\n",
    "types_function": "import types\ntypes.FunctionType(c, {})\n",
    "get_type_hints": "import typing\ntyping.get_type_hints(f)\n",
    # extra cases from the review's MEDIUM and LOW items
    "string_annotation": f"def f(x: \"__import__('os').{SYS}('id')\"):\n    pass\n",
    "parent_package_import": "from components.core import pricing\n",
    "factory_import": "import factory\n",
    "registry_import": "import registry.store\n",
    "psycopg3": "import psycopg\n",
    "unknown_third_party": "import httplib2\n",
    "format_walk": "'{0.__init__.__globals__}'.format(o)\n",
    "mock_patch": "from unittest import mock\n",
    "importorskip": "import pytest\npytest.importorskip(n)\n",
    "rebind_getattr_param": "def f(getattr):\n    return getattr\n",
    "relative_escape": "from ... import other\n",
}


@pytest.mark.parametrize("name", sorted(EVASIONS))
def test_evasion_produces_high(name):
    iss = scan_python(EVASIONS[name], "m.py", D)
    assert any(i.severity == "high" for i in iss), (name, [str(i) for i in iss])


def test_corpus_covers_the_review():
    assert len(EVASIONS) >= 36


def _write(root, files):
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body if isinstance(body, bytes) else body.encode("utf-8"))
    return root


def _high_paths(root):
    return {i.path for i in analyse_component(root).issues if i.severity == "high"}


# H1 coding line
@pytest.mark.parametrize("cookie", [b"# -*- coding: utf-7 -*-", b"# vim: set fileencoding=latin-1 :", b"#coding=cp1252"])
def test_coding_line_other_than_utf8_is_high(tmp_path, cookie):
    body = cookie + b"\nx = 1 # +AAo-print(\"HIDDEN\")\n"
    _write(tmp_path, {"m.py": body})
    iss = analyse_component(tmp_path).issues
    assert [i for i in iss if i.code == "SA-013" and i.path == "m.py" and i.severity == "high"]


def test_utf8_coding_line_is_fine(tmp_path):
    _write(tmp_path, {"m.py": b"# -*- coding: utf-8 -*-\nx = 1\n"})
    assert analyse_component(tmp_path).issues == []


# H8 runner configuration and doctest text inside the component
@pytest.mark.parametrize("name", ["conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml",
                                  "sitecustomize.py", "tests/conftest.py", "x.pth"])
def test_runner_config_files_refused(tmp_path, name):
    _write(tmp_path, {name: "[pytest]\n" if not name.endswith(".py") else "x = 1\n"})
    assert name in _high_paths(tmp_path)


def test_doctest_text_refused(tmp_path):
    _write(tmp_path, {"tests/test_doc.txt": ">>> 1 + 1\n2\n", "notes.md": "plain text\n"})
    assert _high_paths(tmp_path) == {"tests/test_doc.txt"}


def test_shebang_and_shadowing_and_empty_folder(tmp_path):
    _write(tmp_path, {"run": "#!/bin/sh\necho hi\n", "json.py": "x = 1\n", "tests/re.py": "x = 1\n",
                      "pkg/__init__.py": "", "pkg/json.py": "x = 1\n", "httplib2/README.md": "empty\n",
                      "app.py": "import httplib2\n"})
    assert _high_paths(tmp_path) == {"run", "json.py", "tests/re.py", "app.py"}


def test_analyser_reports_symlink_itself(tmp_path):
    (tmp_path / "real.py").write_text("x = 1\n")
    (tmp_path / "link.py").symlink_to(tmp_path / "real.py")
    iss = analyse_component(tmp_path).issues
    assert [i for i in iss if i.path == "link.py" and i.code == "SA-013" and i.severity == "high"]


# M1 embedded non-Python scripts
@pytest.mark.parametrize("doc", [
    {"doctype": "Client Script", "script": "x = 1"},
    {"language": "javascript", "code": "x = 1"},
    {"script": "frappe.ui.form.on('Item', { refresh(frm) { } });"},
    {"condition": "{% if doc.total %}yes{% endif %}"},
])
def test_embedded_non_python_is_high(doc):
    import json
    iss = scan_json(json.dumps(doc, indent=2), "x.json", D)
    assert any(i.severity == "high" and i.code == "SA-013" for i in iss), [str(i) for i in iss]


def test_embedded_python_still_scanned_and_code_key_lenient():
    import json
    assert not [i for i in scan_json(json.dumps({"script": "total = a + b", "code": "1.0.0"}), "x.json", D)
                if i.severity == "high"]
    assert any(i.code == "SA-003" for i in scan_json(json.dumps({"script": f"import os\nos.{SYS}(c)"}), "x.json", D))


# M5 credential names need a key-like value; values are built at run time
def test_credential_rule_needs_key_like_value():
    key = "Zx9" + "Qw7Lm2Pa8Rt5"
    assert any(i.code == "SA-014" for i in scan_python(f"api_key = '{key}'\n", "m.py", D))
    assert any(i.code == "SA-014" for i in scan_python(f"dbPassword = '{key}'\n", "m.py", D))
    assert not scan_python("author = 'Jane Doe Smith'\nauth_mode = 'basic'\n", "m.py", D)


# H8 the runner itself ignores component-controlled pytest config, conftest, plugins and doctests
def test_runner_ignores_component_pytest_config(tmp_path):
    work, home = tmp_path / "w", tmp_path / "h"
    home.mkdir()
    marker = "open('{0}', 'w').write('x')\n"
    _write(work, {
        "pytest.ini": "[pytest]\naddopts = -p evilplug --doctest-glob=*.md\n",
        "evilplug.py": marker.format("plugin_ran.txt"),
        "conftest.py": marker.format("conf_ran.txt"),
        "tests/conftest.py": marker.format("conf2_ran.txt"),
        "tests/test_doc.txt": ">>> " + marker.format("doc_ran.txt") + "1\n",
        "tests/notes.md": ">>> " + marker.format("md_ran.txt") + "1\n",
        "tests/test_ok.py": "def test_ok():\n    assert True\n",
    })
    ran = ["plugin_ran.txt", "conf_ran.txt", "conf2_ran.txt", "doc_ran.txt", "md_ran.txt"]
    res = commands.run_allowed("pytest", "tests", work, home, 60)
    assert res.returncode == 0, res.tail
    assert [m for m in ran if (work / m).exists()] == []
    # control: the old argv template does pick them up, so the assertion above is meaningful
    old = {"pytest": [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", ".", "{path}"]}
    commands.run_allowed("pytest", "tests", work, home, 60, allowed=old)
    assert all((work / m).exists() for m in ("plugin_ran.txt", "conf_ran.txt", "md_ran.txt"))
