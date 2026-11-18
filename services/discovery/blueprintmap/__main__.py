"""CLI. From services/discovery (or with PYTHONPATH=services/discovery):

    python3 -m blueprintmap <odoo-extract.json>

Reads the Odoo connector's raw extract (JSON). Prints {"report", "fragment"} as JSON. Exit 0 when
nothing needs a person, 1 when the report has needs_human or conflicts, 2 on a refusal.
"""
from __future__ import annotations

import argparse
import json
import sys

from .engine import map_records
from .errors import BlueprintMapError


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m blueprintmap")
    ap.add_argument("extract")
    a = ap.parse_args(argv)
    try:
        with open(a.extract, encoding="utf-8") as fh:
            res = map_records(json.load(fh))
    except BlueprintMapError as e:
        print(str(e), file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print("BMP-E01 bmp.err.input_shape (unreadable input)", file=sys.stderr)
        return 2
    json.dump(res, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    print()
    r = res["report"]
    return 1 if r["needs_human"] or r["conflicts"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
