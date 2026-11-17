import sys
from pathlib import Path

BLUEPRINT = Path(__file__).resolve().parents[2]
# `import compiler`, `import validator`, `import registry` (services/blueprint), `import bpdiff` (services/blueprint/diff)
# and `import cmp_helpers` (this folder).
sys.path.insert(0, str(BLUEPRINT / "diff"))
sys.path.insert(0, str(BLUEPRINT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
