"""Storage behind an interface. First backend: a folder of manifest JSON files.

Layout: `<dir>/<component id>.json`, one manifest per file, version inside the manifest. To hold more than one
version of a component in one folder, name the extra files `<component id>@<version>.json`. The file name is
checked against the manifest (id, and version when present). Manifest content is data only: it is parsed with
`json` and never executed, imported or used to build a path.
"""
from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from . import issues as codes
from .issues import Issue

MAX_FILE_BYTES = 1_000_000  # 1 MB
ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,3}$")
NAME_RE = re.compile(r"^([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){1,3})(?:@([0-9A-Za-z.+-]{1,100}))?\.json$")


@dataclass(frozen=True)
class RawManifest:
    """One stored item: parsed JSON (None when it could not be read) plus store-level findings."""

    name: str
    data: Any
    issues: tuple = ()
    name_id: str | None = None
    name_version: str | None = None


class ManifestStore(Protocol):
    """What a registry backend must offer. A service can replace the folder backend by implementing this."""

    def read_all(self) -> list[RawManifest]: ...


def _reject(name: str, message: str) -> RawManifest:
    return RawManifest(name, None, (Issue(codes.FILE, codes.ERROR, name, message),))


class DirectoryStore:
    """Reads `*.json` files directly inside one folder (not recursive), in sorted name order."""

    def __init__(self, directory: str | os.PathLike):
        self.directory = Path(directory)

    def read_all(self) -> list[RawManifest]:
        out = []
        for name in sorted(os.listdir(self.directory)):
            if not name.endswith(".json"):
                continue
            out.append(self._read_one(name))
        return out

    def _read_one(self, name: str) -> RawManifest:
        m = NAME_RE.match(name)
        if not m:
            return _reject(name, "file name must be '<component id>.json' or '<component id>@<version>.json'")
        full = os.path.join(self.directory, name)
        try:
            st = os.lstat(full)
        except OSError as exc:
            return _reject(name, f"cannot stat file ({type(exc).__name__})")
        if stat.S_ISLNK(st.st_mode):
            return _reject(name, "symbolic links are not accepted")
        if not stat.S_ISREG(st.st_mode):
            return _reject(name, "not a regular file")
        if st.st_size > MAX_FILE_BYTES:
            return _reject(name, f"file is larger than {MAX_FILE_BYTES} bytes")
        try:
            with open(full, "rb") as fh:
                raw = fh.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                return _reject(name, f"file is larger than {MAX_FILE_BYTES} bytes")
            data = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError, RecursionError) as exc:  # UnicodeDecodeError is a ValueError
            return _reject(name, f"cannot read file as JSON ({type(exc).__name__})")
        if not isinstance(data, dict):
            return _reject(name, "manifest must be a JSON object")
        return RawManifest(name, data, (), m.group(1), m.group(2))
