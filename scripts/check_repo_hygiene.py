#!/usr/bin/env python3
"""Repo hygiene gate. Fails when the repo contains things that do not belong in it.

Checks (tracked files plus untracked files that are not git-ignored):
  1. Top-level entries and docs/ layout follow the allow-lists below.
  2. No scratch, temp, backup, archive or office/PDF files; no oversized files.
  3. No local machine paths, scratch references or the retired prototype name in text files.
  4. Every Markdown file starts with a level-1 heading.
  5. The engine's name does not appear on customer-visible paths (web/, locale, template, fixture,
     print-format and public-asset folders, docs/brand). ADR-0016.

Run before finishing any session: python3 scripts/check_repo_hygiene.py
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOP_LEVEL_OK = {
    ".editorconfig", ".env.example", ".git", ".github", ".gitignore", ".pre-commit-config.yaml",
    "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "GEMINI.md", "LICENSE", "NOTICE.md", "README.md", "SECURITY.md",
    "agents", "apps", "components", "connectors", "contracts", "docs", "evals", "infra", "scripts",
    "services", "web",
}
DOCS_FILES_OK = {
    "00-START-HERE.md", "ONBOARDING.md", "RULES.md", "PLAN.md", "GATES.md", "STATUS.md", "CHANGELOG.md", "risks.md",
    "open-questions.md", "glossary.md", "HANDOFF.md",
}
DOCS_DIRS_OK = {
    "log", "decisions", "specs", "architecture", "product", "compliance", "security", "legal",
    "brand", "gtm", "fundraising", "research", "strategy", "runbooks",
}
BAD_NAME = re.compile(
    r"(^|[/_\-. ])(scratch|tmp|temp|untitled|backup|old|final[_-]?final|copy of)([/_\-. ]|$)|\(\d+\)|~$",
    re.I,
)
BAD_EXT = {
    ".bak", ".orig", ".swp", ".log", ".zip", ".tar", ".gz", ".tgz", ".7z", ".rar",
    ".pdf", ".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls", ".key", ".pages", ".numbers", ".mov", ".mp4",
}
MAX_BYTES = 1_000_000
TEXT_EXT = {
    ".md", ".py", ".json", ".yml", ".yaml", ".toml", ".txt", ".js", ".ts", ".tsx", ".css", ".html",
    ".svg", ".sh", ".cfg", ".ini", ".example", ".gitignore", ".editorconfig",
}
FORBIDDEN_TEXT = [
    (re.compile(r"(?<![\w/.:-])(/Users/[A-Za-z0-9_.-]+/|/private/tmp/|/home/[a-z0-9_.-]+/)|[A-Za-z]:\\Users\\"), "local machine path"),
    (re.compile(r"scratchpad|\bsession scratch\b", re.I), "scratch reference"),
    (re.compile(r"exrp", re.I), "retired prototype name (say 'change engine')"),
]
# files allowed to mention things the checks otherwise forbid
ALLOW_TEXT = {
    "apps/engine/change_engine/PROVENANCE.md": {"retired prototype name (say 'change engine')"},
    "NOTICE.md": {"retired prototype name (say 'change engine')"},
    "scripts/check_repo_hygiene.py": {"local machine path", "scratch reference", "retired prototype name (say 'change engine')"},
    "scripts/scan_secrets.py": {"local machine path"},
}


# ADR-0016: the engine's name must never appear on customer-visible surfaces.
ENGINE_NAME = re.compile(r"frappe|erpnext", re.I)
VISIBLE_PATH = re.compile(
    r"^(web/|docs/brand/)|/(locales?|i18n|translations|templates|fixtures|print_format|public)/"
)
VISIBLE_EXEMPT = re.compile(r"(^|/)README\.md$|^apps/engine/[^/]+/(PROVENANCE|README)\.md$")


def repo_files():
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
        files = [f for f in out.splitlines() if f and os.path.exists(os.path.join(ROOT, f))]
        return sorted(set(files))
    except Exception:
        found = []
        for d, dirs, fs in os.walk(ROOT):
            dirs[:] = [x for x in dirs if x not in {".git", "node_modules", "__pycache__", ".venv"}]
            for f in fs:
                found.append(os.path.relpath(os.path.join(d, f), ROOT))
        return sorted(found)


def main():
    errors = []
    files = repo_files()

    tops = {f.split("/")[0] for f in files}
    for t in sorted(tops - TOP_LEVEL_OK):
        errors.append(f"top-level entry not allowed: {t} (allowed: see scripts/check_repo_hygiene.py)")

    for f in files:
        parts = f.split("/")
        base = parts[-1]
        ext = os.path.splitext(base)[1].lower()
        if parts[0] == "docs" and len(parts) == 2 and base not in DOCS_FILES_OK:
            errors.append(f"{f}: not an allowed file directly under docs/")
        if parts[0] == "docs" and len(parts) > 2 and parts[1] not in DOCS_DIRS_OK:
            errors.append(f"{f}: docs/{parts[1]}/ is not an allowed docs folder")
        if parts[0] == "docs" and len(parts) == 2 and os.path.isdir(os.path.join(ROOT, f)):
            continue
        if base in {".DS_Store", "Thumbs.db"} or "__pycache__" in parts or "node_modules" in parts:
            errors.append(f"{f}: junk or dependency folder must not be in the repo")
        if BAD_NAME.search(f):
            errors.append(f"{f}: scratch/temp/backup/duplicate-looking name")
        if ext in BAD_EXT:
            errors.append(f"{f}: file type not allowed in the repo ({ext}); external documents live outside the repo")
        full = os.path.join(ROOT, f)
        try:
            size = os.path.getsize(full)
        except OSError:
            continue
        if size > MAX_BYTES:
            errors.append(f"{f}: {size} bytes exceeds {MAX_BYTES} byte limit")
        if ext in TEXT_EXT or base in {".gitignore", ".editorconfig", ".env.example"}:
            try:
                text = open(full, encoding="utf-8").read()
            except Exception:
                continue
            allowed = ALLOW_TEXT.get(f, set())
            for pat, label in FORBIDDEN_TEXT:
                if label in allowed:
                    continue
                m = pat.search(text)
                if m:
                    line = text[: m.start()].count("\n") + 1
                    errors.append(f"{f}:{line}: {label}")
            if (VISIBLE_PATH.search(f) and not VISIBLE_EXEMPT.search(f) and ENGINE_NAME.search(text)
                    and not f.startswith("apps/engine/")):
                line = next(i for i, ln in enumerate(text.splitlines(), 1) if ENGINE_NAME.search(ln))
                errors.append(f"{f}:{line}: engine name on a customer-visible surface (ADR-0016)")
            if ext == ".md" and not f.startswith(".github/") and f != "CLAUDE.md":
                first = next((ln for ln in text.splitlines() if ln.strip()), "")
                if not first.startswith("# "):
                    errors.append(f"{f}: Markdown must start with a '# ' heading")

    if errors:
        print("Repo hygiene FAILED:")
        for e in errors:
            print("  - " + e)
        print(f"{len(errors)} problem(s).")
        return 1
    print(f"Repo hygiene OK ({len(files)} files checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
