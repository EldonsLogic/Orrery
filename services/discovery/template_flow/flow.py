"""Template-first discovery flow (DSC-004).

Show the draft Blueprint made from the vertical template, take the owner's corrections as structured
edits, validate each batch against the Blueprint schema, keep a hash-chained correction history and
return a revised draft. The result is never a final Blueprint: build state stays `draft` and a person
still approves (DSC-009). No model call, no network, no file write. Owner text is data.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from . import pathing, values
from .errors import (BATCH_LIMIT, EDIT_NOOP, EDIT_SHAPE, HISTORY_CHAIN, HISTORY_LIMIT, PATH_NOT_EDITABLE, REPLAY,
                     SCHEMA, SEMANTIC, STALE, STATE, FlowError)
from .summary import build_summary, load_questions, load_registry

REPO = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO / "contracts" / "blueprint.schema.json"
MAX_BATCH = 50
MAX_HISTORY = 1000
EDIT_KEYS = {"id", "op", "pointer", "value", "baseHash"}
_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}\Z", re.ASCII)
ACTORS = ("owner", "team_reviewer")

Clock = Callable[[], str]
# Optional semantic validator port: draft dict -> iterable of error code strings (no warnings).
SemanticValidator = Callable[[dict], Iterable[str]]


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def _schema_errors(validator, bp: dict) -> set[tuple[str, str]]:
    return {("/" + "/".join(str(p) for p in e.absolute_path), e.validator) for e in validator.iter_errors(bp)}


@dataclass(frozen=True)
class Revision:
    """A revised draft. `final` is always False: a person approves it later."""
    blueprint: dict
    base_hash: str
    draft_hash: str
    revision: int
    entries: tuple
    final: bool = field(default=False, init=False)
    needs_human_approval: bool = field(default=True, init=False)


class TemplateFlow:
    def __init__(self, draft: dict, *, clock: Clock, actor: str = "owner", semantic: SemanticValidator | None = None,
                 schema: dict | None = None, registry: list[dict] | None = None, questions: list[dict] | None = None,
                 history: list[dict] | None = None):
        if not isinstance(draft, dict) or (draft.get("meta") or {}).get("buildState") != "draft":
            raise FlowError(STATE, "only a Blueprint in build state draft can be corrected")
        if actor not in ACTORS:
            raise FlowError(EDIT_SHAPE, "unknown actor")
        import jsonschema  # imported here so the module loads without it for read-only use
        self._bp = copy.deepcopy(draft)
        self._clock = clock
        self._actor = actor
        self._semantic = semantic
        sch = schema if schema is not None else json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self._validator = jsonschema.validators.validator_for(sch)(sch)
        self._registry = registry if registry is not None else load_registry()
        self._questions = questions if questions is not None else load_questions()
        self._history: list[dict] = []
        if history:
            self._restore(history)

    # ---- read side -------------------------------------------------------------------------
    @property
    def draft(self) -> dict:
        return copy.deepcopy(self._bp)

    @property
    def draft_hash(self) -> str:
        return digest(self._bp)

    @property
    def history(self) -> list[dict]:
        return copy.deepcopy(self._history)

    def summary(self) -> dict:
        return build_summary(self._bp, self._registry, self._questions, draft_hash=self.draft_hash)

    # ---- history ---------------------------------------------------------------------------
    @staticmethod
    def verify_history(history: list[dict]) -> None:
        prev = "0" * 64
        ids: set[str] = set()
        for i, e in enumerate(history, 1):
            body = {k: v for k, v in e.items() if k != "hash"}
            if e.get("seq") != i or e.get("prevHash") != prev or e.get("hash") != digest(body) or e.get("editId") in ids:
                raise FlowError(HISTORY_CHAIN, "correction history is not an unbroken chain")
            ids.add(e["editId"])
            prev = e["hash"]

    def _restore(self, history: list[dict]) -> None:
        if len(history) > MAX_HISTORY:
            raise FlowError(HISTORY_LIMIT, "history too long")
        self.verify_history(history)
        if history and history[-1].get("draftHash") != self.draft_hash:
            raise FlowError(HISTORY_CHAIN, "history does not end at this draft")
        self._history = copy.deepcopy(history)

    # ---- write side ------------------------------------------------------------------------
    def apply(self, edits: Any) -> Revision:
        """Apply a batch atomically: every edit passes or nothing changes."""
        if not isinstance(edits, (list, tuple)) or not edits or len(edits) > MAX_BATCH:
            raise FlowError(BATCH_LIMIT, "send 1 to %d corrections" % MAX_BATCH)
        if len(self._history) + len(edits) > MAX_HISTORY:
            raise FlowError(HISTORY_LIMIT, "history would be too long")
        used = {e["editId"] for e in self._history}
        batch_ids: set[str] = set()
        base_hash = self.draft_hash
        before_errors = _schema_errors(self._validator, self._bp)
        before_sem = set(self._semantic(self._bp)) if self._semantic else set()
        work = copy.deepcopy(self._bp)
        entries: list[dict] = []
        prev = self._history[-1]["hash"] if self._history else "0" * 64
        at = self._clock()
        revision = int(work["meta"]["revision"]) + 1
        for raw in edits:
            ed = self._check_shape(raw)
            if ed["id"] in used or ed["id"] in batch_ids:
                raise FlowError(REPLAY if ed["id"] in used else BATCH_LIMIT,
                                "correction id already used" if ed["id"] in used else "repeated correction id in one call")
            batch_ids.add(ed["id"])
            if "baseHash" in ed and ed["baseHash"] != base_hash:
                raise FlowError(STALE, "correction was written against another version of the draft")
            segs = pathing.parse_pointer(ed["pointer"])
            spec = next((f for f in self._registry if pathing.match(f["segs"], segs)), None)
            if spec is None:
                raise FlowError(PATH_NOT_EDITABLE, "this item cannot be corrected here", ed["pointer"])
            parent, leaf, exists, ancestors = pathing.resolve(work, segs, bool(spec.get("create")))
            new = values.normalise(ed["value"], spec)
            old = copy.deepcopy(parent.get(leaf)) if exists else None
            if exists and old == new and type(old) is type(new):
                raise FlowError(EDIT_NOOP, "value is unchanged", ed["pointer"])
            parent[leaf] = new
            self._mark(ancestors)
            body = {"seq": len(self._history) + len(entries) + 1, "editId": ed["id"], "op": "set",
                    "pointer": "/" + "/".join(segs), "before": old, "after": copy.deepcopy(new),
                    "actor": self._actor, "at": at, "revision": revision, "prevHash": prev}
            entries.append(body)
            prev = digest(body)
            body["hash"] = prev
        work["meta"]["revision"] = revision
        work["meta"]["updatedAt"] = at
        work["meta"]["buildState"] = "draft"
        new_errors = _schema_errors(self._validator, work) - before_errors
        if new_errors:
            raise FlowError(SCHEMA, "the corrections would make the draft invalid against the Blueprint schema")
        if self._semantic and set(self._semantic(work)) - before_sem:
            raise FlowError(SEMANTIC, "the corrections would break a Blueprint rule")
        final_hash = digest(work)
        # the last entry carries the draft hash so a restore can check where the chain ends
        entries[-1].pop("hash")
        entries[-1]["draftHash"] = final_hash
        entries[-1]["hash"] = digest(entries[-1])
        self._bp = work
        self._history.extend(entries)
        return Revision(copy.deepcopy(work), base_hash, final_hash, revision, tuple(copy.deepcopy(entries)))

    # ---- helpers ---------------------------------------------------------------------------
    @staticmethod
    def _check_shape(raw: Any) -> dict:
        if not isinstance(raw, dict) or set(raw) - EDIT_KEYS or not {"id", "pointer", "value"} <= set(raw):
            raise FlowError(EDIT_SHAPE, "a correction has exactly: id, pointer, value (and optionally op, baseHash)")
        if not isinstance(raw["id"], str) or not _ID.match(raw["id"]):
            raise FlowError(EDIT_SHAPE, "correction id must be 8 to 64 characters of A-Z a-z 0-9 _ -")
        if raw.get("op", "set") != "set":
            raise FlowError(EDIT_SHAPE, "only the set operation exists")
        if "baseHash" in raw and not (isinstance(raw["baseHash"], str) and re.fullmatch(r"[0-9a-f]{64}", raw["baseHash"])):
            raise FlowError(EDIT_SHAPE, "baseHash must be a SHA-256 hex string")
        return raw

    @staticmethod
    def _mark(ancestors: list) -> None:
        for a in reversed(ancestors[1:]):
            if isinstance(a, dict) and isinstance(a.get("provenance"), dict):
                a["provenance"]["humanEdited"] = True
                a["provenance"]["editedBy"] = "owner"
                return
