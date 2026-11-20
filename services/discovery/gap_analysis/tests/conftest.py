import sys
from pathlib import Path

DISC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(DISC))                       # import gap_analysis
sys.path.insert(0, str(DISC.parent / "blueprint"))  # import registry, validator
