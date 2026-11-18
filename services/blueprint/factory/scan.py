"""Safe copy of a candidate component into a fresh folder, with limits. Nothing is executed or imported."""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from . import errors as E

MAX_FILES = 500
MAX_TOTAL_BYTES = 5_000_000
MAX_FILE_BYTES = 1_000_000


@dataclass(frozen=True)
class Limits:
    max_files: int = MAX_FILES
    max_total_bytes: int = MAX_TOTAL_BYTES
    max_file_bytes: int = MAX_FILE_BYTES


def check_relpath(rel: str) -> str:
    """Return rel if it is a plain relative path that stays inside the component; else raise FAC-004."""
    if not isinstance(rel, str) or not rel or "\x00" in rel or "\\" in rel or rel.startswith("/") or len(rel) > 200:
        raise E.FacError(E.TRAVERSAL, f"unsafe path {rel!r}")
    if any(p in ("", "..") for p in rel.split("/")):
        raise E.FacError(E.TRAVERSAL, f"unsafe path {rel!r}")
    return rel


def copy_component(src: str | os.PathLike, dst: Path, limits: Limits = Limits()) -> int:
    """Copy src into the existing empty folder dst. Returns the file count. Raises FacError on any violation."""
    src = Path(src)
    try:
        st = os.lstat(src)
    except OSError as exc:
        raise E.FacError(E.CANDIDATE, f"cannot read candidate folder ({type(exc).__name__})")
    if stat.S_ISLNK(st.st_mode):
        raise E.FacError(E.CANDIDATE, "candidate folder is a symlink")
    if not stat.S_ISDIR(st.st_mode):
        raise E.FacError(E.CANDIDATE, "candidate is not a folder")
    files = total = 0
    for root, dirs, names in os.walk(src, followlinks=False):
        dirs.sort()
        rel_root = Path(root).relative_to(src)
        for d in list(dirs):
            if stat.S_ISLNK(os.lstat(Path(root) / d).st_mode):
                raise E.FacError(E.SPECIAL_FILE, f"symlink folder '{rel_root / d}'")
        (dst / rel_root).mkdir(parents=True, exist_ok=True)
        for name in sorted(names):
            p, rel = Path(root) / name, rel_root / name
            s = os.lstat(p)
            if not stat.S_ISREG(s.st_mode):
                raise E.FacError(E.SPECIAL_FILE, f"'{rel}' is a symlink or not a regular file")
            files += 1
            if files > limits.max_files:
                raise E.FacError(E.TOO_MANY, f"more than {limits.max_files} files")
            total += s.st_size
            if s.st_size > limits.max_file_bytes or total > limits.max_total_bytes:
                raise E.FacError(E.TOO_BIG, f"size limit exceeded at '{rel}'")
            fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                with os.fdopen(fd, "rb") as fh:
                    data = fh.read(limits.max_file_bytes + 1)
            except OSError as exc:
                raise E.FacError(E.SPECIAL_FILE, f"cannot read '{rel}' ({type(exc).__name__})")
            if len(data) > limits.max_file_bytes:
                raise E.FacError(E.TOO_BIG, f"'{rel}' grew past the file limit")
            (dst / rel).write_bytes(data)
    return files
