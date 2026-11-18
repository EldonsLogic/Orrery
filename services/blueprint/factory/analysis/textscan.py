"""JSON and other text files: embedded server scripts are scanned as Python; every string is checked for literals."""
from __future__ import annotations

import json
import re

from . import rules as R
from .codes import CREDENTIAL, HIGH, MEDIUM, NETWORK, SECRETS, UNPARSEABLE, Issue
from .pyscan import Declared, scan_python


class Pairs(list):
    """JSON object kept as a list of (key, value) so duplicate keys are not hidden."""


def _locate(lines: list, needle: str, start: int) -> int:
    for n in range(start, len(lines)):
        if needle in lines[n]:
            return n
    return start


def scan_literal(path: str, line: int, text: str, key: str | None = None) -> list:
    out = []
    if len(text) > 100_000:
        return out
    for rx, what in R.SECRET_LITERALS:
        if rx.search(text):
            out.append(Issue(path, line, CREDENTIAL, HIGH, f"hard-coded {what}"))
    if len(text) < 400:
        if any(rx.search(text) for rx in R.SENSITIVE_PATHS):
            out.append(Issue(path, line, SECRETS, HIGH, f"names a credential or system file: {text[:60]!r}"))
        m = R.URL.search(text)
        if m and not m.group(1).lower().endswith(R.SAFE_HOST_SUFFIX) and (key is None or key.lower() in R.URL_KEYS):
            out.append(Issue(path, line, NETWORK, MEDIUM, f"URL to host '{m.group(1)[:60]}'"))
    return out


def scan_json(text: str, path: str, declared: Declared, is_manifest: bool = False) -> list:
    try:
        data = json.loads(text, object_pairs_hook=Pairs, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
    except (ValueError, RecursionError) as exc:
        return [Issue(path, getattr(exc, "lineno", 1) or 1, UNPARSEABLE, HIGH, f"not valid JSON ({type(exc).__name__}); not analysed")]
    lines = text.splitlines()
    issues: list = []
    cursor = [0]

    def walk(node, key=None, depth=0):
        if depth > 60:
            issues.append(Issue(path, 1, UNPARSEABLE, HIGH, "JSON nested too deep to analyse"))
            return
        if isinstance(node, Pairs):
            for k, v in node:
                walk(v, k if isinstance(k, str) else None, depth + 1)
        elif isinstance(node, list):
            for v in node:
                walk(v, key, depth + 1)
        elif isinstance(node, str):
            needle = json.dumps(node, ensure_ascii=False)[1:41].rstrip("\\")
            n = _locate(lines, needle, cursor[0])
            cursor[0] = n
            line = n + 1
            if is_manifest and key in ("upstream", "licence", "owner", "description", "name"):
                return
            issues.extend(scan_literal(path, line, node, key))
            if key and key.lower() in R.CODE_KEYS and len(node) > 3 and re.search(r"[=()\[\]]|\bimport\b|\bdef\b|\breturn\b", node):
                body = node
                found = scan_python(body, path, declared, line_offset=line - 1, mode="exec", embedded=True)
                if found and found[0].code == UNPARSEABLE:  # a bare expression (condition, formula)
                    found = scan_python(body.strip(), path, declared, line_offset=line - 1, mode="eval", embedded=True)
                issues.extend(found)

    walk(data)
    return issues


def scan_text(text: str, path: str) -> list:
    """Any other text file: literals only (credentials, key blocks, credential file names)."""
    issues = []
    for n, ln in enumerate(text.splitlines(), 1):
        if len(ln) > 100_000:
            continue
        for rx, what in R.SECRET_LITERALS:
            if rx.search(ln):
                issues.append(Issue(path, n, CREDENTIAL, HIGH, f"hard-coded {what}"))
    return issues
