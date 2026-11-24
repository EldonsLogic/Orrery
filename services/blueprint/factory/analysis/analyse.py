"""Walk a component folder and run the deterministic static analysis (SEC-010). No file is imported or run."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import rules as R
from .codes import HIGH, INTERNAL_ERROR, UNDECLARED, UNPARSEABLE, UNSUPPORTED, Analysis, Issue
from .pyscan import Declared, scan_python
from .textscan import scan_json, scan_text

MAX_FILE_BYTES = 1_000_000
# Module names a component file or folder must not shadow (PYTHONPATH puts the component first on sys.path).
_STD = getattr(sys, "stdlib_module_names", None) or frozenset()
SHADOWED = (frozenset(_STD) | R.SAFE_MODULES | {m.split(".")[0] for m in R.MODULE_RULES} |
            {"pytest", "_pytest", "pluggy", "iniconfig", "packaging", "py", "os", "sys", "builtins"}) - {"test", "tests"}


def _is_package(d: Path) -> bool:
    """A folder counts as an importable local module only if it holds Python files (an empty folder does not)."""
    return any(p.suffix == ".py" and p.is_file() and not p.is_symlink() for p in d.rglob("*.py"))


def declared_from(manifest: dict, root: Path) -> Declared:
    reqs = []
    for r in manifest.get("requires") or []:
        if isinstance(r, dict) and isinstance(r.get("component"), str):
            reqs.append(r["component"])
    dh = manifest.get("dataHandling")
    sends = isinstance(dh, dict) and dh.get("sendsDataToModels") is True
    local = ({p.stem for p in root.iterdir() if p.suffix == ".py" and p.is_file()} |
             {p.name for p in root.iterdir() if p.is_dir() and not p.is_symlink() and _is_package(p)})
    cid = manifest.get("id") if isinstance(manifest.get("id"), str) else ""
    return Declared(tuple(reqs), sends, frozenset(local), cid)


def _shadows(root: Path, p: Path) -> list:
    """A module or package that can land on sys.path (component root, or a test folder pytest inserts because it has
    no __init__.py) must not take the name of a standard or test-runner module."""
    rel = p.relative_to(root).as_posix()
    parent = p.parent
    if parent != root and (parent / "__init__.py").is_file():
        return []
    name = p.stem if p.suffix == ".py" else p.name
    if name in SHADOWED:
        return [Issue(rel, 1, UNDECLARED, HIGH, f"'{rel}' shadows the module '{name}'; rename it")]
    return []


def _file(root: Path, p: Path, declared: Declared) -> list:
    rel = p.relative_to(root).as_posix()
    ext = p.suffix.lower()
    if p.name.lower() in R.RUNNER_CONFIG_FILES or ext == ".pth":
        return [Issue(rel, 1, UNSUPPORTED, HIGH, f"'{p.name}' is test-runner or interpreter configuration; it is "
                      "refused whatever it holds")]
    if ext in R.BINARY_EXT or ext in R.SCRIPT_EXT:
        return [Issue(rel, 1, UNSUPPORTED, HIGH, f"'{ext}' files cannot be analysed (compiled, packed or non-Python code)")]
    data = p.read_bytes()
    if b"\x00" in data:
        return [Issue(rel, 1, UNSUPPORTED, HIGH, "binary content cannot be analysed")]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [Issue(rel, 1, UNPARSEABLE, HIGH, "not valid UTF-8; not analysed")]
    if ext == ".py":
        head = b"\n".join(data.splitlines()[:2])
        m = R.CODING.search(head)
        if m and m.group(1).decode("ascii", "replace").lower().replace("_", "-") not in ("utf-8", "utf8"):
            return [Issue(rel, 1, UNSUPPORTED, HIGH, "source coding line other than utf-8; the interpreter would read "
                          "different text than the analyser")]
        return scan_python(text, rel, declared, source=data, max_rel_level=rel.count("/") + 1)
    if ext == ".json":
        return scan_json(text, rel, declared, is_manifest=(rel == "manifest.json"))
    if ext == "" and data.startswith(b"#!"):
        return [Issue(rel, 1, UNSUPPORTED, HIGH, "script with a '#!' line cannot be analysed")]
    if ext in R.TEXT_EXT or p.name.startswith("."):
        return scan_text(text, rel)
    return [Issue(rel, 1, UNSUPPORTED, HIGH, f"unknown file type '{ext}' cannot be analysed")]


def analyse_component(root: str | os.PathLike, manifest: dict | None = None) -> Analysis:
    """Analyse every file under root. Never raises: an internal failure is a HIGH finding (fail closed)."""
    res = Analysis()
    root = Path(root)
    try:
        declared = declared_from(manifest or {}, root)
        seen = set()
        for dirpath, dirs, names in os.walk(root, followlinks=False):
            dirs.sort()
            for d in dirs:
                if _is_package(Path(dirpath) / d):
                    res.issues.extend(_shadows(root, Path(dirpath) / d))
            for name in sorted(names):
                p = Path(dirpath) / name
                if p.is_symlink() or not p.is_file():
                    res.issues.append(Issue(p.relative_to(root).as_posix(), 1, UNSUPPORTED, HIGH, "not a regular file"))
                    continue
                res.files += 1
                if p.suffix == ".py":
                    res.issues.extend(_shadows(root, p))
                if p.stat().st_size > MAX_FILE_BYTES:
                    res.issues.append(Issue(p.relative_to(root).as_posix(), 1, UNSUPPORTED, HIGH, "file over 1 MB"))
                    continue
                for i in _file(root, p, declared):
                    if i not in seen:
                        seen.add(i)
                        res.issues.append(i)
    except Exception as exc:  # fail closed
        res.issues.append(Issue(".", 1, INTERNAL_ERROR, HIGH, f"static analysis failed ({type(exc).__name__})"))
    order = {"high": 0, "medium": 1, "low": 2}
    res.issues.sort(key=lambda i: (order[i.severity], i.path, i.line, i.code))
    return res
