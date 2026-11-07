import sys
from pathlib import Path

# Make `import validator` work no matter where pytest is started.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
