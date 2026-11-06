"""Shared helpers for docs scripts (stdlib only)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUSES = ("todo", "doing", "done", "blocked")
GATES = ("G0", "G1", "G2", "G3", "G4", "G5")
OWNERS = ("eldon", "partner", "unassigned")
ID_RE = re.compile(r"^[A-Z]+(?:-[A-Z]+)*-\d{3}$")
COLUMNS = ["ID", "Item", "Part", "Gate", "Depends", "Owner", "Status"]


def parse_plan(path=None):
    """Return (rows, errors). Each row is a dict keyed by COLUMNS."""
    path = path or ROOT / "docs" / "PLAN.md"
    rows, errors = [], []
    if not path.exists():
        return rows, ["docs/PLAN.md is missing"]
    seen = set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or not ID_RE.match(cells[0]):
            continue
        if len(cells) != len(COLUMNS):
            errors.append(f"PLAN.md:{n}: expected {len(COLUMNS)} columns, got {len(cells)}")
            continue
        row = dict(zip(COLUMNS, cells))
        if row["ID"] in seen:
            errors.append(f"PLAN.md:{n}: duplicate ID {row['ID']}")
        seen.add(row["ID"])
        if row["Status"] not in STATUSES:
            errors.append(f"PLAN.md:{n}: {row['ID']} bad Status '{row['Status']}'")
        if row["Gate"] not in GATES:
            errors.append(f"PLAN.md:{n}: {row['ID']} bad Gate '{row['Gate']}'")
        if row["Owner"] not in OWNERS:
            errors.append(f"PLAN.md:{n}: {row['ID']} bad Owner '{row['Owner']}'")
        row["line"] = n
        rows.append(row)
    ids = {r["ID"] for r in rows}
    for r in rows:
        dep = r["Depends"]
        if dep in ("-", ""):
            continue
        for d in [x.strip() for x in dep.split(",")]:
            if d not in ids:
                errors.append(f"PLAN.md:{r['line']}: {r['ID']} depends on unknown ID '{d}'")
    return rows, errors


def current_gate():
    p = ROOT / "docs" / "GATES.md"
    if p.exists():
        m = re.search(r"^Current gate:\s*(G[0-5])", p.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1)
    return "UNKNOWN"


def log_files():
    d = ROOT / "docs" / "log"
    if not d.is_dir():
        return []
    return sorted(
        (f for f in d.glob("*.md") if f.name not in ("README.md", "TEMPLATE.md")),
        key=lambda f: f.name,
        reverse=True,
    )


def log_summary(path):
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^## Summary\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return ""
    for line in m.group(1).splitlines():
        if line.strip():
            return line.strip().lstrip("- ").strip()
    return ""


def adr_files():
    d = ROOT / "docs" / "decisions"
    return sorted(d.glob("ADR-*.md")) if d.is_dir() else []


def adr_status(path):
    m = re.search(r"^Status:\s*(.+)$", path.read_text(encoding="utf-8"), re.M)
    return m.group(1).strip() if m else "UNKNOWN"
