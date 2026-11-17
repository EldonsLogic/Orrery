"""Helpers for the compiler snapshot tests (QA-004): the case table, snapshot rendering, compare-or-update.

Inputs are the fictional BPL-005 fixture, its draft golden-path engine mapping and synthetic edits of them (the repo
holds one Blueprint fixture and no ready-made invalid ones, so each invalid case is a small named edit written here).
A snapshot is the stable form of the result: valid cases hold the whole artifact plus its plan view, refusal cases
hold only the stable (code, path) pairs, never the free-text message.

Update switch: environment variable UPDATE_SNAPSHOTS=1 (exactly "1") rewrites snapshot files; anything else never
writes. A missing snapshot is a failure, never created silently, unless the switch is on.
"""
from __future__ import annotations

import copy
import difflib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BLUEPRINT = HERE.parents[1]
# Same import roots the compiler tests use; explicit so this folder works without any conftest.
for _p in (BLUEPRINT / "diff", BLUEPRINT, BLUEPRINT / "tests" / "compiler"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import cmp_helpers as H  # noqa: E402
from bpdiff.model import node_at  # noqa: E402
from compiler import compile_blueprint, plan_view, to_bytes  # noqa: E402

SNAPSHOT_DIR = HERE / "snapshots"
UPDATE_ENV = "UPDATE_SNAPSHOTS"
UPDATE_COMMAND = f"{UPDATE_ENV}=1 python -m pytest services/blueprint/tests/compiler_snapshots"
MAX_TOTAL_BYTES = 400 * 1024
FIXTURE_DIR = H.FIXTURE.parent
FIXTURE_NAME = H.FIXTURE.name  # trading-distribution.blueprint.json


def update_enabled() -> bool:
    return os.environ.get(UPDATE_ENV) == "1"


# ------------------------------------------------------------------ cases
def _edit_manifest(cid, fn):
    out = []
    for m in H.manifests():
        if m["id"] == cid:
            m = copy.deepcopy(m)
            fn(m)
        out.append(m)
    return H.registry(out)


def _inputs(bp=None, reg=None, mp=None, env="sandbox"):
    return {"bp": H.blueprint() if bp is None else bp, "reg": H.registry() if reg is None else reg,
            "mp": H.mapping() if mp is None else mp, "env": env}


def _bp_edit(fn):
    def build():
        bp = H.blueprint()
        fn(bp)
        return _inputs(bp=bp)
    return build


def _mp_edit(fn):
    def build():
        mp = H.mapping()
        fn(mp)
        return _inputs(mp=mp)
    return build


def _production(fn=None):
    def build():
        bp, reg, mp = H.production_inputs()
        if fn:
            bp, reg, mp = fn(bp, reg, mp)
        return _inputs(bp, reg, mp, "production")
    return build


def _certified_except(cid):
    def fn(bp, reg, mp):
        return bp, H.registry([m if m["id"] == cid else H.certify(m) for m in H.manifests()]), mp
    return fn


def _set(d, key, value):
    d[key] = value


def _cycle(m):
    m["requires"] = [{"component": "core.sales_order", "versionRange": "^0.1.0"}]


def _broken_manifest():
    broken = copy.deepcopy(H.manifests()[0])
    broken["id"], broken["licence"] = "zz.broken", {"spdx": "NOASSERTION"}
    return _inputs(reg=H.registry(H.manifests() + [broken]))


def _nan_blueprint(bp):
    bp["meta"]["revision"] = float("nan")


def _del_version_set(bp):
    del bp["meta"]["engineTarget"]["versionSet"]


def _ledger_effect(mp):
    next(e for e in mp["entities"] if e["blueprintEntity"] == "customer")["ledgerEffect"] = "gl"


def _precision(mp):
    next(f for e in mp["entities"] for f in e["fields"] if "computed" in f)["computed"]["rounding"]["precision"] = 3


# name -> builder returning compile inputs. Valid cases first, then one refusal per stable failure family.
VALID_CASES = {
    "trading-distribution.sandbox": lambda: _inputs(),
}
REFUSAL_CASES = {
    "bp-schema-invalid-revision": _bp_edit(lambda bp: bp["meta"].__setitem__("revision", "one")),
    "bp-dangling-workflow-reference": _bp_edit(lambda bp: bp["entities"][0].__setitem__("workflow", "no_such_flow")),
    "bp-not-an-object": lambda: _inputs(bp=["not", "a", "blueprint"]),
    "bp-non-json-value": _bp_edit(_nan_blueprint),
    "bp-missing-engine-version-set": _bp_edit(_del_version_set),
    "bp-engine-name-in-tenant-text": _bp_edit(lambda bp: bp["entities"][0]["labels"].__setitem__("en", "Customer (ERPNext)")),
    "bp-no-version-in-range": _bp_edit(lambda bp: bp["components"][0].__setitem__("versionRange", "^9.0.0")),
    "env-unknown": lambda: _inputs(env="staging"),
    "env-fixture-as-is-for-production": lambda: _inputs(env="production"),
    "reg-missing-component": lambda: _inputs(reg=H.registry([m for m in H.manifests() if m["id"] != "core.customer"])),
    "reg-draft-component-in-sandbox": lambda: _inputs(reg=_edit_manifest("core.customer", lambda m: _set(m, "certification", {"level": "draft"}))),
    "reg-dependency-cycle": lambda: _inputs(reg=_edit_manifest("core.customer", _cycle)),
    "reg-admission-error": _broken_manifest,
    "reg-wrong-type": lambda: _inputs(reg={"core.customer": []}),
    "prod-tested-component": _production(_certified_except("core.customer")),
    "prod-ledger-component-below-level": _production(_certified_except("stock.ledger")),
    "map-not-an-object": lambda: _inputs(mp=["not", "a", "mapping"]),
    "map-unknown-top-level-key": _mp_edit(lambda mp: _set(mp, "rates", {"vat": 15})),
    "map-unknown-nested-key": _mp_edit(lambda mp: _set(mp["entities"][0]["fields"][0], "taxRate", 15)),
    "map-entity-not-in-blueprint": _mp_edit(lambda mp: _set(mp["entities"][0], "blueprintEntity", "no_such_entity")),
    "map-field-type-mismatch": _mp_edit(lambda mp: _set(mp["entities"][0]["fields"][0], "blueprintType", "integer")),
    "map-other-adapter": _mp_edit(lambda mp: _set(mp["engine"], "adapter", "other_engine")),
    "map-other-version-set": _mp_edit(lambda mp: _set(mp["engine"], "versionSet", "set-other")),
    "map-other-blueprint-contract": _mp_edit(lambda mp: _set(mp["blueprintRef"], "contract", "9.9.9")),
    "map-grant-beyond-role": _mp_edit(lambda mp: mp["roles"][1]["grants"][1]["actions"].append("delete")),
    "map-ledger-effect-without-ledger-component": _mp_edit(_ledger_effect),
    "map-precision-mismatch": _mp_edit(_precision),
}
SNAPSHOT_NAMES = {f"valid--{n}.json" for n in VALID_CASES} | {f"refusal--{n}.json" for n in REFUSAL_CASES}


def snapshot_file(kind: str, name: str) -> Path:
    return SNAPSHOT_DIR / f"{kind}--{name}.json"


def run_case(builder) -> object:
    i = builder()
    return compile_blueprint(i["bp"], i["reg"], i["mp"], environment=i["env"]), i


# ------------------------------------------------------------------ rendering
def render_valid(result) -> bytes:
    assert result.ok, [str(e) for e in result.errors]
    return to_bytes({"artifact": result.artifact, "planView": plan_view(result.artifact)})


def render_refusal(result, env: str) -> bytes:
    assert not result.ok and result.artifact is None, "expected a refusal"
    errors = [{"code": e.code, "path": e.path} for e in result.errors]
    return to_bytes({"environment": env, "errors": errors})


def render_case(kind: str, builder) -> bytes:
    result, i = run_case(builder)
    return render_valid(result) if kind == "valid" else render_refusal(result, i["env"])


# ------------------------------------------------------------------ golden cross-check
def resolve_golden(value, bp):
    """Expand the golden file's "$fromBlueprint" pointers and "$blueprintHash" (see tests/compiler/test_cmp_golden.py)."""
    import hashlib
    if isinstance(value, dict):
        if set(value) == {"$fromBlueprint"}:
            return copy.deepcopy(node_at(bp, value["$fromBlueprint"].split("/")[1:]))
        return {k: resolve_golden(v, bp) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_golden(v, bp) for v in value]
    if value == "$blueprintHash":
        return "sha256:" + hashlib.sha256(H.canonical(bp)).hexdigest()
    return value


# ------------------------------------------------------------------ compare or update
def diff_message(expected: str, actual: str, name: str, context: int = 3, max_lines: int = 60) -> str:
    """Readable unified diff of the first differing region only."""
    lines = list(difflib.unified_diff(expected.splitlines(), actual.splitlines(), f"snapshot/{name}", f"actual/{name}",
                                      lineterm="", n=context))
    out, hunks = [], 0
    for line in lines:
        if line.startswith("@@"):
            hunks += 1
            if hunks > 1:
                out.append("... (further differences not shown)")
                break
        out.append(line)
    if len(out) > max_lines:
        out = out[:max_lines] + ["... (truncated)"]
    return "\n".join(out)


def _shown(path: Path) -> str:
    return f"{path.parent.name}/{path.name}"


def assert_matches_snapshot(path: Path, actual: bytes) -> None:
    """Fail on a missing or different snapshot, unless UPDATE_SNAPSHOTS=1 (then write it). Never writes otherwise."""
    if update_enabled():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != actual:
            path.write_bytes(actual)
        return
    if not path.exists():
        raise AssertionError(f"snapshot missing: {_shown(path)}\nTo create it after reviewing the output, run:\n  {UPDATE_COMMAND}")
    expected = path.read_bytes()
    if expected != actual:
        raise AssertionError(
            f"snapshot differs: {_shown(path)}\n"
            f"{diff_message(expected.decode('utf-8'), actual.decode('utf-8'), path.name)}\n"
            f"If the change is intended, review it and update with:\n  {UPDATE_COMMAND}")
