"""CLI. From services/discovery (or with PYTHONPATH=services/discovery):

    python3 -m prevalidate <dataset.json> [--config <config.json>]

Prints the report as JSON. Exit 0 when nothing is quarantined, 1 when rows are quarantined,
2 on a refusal (coded error on stderr).
"""
from __future__ import annotations

import argparse
import json
import sys

from .errors import PrevalidationError
from .report import prevalidate


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m prevalidate")
    ap.add_argument("dataset")
    ap.add_argument("--config")
    a = ap.parse_args(argv)
    try:
        with open(a.dataset, encoding="utf-8") as fh:
            ds = json.load(fh)
        cfg = None
        if a.config:
            with open(a.config, encoding="utf-8") as fh:
                cfg = json.load(fh)
        rep = prevalidate(ds, cfg)
    except PrevalidationError as e:
        print(str(e), file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print("PRE-E01 pre.err.dataset_shape (unreadable input)", file=sys.stderr)
        return 2
    json.dump(rep.to_dict(), sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    print()
    return 1 if rep.quarantine else 0


if __name__ == "__main__":
    raise SystemExit(main())
