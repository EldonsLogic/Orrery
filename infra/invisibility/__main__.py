"""CLI entrypoint for python3 -m infra.invisibility."""
from __future__ import annotations

import sys
from .crawler import main

if __name__ == "__main__":
    sys.exit(main())
