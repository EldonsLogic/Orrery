"""compile_blueprint: Blueprint + registry + engine mapping -> compiled artifact (initial build) or refusal.

Pure and deterministic: no clock, no randomness, no I/O beyond reading the contract schemas, inputs never modified.
Order of gates (each fails closed): plain-JSON input, Blueprint validator, environment and registry, component
resolution, engine mapping, step compilation, artifact checks.
"""
from __future__ import annotations

import copy
from typing import Any

from . import artifact as art
from ._deps import ValidationContext, blueprint_hash, bpdiff, validate
from .components import resolve_components
from .mapping import check_mapping
from .result import CompileResult, Issue, Refused, sort_issues
from .steps import ledger_or_tax_subjects, post_conditions, risk, skeleton, steps_from_ops


def compile_blueprint(blueprint: Any, registry: Any, engine_mapping: Any, *, environment: str) -> CompileResult:
    """Compile one Blueprint revision into the initial-build artifact for an empty site of `environment`
    ("sandbox" or "production"). Returns CompileResult(ok, artifact | errors); never raises for bad input."""
    try:
        return CompileResult(artifact=_compile(copy.deepcopy(blueprint), registry, copy.deepcopy(engine_mapping),
                                               environment))
    except Refused as r:
        return CompileResult(errors=sort_issues(r.issues))
    except Exception as exc:  # a bug or an input shape no gate anticipated: refuse, never emit
        return CompileResult(errors=[Issue("CMP-INTERNAL-001", "", f"compiler could not run ({type(exc).__name__})")])


def _refuse_if(issues: list[Issue]) -> None:
    if issues:
        raise Refused(issues)


def _compile(bp: Any, registry: Any, mapping: Any, environment: str) -> dict:
    try:
        bpdiff.model.validate_input(bp)
    except bpdiff.BpdError as e:
        raise Refused([Issue("CMP-INPUT-001", "", f"Blueprint is not plain JSON ({e.code})")])
    if not hasattr(registry, "is_eligible") or not hasattr(registry, "as_validation_context_registry"):
        raise Refused([Issue("CMP-REG-002", "", "registry must be a component Registry")])

    report = validate(bp, ValidationContext(registry=registry.as_validation_context_registry()))
    _refuse_if([Issue(i.code, i.path, i.message) for i in report.errors])
    meta = bp["meta"]
    target = meta.get("engineTarget") or {}
    if not isinstance(target.get("versionSet"), str):
        raise Refused([Issue("CMP-BP-001", "/meta/engineTarget/versionSet",
                             "an engine version set is required to compile")])

    resolved, issues = resolve_components(bp, registry, environment)
    if not any(i.code == "CMP-ENV-001" for i in issues):
        issues += check_mapping(mapping, bp, resolved, environment)
    _refuse_if(issues)

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
