import sys
from pathlib import Path

DISC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(DISC))                       # import template_flow
sys.path.insert(0, str(DISC / "templates"))         # import instantiate
sys.path.insert(0, str(DISC.parent / "blueprint"))  # import validator
