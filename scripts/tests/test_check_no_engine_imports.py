"""QA-022: the engine-import check flags real imports only (ADR-0080 point 3)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_no_engine_imports.py"


def run_check(files):
    """Write {relative path: source} under a temp services/ tree and run the check on it."""
    with tempfile.TemporaryDirectory() as temp:
        for rel, src in files.items():
            path = Path(temp) / "services" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(src, encoding="utf-8")
        r = subprocess.run([sys.executable, str(SCRIPT), "--root", temp], capture_output=True, text=True)
        return r.returncode, r.stdout


class NoEngineImportsTests(unittest.TestCase):
    def test_plain_import_flagged_with_file_and_line(self):
        code, out = run_check({"a/m.py": "import os\nimport frappe\n"})
        self.assertEqual(code, 1)
        self.assertIn("services/a/m.py:2: forbidden engine import frappe (ADR-0080)", out)

    def test_from_import_flagged(self):
        code, out = run_check({"m.py": "from erpnext.accounts import utils\n"})
        self.assertEqual(code, 1)
        self.assertIn("m.py:1: forbidden engine import erpnext (ADR-0080)", out)

    def test_hrms_and_submodule_flagged(self):
        code, out = run_check({"m.py": "import hrms.payroll\n"})
        self.assertEqual(code, 1)
        self.assertIn("forbidden engine import hrms", out)

    def test_dynamic_imports_flagged(self):
        src = "import importlib\nimportlib.import_module('frappe.utils')\n__import__('hrms')\n"
        code, out = run_check({"m.py": src})
        self.assertEqual(code, 1)
        self.assertIn("m.py:2: forbidden engine import frappe", out)
        self.assertIn("m.py:3: forbidden engine import hrms", out)

    def test_string_mention_not_flagged(self):
        code, out = run_check({"m.py": "x = 'import frappe'\ny = \"\"\"from erpnext import x\"\"\"\n"})
        self.assertEqual((code, out.strip()), (0, "OK"))

    def test_comment_not_flagged(self):
        code, _ = run_check({"m.py": "# import frappe\nimport os  # from hrms import x\n"})
        self.assertEqual(code, 0)

    def test_similar_names_not_flagged(self):
        code, _ = run_check({"m.py": "import frappe_client\nimport hrms_skeleton\nfrom myfrappe import x\n"})
        self.assertEqual(code, 0)

    def test_clean_tree(self):
        code, out = run_check({"m.py": "import json\n", "n/k.py": "from pathlib import Path\n"})
        self.assertEqual((code, out.strip()), (0, "OK"))

    def test_real_repo_passes(self):
        r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
