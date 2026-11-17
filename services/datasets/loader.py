"""Load the committed dataset, verifying each file against manifest.json (for the dev bench and evals)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"


def load_manifest(data_dir: Path = DATA_DIR) -> dict:
    return json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))


def load_market(market: str, data_dir: Path = DATA_DIR) -> dict:
    """market: SA, AE, EG or QA. Raises ValueError when the file does not match the manifest hash."""
    for entry in load_manifest(data_dir)["files"]:
        if entry["market"] == market:
            raw = (data_dir / entry["path"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                raise ValueError(f"{entry['path']} does not match manifest.json; regenerate with python3 -m services.datasets")
            return json.loads(raw.decode("utf-8"))
    raise KeyError(market)


def load_all(data_dir: Path = DATA_DIR) -> dict:
    return {e["market"]: load_market(e["market"], data_dir) for e in load_manifest(data_dir)["files"]}
