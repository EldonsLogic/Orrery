"""Build state machine, draft to live, with the human gates (BPL-020, Tier 3). See machine.py."""
from .canon import content_digest
from .errors import CODES, BuildStateError
from .ledger import SignOffLedger
from .machine import (AUTHOR, CONFIRMATIONS, CUTOVER_CHECKS, REASONS, STATES, BuildStateMachine, idempotency_key)
from .ports import OWNER, REVIEWER, RUNNER, Principal
from .sealed import SealedLog

import json as _json
from pathlib import Path as _Path

_LABELS = _json.loads((_Path(__file__).with_name("labels.json")).read_text(encoding="utf-8"))


def label(key: str, lang: str) -> str:
    return _LABELS[lang][key]


def label_keys() -> set:
    """Every key the screens use; tests check both languages carry all of them."""
    keys = {"bs.title", "bs.stale_notice", "bs.gate_notice", "bs.pending.applying", "bs.pending.unknown", "bs.pending.sandbox",
            "bs.pending.live"}
    keys |= {f"bs.state.{s}" for s in STATES} | {f"bs.reason.{r}" for r in REASONS} | {f"bs.confirm.{c}" for c in CONFIRMATIONS}
    keys |= {f"bs.check.{c}" for c in CUTOVER_CHECKS} | {f"bs.error.{c}" for c in CODES}
    return keys


__all__ = ["AUTHOR", "BuildStateError", "BuildStateMachine", "CODES", "CONFIRMATIONS", "CUTOVER_CHECKS", "OWNER", "Principal",
           "REASONS", "REVIEWER", "RUNNER", "STATES", "SealedLog", "SignOffLedger", "content_digest", "idempotency_key", "label", "label_keys"]
