"""Canonical JSON, digests, edits and the field-level diff. Plain data only (dict, list, str, int, bool, None);
floats are refused so one content has one byte string. Nothing here computes or interprets a tax value."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import re

from .errors import PublishError

FILES = ("pack.json", "manifest.json", "evidence.json", "strings.json")
IDENTITY = ("packId", "countryCode", "componentId", "version")  # set by the workflow, never by an edit
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}\Z")
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}\Z")
SUBJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}\Z")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")  # release versions only, no pre-release


def canonical(obj) -> bytes:
    _plain(obj, 0)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


SIGNOFF_DOMAIN = b"country-pack-signoff-v1\n"


def signoff_challenge(statement_digest: str) -> str:
    """The WebAuthn challenge each signer's assertion must carry (ADR-0071 1.8, Eldon's #344 answer): base64url
    without padding of SHA-256(`country-pack-signoff-v1\\n` + the ASCII statementDigest), so an assertion over a
    sign-off cannot be replayed for anything else."""
    raw = hashlib.sha256(SIGNOFF_DOMAIN + statement_digest.encode("ascii")).digest()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _plain(v, depth):
    if depth > 24:
        raise PublishError("PP-002")
    t = type(v)
    if v is None or t in (bool, int):
        return
    if t is str:
        try:
            v.encode("utf-8")
        except UnicodeEncodeError:
            raise PublishError("PP-002") from None
        return
    if t is list:
        for x in v:
            _plain(x, depth + 1)
    elif t is dict:
        for k, x in v.items():
            if type(k) is not str:
                raise PublishError("PP-002")
            _plain(x, depth + 1)
    else:
        raise PublishError("PP-002")


def semver(v) -> tuple:
    m = SEMVER_RE.match(v) if isinstance(v, str) else None
    if not m:
        raise PublishError("PP-001")
    return tuple(int(x) for x in m.groups())


def parse_files(files: dict) -> dict:
    """Stored bytes -> parsed JSON per file; the closed file set and plain JSON are enforced."""
    if not isinstance(files, dict) or not {"pack.json", "manifest.json", "evidence.json"} <= set(files) or set(files) - set(FILES):
        raise PublishError("PP-002")
    out = {}
    for path, raw in files.items():
        if type(raw) is not bytes or not 1 <= len(raw) <= 1048576:
            raise PublishError("PP-002")
        try:
            val = json.loads(raw.decode("utf-8"), parse_float=_no_float, parse_constant=_no_float)
        except (ValueError, UnicodeDecodeError):
            raise PublishError("PP-002") from None
        _plain(val, 0)
        out[path] = val
    return out


def _no_float(_):
    raise ValueError("float")


def file_entries(files: dict) -> list:
    return [{"path": p, "sha256": digest(files[p]), "size": len(files[p])} for p in sorted(files)]


def content_digest(country: str, pack_id: str, version: str, files: dict) -> str:
    return digest(canonical({"countryCode": country, "packId": pack_id, "version": version, "files": file_entries(files)}))


def _parent(root, segs):
    cur = root
    for s in segs[:-1]:
        cur = _step(cur, s)
    return cur


def _step(cur, seg):
    if isinstance(cur, dict) and seg in cur:
        return cur[seg]
    if isinstance(cur, list) and seg.isdigit() and int(seg) < len(cur):
        return cur[int(seg)]
    raise PublishError("PP-003")


def apply_edit(parsed: dict, edit: dict) -> None:
    """edit: {file, path (dotted), op: set|delete, value}. The parent of the path must already exist."""
    if set(edit) - {"file", "path", "op", "value"} or edit.get("file") not in parsed or edit.get("op") not in ("set", "delete"):
        raise PublishError("PP-003")
    path = edit.get("path")
    if not isinstance(path, str) or not path:
        raise PublishError("PP-003")
    segs = path.split(".")
    if edit["file"] in ("pack.json", "manifest.json") and len(segs) == 1 and segs[0] in IDENTITY:
        raise PublishError("PP-003")
    parent, last = _parent(parsed[edit["file"]], segs), segs[-1]
    if edit["op"] == "delete":
        _step(parent, last)
        del parent[last if isinstance(parent, dict) else int(last)]
        return
    value = copy.deepcopy(edit.get("value"))
    _plain(value, 0)
    if isinstance(parent, dict):
        parent[last] = value
    elif isinstance(parent, list) and last.isdigit() and int(last) <= len(parent):
        parent[int(last):int(last) + 1] = [value]
    else:
        raise PublishError("PP-003")


def _walk(path, a, b, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            _walk(path + [k], a.get(k, _MISSING), b.get(k, _MISSING), out)
    elif isinstance(a, list) and isinstance(b, list):
        for i in range(max(len(a), len(b))):
            _walk(path + [str(i)], a[i] if i < len(a) else _MISSING, b[i] if i < len(b) else _MISSING, out)
    elif a is _MISSING and b is not _MISSING:
        out.append((path, "added", None, b))
    elif b is _MISSING and a is not _MISSING:
        out.append((path, "removed", a, None))
    elif a != b or type(a) is not type(b):
        out.append((path, "changed", a, b))


_MISSING = object()


def diff(base: dict, new: dict, product_paths) -> list:
    """Field-level changes between two parsed bundles, sorted by (file, path). A change is `product_choice` only
    when it is in pack.json and its dotted path is exactly on the market's product-choice list; everything else
    (other files, unlisted paths) is `statutory`, so unknown means the stricter class. The top-level version
    key is the release identity, not content, and is left out."""
    changes = []
    for f in sorted(set(base) | set(new)):
        a, b = base.get(f, _MISSING), new.get(f, _MISSING)
        if f in ("pack.json", "manifest.json"):
            a, b = _no_version(a), _no_version(b)
        rows = []
        _walk([], a, b, rows)
        for segs, op, before, after in rows:
            dotted = ".".join(segs)
            cls = "product_choice" if f == "pack.json" and dotted in product_paths else "statutory"
            changes.append({"file": f, "path": dotted, "op": op, "before": before, "after": after, "class": cls})
    return sorted(changes, key=lambda c: (c["file"], c["path"]))


def _no_version(v):
    if isinstance(v, dict):
        v = dict(v)
        v.pop("version", None)
    return v
