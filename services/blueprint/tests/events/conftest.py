import sys
from pathlib import Path

EVENTS = Path(__file__).resolve().parents[2] / "events"
# `import evstream` (services/blueprint/events) and the shared test helpers.
sys.path.insert(0, str(EVENTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
