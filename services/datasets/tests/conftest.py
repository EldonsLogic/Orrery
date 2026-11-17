import sys
from pathlib import Path

# Make `import services.datasets` work wherever pytest is started (services/ is a namespace package).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
