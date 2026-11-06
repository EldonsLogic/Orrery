#!/usr/bin/env python3
"""Create docs/log/YYYY-MM-DD-<author>-<tool>-<slug>.md from TEMPLATE.md."""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--author", required=True, help="eldon or partner")
    ap.add_argument("--tool", required=True, help="e.g. claude-code, codex, antigravity")
    ap.add_argument("--slug", required=True, help="short topic, e.g. adr-tenancy")
    ap.add_argument("--ids", default="-", help="comma list of plan IDs, e.g. GOV-001,SEC-002")
    ap.add_argument("--model", default="", help="model name, e.g. opus-5")
    a = ap.parse_args()
    today = date.today().isoformat()
    name = f"{today}-{slugify(a.author)}-{slugify(a.tool)}-{slugify(a.slug)}.md"
    path = ROOT / "docs" / "log" / name
    if path.exists():
        print(f"exists: {path}", file=sys.stderr)
        return 1
    text = (ROOT / "docs" / "log" / "TEMPLATE.md").read_text(encoding="utf-8")
    tool = a.tool + (f" / {a.model}" if a.model else "")
    text = (text.replace("<slug>", a.slug).replace("YYYY-MM-DD", today)
            .replace("Author: <eldon|partner>", f"Author: {a.author}")
            .replace("Tool and model: <tool / model>", f"Tool and model: {tool}")
            .replace("Plan IDs: <comma list or ->", f"Plan IDs: {a.ids}"))
    path.write_text(text, encoding="utf-8")
    print(f"created docs/log/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
