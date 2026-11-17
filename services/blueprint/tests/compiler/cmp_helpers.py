"""Shared inputs for the compiler tests. All data is the fictional BPL-005 fixture, the draft golden-path mapping and
synthetic manifests derived from the fixture registry; nothing here is a real company or component."""
from __future__ import annotations

import copy
import glob
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from compiler import compile_blueprint
from registry import Registry

REPO = Path(__file__).resolve().parents[4]
FIXTURE = REPO / "services" / "blueprint" / "fixtures" / "trading-distribution.blueprint.json"
REGISTRY_DIR = REPO / "services" / "blueprint" / "fixtures" / "registry"
MAPPING = REPO / "contracts" / "examples" / "engine-mapping-golden-path.json"
EXPECTED = Path(__file__).resolve().parent / "fixtures" / "trading-distribution.expected-artifact.json"
ARTIFACT_SCHEMA = json.loads((REPO / "contracts" / "compiled-artifact.schema.json").read_text(encoding="utf-8"))
ARTIFACT_VALIDATOR = Draft202012Validator(ARTIFACT_SCHEMA)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def blueprint() -> dict:
    return load(FIXTURE)


def mapping() -> dict:
    return load(MAPPING)


def manifests() -> list[dict]:
    return [load(Path(f)) for f in sorted(glob.glob(str(REGISTRY_DIR / "*.json")))]


def registry(mans: list[dict] | None = None) -> Registry:
    return Registry.from_manifests(manifests() if mans is None else mans)


_DEFAULT = object()


def compile_fixture(bp=_DEFAULT, reg=_DEFAULT, mp=_DEFAULT, environment="sandbox"):
    return compile_blueprint(blueprint() if bp is _DEFAULT else bp, registry() if reg is _DEFAULT else reg,
                             mapping() if mp is _DEFAULT else mp, environment=environment)


def codes(result) -> set[str]:
    assert not result.ok and result.artifact is None and result.errors, "expected a refusal"
    return {i.code for i in result.errors}


def canonical(value) -> bytes:
    """Independent of the compiler: sorted keys, no spaces, UTF-8 (contract 5.8)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(value) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def certify(manifest: dict) -> dict:
    """A synthetic certified copy of a fixture manifest (schema 113-150 and admission REG-006 requirements)."""
    m = copy.deepcopy(manifest)
    m["certification"] = {"level": "certified", "reviewedBy": ["example-reviewer"], "certifiedAt": "2026-01-01T00:00:00Z",
                          "evidence": [{"kind": "ci_run", "ref": "example-ci-run"}],
                          "touchesLedgerOrTax": manifest["certification"].get("touchesLedgerOrTax", False)}
    return m


def production_inputs() -> tuple[dict, Registry, dict]:
    """Inputs a production compile accepts: certified manifests and a verified mapping pinned to the fixture's
    version set (both synthetic; the real mapping stays draft until the bench run)."""
    mp = mapping()
    mp["status"] = "verified"
    mp["engine"]["versionSet"] = blueprint()["meta"]["engineTarget"]["versionSet"]
    return blueprint(), registry([certify(m) for m in manifests()]), mp


def numbers(value, out=None) -> list:
    out = [] if out is None else out
    if isinstance(value, bool):
        return out
    if isinstance(value, (int, float)):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            numbers(v, out)
    elif isinstance(value, list):
        for v in value:
            numbers(v, out)
    return out
