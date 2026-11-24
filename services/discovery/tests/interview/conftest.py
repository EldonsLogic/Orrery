import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))  # services/discovery, so `import interview` works
sys.path.insert(0, str(HERE))
