"""compile_blueprint: Blueprint + registry + engine mapping -> compiled artifact (initial build, or base to target with
an embedded inverse when a base revision is given, BPL-039) or refusal.

Pure and deterministic: no clock, no randomness, no I/O beyond reading the contract schemas, inputs never modified.
Order of gates (each fails closed): plain-JSON input, Blueprint validator, environment and registry, component
resolution, engine mapping, step compilation, artifact checks.
"""
from __future__ import annotations

import copy
import hashlib
from typing import Any

from . import artifact as art
from ._deps import ValidationContext, blueprint_hash, bpdiff, canonical, validate
from .components import resolve_components
from .incremental import ledger_or_tax, steps_from_diff
from .mapping import check_mapping
from .result import CompileResult, Issue, Refused, sort_issues
from .steps import ledger_or_tax_subjects, post_conditions, risk, skeleton, steps_from_ops


def compile_blueprint(blueprint: Any, registry: Any, engine_mapping: Any, *, environment: str,
                      base: Any = None) -> CompileResult:
    """Compile one Blueprint revision for `environment` ("sandbox" or "production"). With no `base`: the initial-build
    artifact for an empty site. With a `base` revision: the incremental artifact from base to `blueprint`, carrying
    its inverse (BPL-039). Returns CompileResult(ok, artifact | errors); never raises for bad input."""
    try:
        if base is not None:
            return CompileResult(artifact=_compile_change(copy.deepcopy(base), copy.deepcopy(blueprint), registry,
                                                          copy.deepcopy(engine_mapping), environment))
        return CompileResult(artifact=_compile(copy.deepcopy(blueprint), registry, copy.deepcopy(engine_mapping),
                                               environment))
    except Refused as r:
        return CompileResult(errors=sort_issues(r.issues))
    except Exception as exc:  # a bug or an input shape no gate anticipated: refuse, never emit
        return CompileResult(errors=[Issue("CMP-INTERNAL-001", "", f"compiler could not run ({type(exc).__name__})")])


def _refuse_if(issues: list[Issue]) -> None:
    if issues:
        raise Refused(issues)


def _gates(bp: Any, registry: Any, mapping: Any, environment: str) -> dict:
    """Every gate before step compilation; returns the resolved components."""
    try:
        bpdiff.model.validate_input(bp)
    except bpdiff.BpdError as e:
        raise Refused([Issue("CMP-INPUT-001", "", f"Blueprint is not plain JSON ({e.code})")])
    if not hasattr(registry, "is_eligible") or not hasattr(registry, "as_validation_context_registry"):
        raise Refused([Issue("CMP-REG-002", "", "registry must be a component Registry")])

    report = validate(bp, ValidationContext(registry=registry.as_validation_context_registry()))
    _refuse_if([Issue(i.code, i.path, i.message) for i in report.errors])
    target = bp["meta"].get("engineTarget") or {}
    if not isinstance(target.get("versionSet"), str):
        raise Refused([Issue("CMP-BP-001", "/meta/engineTarget/versionSet",
                             "an engine version set is required to compile")])

    resolved, issues = resolve_components(bp, registry, environment)
    if not any(i.code == "CMP-ENV-001" for i in issues):
        issues += check_mapping(mapping, bp, resolved, environment)
    _refuse_if(issues)
    return resolved


def _compile(bp: Any, registry: Any, mapping: Any, environment: str) -> dict:
    resolved = _gates(bp, registry, mapping, environment)
    meta, target = bp["meta"], bp["meta"]["engineTarget"]
    d = bpdiff.diff(skeleton(bp), bp)
    steps, skipped, issues = steps_from_ops(d["ops"])
    _refuse_if(issues)
    artifact = art.assemble(
        blueprint_ref={"id": meta["id"], "base": None, "diffHash": None,
                       "target": {"hash": blueprint_hash(bp), "revision": meta["revision"]}},
        engine_target={"adapter": target["adapter"], "versionSet": target["versionSet"]},
        components=[{"id": cid, "version": resolved[cid]["version"]} for cid in sorted(resolved)],
        steps=steps, skipped=skipped, post_conditions=post_conditions(steps, bp),
        risk=risk(d["risk"], steps, ledger_or_tax_subjects(steps, resolved)))
    _refuse_if(art.check(artifact))
    return artifact


def _ref(bp: dict) -> dict:
    return {"hash": blueprint_hash(bp), "revision": bp["meta"]["revision"]}


def _side(d: dict, frm: dict, to: dict, resolved: dict, both: dict, inverse: dict | None) -> dict:
    """One artifact of an incremental compile: forward (d = diff(base, target)) or its inverse (d = invert(diff))."""
    steps, skipped, issues = steps_from_diff(d, frm, to, restores=inverse is None)
    _refuse_if(issues)
    meta, target = to["meta"], to["meta"]["engineTarget"]
    artifact = art.assemble(
        blueprint_ref={"id": meta["id"], "base": _ref(frm), "target": _ref(to),
                       "diffHash": "sha256:" + hashlib.sha256(canonical(d)).hexdigest()},
        engine_target={"adapter": target["adapter"], "versionSet": target["versionSet"]},
        components=[{"id": cid, "version": resolved[cid]["version"]} for cid in sorted(resolved)],
        steps=steps, skipped=skipped, post_conditions=post_conditions(steps, to),
        risk=risk(d["risk"], steps, ledger_or_tax(steps, both, frm, to)),
        kind="inverse" if inverse is None else "forward", inverse=inverse)
    _refuse_if(art.check(artifact))
    return artifact


def _compile_change(base: Any, bp: Any, registry: Any, mapping: Any, environment: str) -> dict:
    """Incremental compile (BPL-039): forward from diff(base, target), inverse from invert(diff) (contract 9.6)."""
    try:
        base_resolved = _gates(base, registry, mapping, environment)
    except Refused as r:
        raise Refused([Issue(i.code, i.path, "base revision: " + i.message) for i in r.issues])
    resolved = _gates(bp, registry, mapping, environment)
    bm, tm = base["meta"], bp["meta"]
    if bm["id"] != tm["id"]:
        raise Refused([Issue("CMP-INC-001", "/meta/id", "base and target are different Blueprints")])
    if bm["engineTarget"] != tm["engineTarget"]:
        raise Refused([Issue("CMP-INC-002", "/meta/engineTarget",
                             "an engine target change is not an incremental compile")])
    if tm["revision"] < bm["revision"] or (tm["revision"] == bm["revision"] and _ref(base) != _ref(bp)):
        raise Refused([Issue("CMP-INC-003", "/meta/revision", "target revision must follow the base revision")])
    d = bpdiff.diff(base, bp)
    both = {**base_resolved, **resolved}
    inverse = _side(bpdiff.invert(d), bp, base, base_resolved, both, None)
    return _side(d, base, bp, resolved, both, inverse)
