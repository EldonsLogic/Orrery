import sys
from pathlib import Path

BLUEPRINT = Path(__file__).resolve().parents[2]
# `import bpdiff` (services/blueprint/diff), `import validator` (services/blueprint) and
# `import instantiate` (services/discovery/templates).
sys.path.insert(0, str(BLUEPRINT / "diff"))
sys.path.insert(0, str(BLUEPRINT))
sys.path.insert(0, str(BLUEPRINT.parent / "discovery" / "templates"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
