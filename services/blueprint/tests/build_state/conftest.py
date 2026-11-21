import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BP = HERE.parents[1]  # services/blueprint
sys.path.insert(0, str(BP))
sys.path.insert(0, str(BP / "tests" / "simulator"))
sys.path.insert(0, str(HERE))
