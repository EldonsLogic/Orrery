#!/usr/bin/env python3
"""Regex secret scan over the working tree. Exit 1 on any hit."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}
SKIP_PREFIXES = ("docs/brand/",)
SKIP_FILES = {".env.example", "scripts/scan_secrets.py"}
BIN_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2", ".ttf", ".otf", ".zip", ".gz"}

PATTERNS = [
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{50,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenAI-style key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("password assignment", re.compile(r"""(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|token)\b\s*[:=]\s*["'][^"'\s$<{][^"'\s]{7,}["']""")),
]
PLACEHOLDER = re.compile(r"(?i)(example|placeholder|changeme|your[_-]|xxxx|dummy|test|sample|redacted|<)")


def files():
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if set(p.relative_to(ROOT).parts) & SKIP_DIRS:
            continue
        if rel in SKIP_FILES or rel.startswith(SKIP_PREFIXES) or p.suffix.lower() in BIN_EXT:
            continue
        yield p, rel


def main():
    hits = 0
    for p, rel in files():
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for label, rx in PATTERNS:
                m = rx.search(line)
                if m and label == "password assignment" and PLACEHOLDER.search(m.group(0)):
                    continue
                if m:
                    print(f"{rel}:{n}: possible {label}")
                    hits += 1
    print(f"secret scan: {hits} hit(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
