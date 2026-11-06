#!/usr/bin/env python3
"""Docs gate: required files, log headers, ADR index, PLAN table, links, STATUS freshness.

--allow-missing-prefix a/,b/  skip required-file and link checks for paths under these
prefixes (used while other authors' paths are still being written).
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_lib import ROOT, parse_plan, log_files, adr_files
import build_status

REQUIRED = [
    "AGENTS.md", "CLAUDE.md", "GEMINI.md", "README.md", "CONTRIBUTING.md", "SECURITY.md", "NOTICE.md",
    ".gitignore", ".editorconfig", ".env.example", ".pre-commit-config.yaml",
    ".github/CODEOWNERS", ".github/PULL_REQUEST_TEMPLATE.md", ".github/dependabot.yml",
    ".github/workflows/ci.yml", ".github/ISSUE_TEMPLATE/config.yml",
    "agents/README.md", "agents/routing.md", "agents/model-registry.md", "agents/delegation-playbook.md",
    "docs/00-START-HERE.md", "docs/RULES.md", "docs/PLAN.md", "docs/GATES.md", "docs/STATUS.md", "docs/CHANGELOG.md",
    "docs/risks.md", "docs/open-questions.md", "docs/glossary.md", "docs/HANDOFF.md",
    "docs/log/README.md", "docs/log/TEMPLATE.md",
    "docs/decisions/TEMPLATE.md", "docs/decisions/INDEX.md",
    "scripts/check_docs.py", "scripts/build_status.py", "scripts/new_log.py",
    "scripts/session_start.py", "scripts/scan_secrets.py",
]
LOG_FIELDS = ["Date:", "Author:", "Tool and model:", "Plan IDs:"]
CORE_GLOBS = ["AGENTS.md", "README.md", "docs/00-START-HERE.md", "docs/RULES.md", "docs/PLAN.md", "docs/GATES.md",
              "docs/decisions/*.md", "agents/*.md"]
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def strip_code(text):
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-missing-prefix", default="")
    a = ap.parse_args()
    skip = tuple(p.strip() for p in a.allow_missing_prefix.split(",") if p.strip())
    errors, warnings = [], []

    def skipped(rel):
        return rel.startswith(skip) if skip else False

    for rel in REQUIRED:
        if not (ROOT / rel).exists() and not skipped(rel):
            errors.append(f"missing required file: {rel}")

    for f in log_files():
        text = f.read_text(encoding="utf-8")
        for field in LOG_FIELDS:
            if not re.search(rf"^{re.escape(field)}", text, re.M):
                errors.append(f"docs/log/{f.name}: missing header field '{field}'")

    idx = ROOT / "docs/decisions/INDEX.md"
    if idx.exists():
        t = idx.read_text(encoding="utf-8")
        for f in adr_files():
            if f.name not in t:
                errors.append(f"docs/decisions/INDEX.md does not list {f.name}")

    _, perrs = parse_plan()
    errors += perrs

    core = set()
    for g in CORE_GLOBS:
        core.update(ROOT.glob(g))
    for f in sorted(ROOT.rglob("*.md")):
        rel = f.relative_to(ROOT).as_posix()
        if set(f.relative_to(ROOT).parts) & {".git", "node_modules", ".venv"}:
            continue
        is_core = f in core
        text = strip_code(f.read_text(encoding="utf-8"))
        for target in LINK_RE.findall(text):
            if re.match(r"^(https?:|mailto:|#)", target):
                continue
            path = target.split("#")[0]
            if not path:
                continue
            dest = (f.parent / path).resolve()
            if dest.exists():
                continue
            try:
                drel = dest.relative_to(ROOT).as_posix()
            except ValueError:
                drel = path
            if skip and (drel.startswith(skip) or skipped(rel)):
                continue
            msg = f"{rel}: broken link -> {target}"
            (errors if is_core else warnings).append(msg)

    status = ROOT / "docs/STATUS.md"
    if status.exists() and status.read_text(encoding="utf-8") != build_status.render():
        errors.append("docs/STATUS.md is stale: run python3 scripts/build_status.py")

    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    print(f"docs check: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
