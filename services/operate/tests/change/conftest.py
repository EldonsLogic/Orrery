import sys
from pathlib import Path

OPERATE = Path(__file__).resolve().parents[2]
for p in (OPERATE, OPERATE.parent, OPERATE.parents[1] / "services/blueprint/events"):
    sys.path.insert(0, str(p))
