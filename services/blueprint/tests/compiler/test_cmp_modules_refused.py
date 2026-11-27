"""The compiler has no rule for `modules` yet (ADR-0079; compiler support is BPL-061, G2): an added or changed
`modules` block must be refused with CMP-ART-001, never compiled or skipped. Pins today's fail-closed behaviour
(#395 review M3). Synthetic data only."""
import copy
import json

import cmp_helpers as H
from bpdiff import diff
from compiler.incremental import steps_from_diff
from compiler.steps import skeleton, steps_from_ops

CRM = json.loads((H.REPO / "contracts" / "examples" / "blueprint-modules-minimal.json").read_text(
    encoding="utf-8"))["modules"]


def _with_modules(bp):
    t = copy.deepcopy(bp)
    t["meta"]["revision"] = bp["meta"]["revision"] + 1
    t["modules"] = copy.deepcopy(CRM)
    return t


def _module_issues(issues):
    return [(i.code, i.path) for i in issues if i.path.startswith("/modules")]


def test_initial_build_with_modules_is_refused():
    target = _with_modules(H.blueprint())
    ops = [o for o in diff(skeleton(target), target)["ops"] if o["path"][:1] == ["modules"]]
    steps, skipped, issues = steps_from_ops(ops)
    assert ops and steps == [] and skipped == []
    assert _module_issues(issues) == [("CMP-ART-001", "/modules")]


def test_adding_modules_to_a_live_blueprint_is_refused():
    base = H.blueprint()
    target = _with_modules(base)
    steps, skipped, issues = steps_from_diff(diff(base, target), base, target)
    assert not [s for s in steps if any(p.startswith("/modules") for p in s["sourceOps"])]
    assert not [s for s in skipped if s["pointer"].startswith("/modules")]
    assert _module_issues(issues) == [("CMP-ART-001", "/modules")]


def test_changing_a_modules_block_is_refused():
    base = _with_modules(H.blueprint())
    target = copy.deepcopy(base)
    target["meta"]["revision"] += 1
    target["modules"]["crm"]["pipeline"]["stages"][0]["probabilityPercent"] = 20
    steps, skipped, issues = steps_from_diff(diff(base, target), base, target)
    assert not [s for s in steps if any(p.startswith("/modules") for p in s["sourceOps"])]
    assert _module_issues(issues) == [("CMP-ART-001", "/modules/crm/pipeline/stages/qualify/probabilityPercent")]


def test_full_compile_with_modules_is_refused():
    r = H.compile_fixture(bp=_with_modules(H.blueprint()))
    assert not r.ok and r.artifact is None
    assert [(i.code, i.path) for i in r.errors] == [("CMP-ART-001", "/modules")]
