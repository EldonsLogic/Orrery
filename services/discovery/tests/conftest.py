import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# `import validator` (services/blueprint) and `import instantiate` (services/discovery/templates).
sys.path.insert(0, str(ROOT.parents[0] / "blueprint"))
sys.path.insert(0, str(ROOT / "templates"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
