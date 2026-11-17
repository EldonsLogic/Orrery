"""CLI. From the repo root:

    python3 -m services.datasets [--seed N] [--out DIR]     write the dataset (default DIR: services/datasets/data)
    python3 -m services.datasets --check [--seed N]         exit 1 if the committed files differ from a fresh run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import DEFAULT_SEED
from .generator import generate


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m services.datasets")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "data")
    ap.add_argument("--check", action="store_true", help="compare with the files in --out instead of writing")
    args = ap.parse_args(argv)
    files = generate(args.seed)
    if args.check:
        bad = [n for n, b in files.items() if not (args.out / n).is_file() or (args.out / n).read_bytes() != b]
        for n in bad:
            print(f"DIFFERS {n}")
        print("dataset check: " + ("FAILED" if bad else "ok"))
        return 1 if bad else 0
    args.out.mkdir(parents=True, exist_ok=True)
    for n, b in files.items():
        (args.out / n).write_bytes(b)
        print(f"wrote {n} ({len(b)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
