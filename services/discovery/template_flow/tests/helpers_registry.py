import json
from pathlib import Path

REG = Path(__file__).resolve().parents[3] / "blueprint" / "fixtures" / "registry"


def load_registry_dir():
    out = {}
    for f in sorted(REG.glob("*.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        out.setdefault(m["id"], []).append(m)
    return out
