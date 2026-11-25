"""Assemble, seal and check the compiled artifact (contracts/compiled-artifact.schema.json 0.1.0, engine-adapter.md 9)."""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator

from ._deps import CONTRACTS, canonical
from .result import Issue, ptr

ARTIFACT_SCHEMA = "0.1.0"
COMPILER = {"name": "bpl-compiler", "version": "0.1.0"}
ALGORITHM = "sha256-canonical-json-v1"
MAX_BYTES = 1_048_576
MAX_STEPS = 500
MAX_POST_CONDITIONS = 1000
MAX_COMPONENTS = 200
MAX_PARAMS_DEPTH = 32
SECRET_KEY = re.compile(r"[Pp]assword|[Ss]ecret|[Aa]pi_?[Kk]ey|[Tt]oken|[Cc]redential")  # $defs.noSecretKeys
ENGINE_NAME = re.compile(r"(?i)frappe|erpnext")  # ADP-C-006 denylist, ADR-0016 (steps and checks only)


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads((CONTRACTS / "compiled-artifact.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def content_hash(artifact: dict) -> str:
    """9.1: sha256 over the canonical JSON of the artifact without artifactId and integrity."""
    body = {k: v for k, v in artifact.items() if k not in ("artifactId", "integrity")}
    return "sha256:" + hashlib.sha256(canonical(body)).hexdigest()


def seal(artifact: dict) -> dict:
    digest = content_hash(artifact)
    artifact["integrity"] = {"algorithm": ALGORITHM, "contentHash": digest, "signature": None}
    artifact["artifactId"] = "art_" + digest[len("sha256:"):len("sha256:") + 32]
    return artifact


def assemble(*, blueprint_ref: dict, engine_target: dict, components: list[dict], steps: list[dict],
             skipped: list[dict], post_conditions: list[dict], risk: dict, kind: str = "forward",
             inverse: dict | None = None) -> dict:
    """The sealed artifact. An embedded `inverse` must already be sealed: it is hashed as it stands (9.1)."""
    art = {"artifactSchema": ARTIFACT_SCHEMA, "artifactId": "", "kind": kind, "compiler": dict(COMPILER),
           "blueprint": blueprint_ref, "engineTarget": engine_target, "components": components, "steps": steps,
           "skippedOps": skipped, "postConditions": post_conditions, "risk": risk, "inverse": inverse, "integrity": {}}
    return seal(art)


def _depth(value: Any) -> int:
    if isinstance(value, dict):
        return 1 + max((_depth(v) for v in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_depth(v) for v in value), default=0)
    return 0


def _secret_keys(value: Any, path: str) -> list[str]:
    hits = []
    if isinstance(value, dict):
        for k, v in sorted(value.items()):
            if SECRET_KEY.search(k):
                hits.append(path + "/" + k)
            hits += _secret_keys(v, path + "/" + k)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            hits += _secret_keys(v, f"{path}/{i}")
    return hits


def check(artifact: dict) -> list[Issue]:
    """Schema plus the x-validator-rules this side can check. Any issue refuses the compile (fail closed)."""
    issues = [Issue("CMP-ART-004", ptr(*e.absolute_path), f"artifact schema: {e.validator} failed")
              for e in _validator().iter_errors(artifact)]
    size = len(canonical(artifact))
    for name, actual, allowed in (("bytes", size, MAX_BYTES), ("steps", len(artifact["steps"]), MAX_STEPS),
                                  ("postConditions", len(artifact["postConditions"]), MAX_POST_CONDITIONS),
                                  ("components", len(artifact["components"]), MAX_COMPONENTS)):
        if actual > allowed:
            issues.append(Issue("CMP-ART-003", "/" + name if name != "bytes" else "",
                                f"artifact {name} {actual} over the limit {allowed}"))
    for s in artifact["steps"]:
        where = ptr("steps", s["seq"] - 1, "params")
        for hit in _secret_keys(s["params"], where):
            issues.append(Issue("CMP-ART-002", hit, "secret-like key in step params"))
        if _depth(s["params"]) > MAX_PARAMS_DEPTH:
            issues.append(Issue("CMP-ART-003", where, f"params nesting deeper than {MAX_PARAMS_DEPTH}"))
    neutral = canonical({"steps": artifact["steps"], "postConditions": artifact["postConditions"]}).decode("utf-8")
    if ENGINE_NAME.search(neutral):
        issues.append(Issue("CMP-ART-005", "/steps", "an engine product name appears in steps or post-conditions"))
    if artifact["artifactId"] != "art_" + artifact["integrity"]["contentHash"][7:39] or \
            artifact["integrity"]["contentHash"] != content_hash(artifact):
        issues.append(Issue("CMP-ART-004", "/integrity", "content hash or artifact id does not match"))
    return issues


def to_bytes(value: Any) -> bytes:
    """The file form the CLI writes: sorted keys, two-space indent, UTF-8, trailing newline. Same input, same bytes."""
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
