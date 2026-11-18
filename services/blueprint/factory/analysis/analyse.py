"""Walk a component folder and run the deterministic static analysis (SEC-010). No file is imported or run."""
from __future__ import annotations

import os
from pathlib import Path

from . import rules as R
from .codes import INTERNAL_ERROR, UNPARSEABLE, UNSUPPORTED, HIGH, Analysis, Issue
from .pyscan import Declared, scan_python
from .textscan import scan_json, scan_text

MAX_FILE_BYTES = 1_000_000


def declared_from(manifest: dict, root: Path) -> Declared:
    reqs = []
    for r in manifest.get("requires") or []:
        if isinstance(r, dict) and isinstance(r.get("component"), str):
            reqs.append(r["component"])
    dh = manifest.get("dataHandling")
    sends = isinstance(dh, dict) and dh.get("sendsDataToModels") is True
    local = {p.stem for p in root.iterdir() if p.suffix == ".py"} | {p.name for p in root.iterdir() if p.is_dir()}
    cid = manifest.get("id") if isinstance(manifest.get("id"), str) else ""
    return Declared(tuple(reqs), sends, frozenset(local), cid)


def _file(root: Path, p: Path, declared: Declared) -> list:
    rel = p.relative_to(root).as_posix()
    ext = p.suffix.lower()
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
        return scan_python(text, rel, declared)
    if ext == ".json":
        return scan_json(text, rel, declared, is_manifest=(rel == "manifest.json"))
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
            for name in sorted(names):
                p = Path(dirpath) / name
                if p.is_symlink() or not p.is_file():
                    res.issues.append(Issue(p.relative_to(root).as_posix(), 1, UNSUPPORTED, HIGH, "not a regular file"))
                    continue
                res.files += 1
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
