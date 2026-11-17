"""Order independence, the plan view, the command line and the round trip through the fake adapter."""
import copy
import json
import random
import subprocess
import sys

import pytest

import cmp_helpers as H
from compiler import plan_view, to_bytes

COLLECTIONS = ("locations", "components", "entities", "workflows", "roles", "approvals", "reports", "integrations")
SEEDS = [1, 2, 3, 7, 42]


def _art(**kw):
    r = H.compile_fixture(**kw)
    assert r.ok, [str(i) for i in r.errors]
    return r.artifact


# ------------------------------------------------------------------ order independence
@pytest.mark.parametrize("seed", SEEDS)
def test_registry_manifest_order_does_not_change_the_artifact(seed):
    mans = H.manifests()
    random.Random(seed).shuffle(mans)
    assert to_bytes(_art(reg=H.registry(mans))) == to_bytes(_art())


@pytest.mark.parametrize("seed", SEEDS)
def test_mapping_list_order_does_not_change_the_artifact(seed):
    mp, rnd = H.mapping(), random.Random(seed)
    for key in ("entities", "roles", "operations", "unmapped"):
        rnd.shuffle(mp.get(key, []))
    for em in mp["entities"]:
        rnd.shuffle(em["fields"])
    assert to_bytes(_art(mp=mp)) == to_bytes(_art())


@pytest.mark.parametrize("seed", SEEDS)
def test_blueprint_collection_order_changes_only_the_revision_hash(seed):
    """Top-level collections are keyed by id (bpdiff), so their order is not significant to the steps, components,
    post-conditions, skipped ops or risk. The revision hash covers the exact document, so it (and with it the
    content hash and id) differs, as contract 9.2 requires."""
    bp, rnd = H.blueprint(), random.Random(seed)
    for key in COLLECTIONS:
        rnd.shuffle(bp[key])
    a, b = _art(bp=bp), _art()
    for key in ("steps", "components", "postConditions", "skippedOps", "risk", "engineTarget"):
        assert a[key] == b[key], key
    assert a["blueprint"]["target"]["hash"] == H.sha(bp) != b["blueprint"]["target"]["hash"]


def test_reordering_entity_fields_changes_the_order_check():
    """Field order is significant (bpdiff orderSignificant): it must show up in the artifact."""
    bp = H.blueprint()
    bp["entities"][0]["fields"].reverse()
    pc = next(p for p in _art(bp=bp)["postConditions"] if p["pointer"] == "/entities/customer/fields")
    assert pc["expected"] == [f["id"] for f in bp["entities"][0]["fields"]]


# ------------------------------------------------------------------ plan view
def test_plan_view_has_one_row_per_step_in_seq_order():
    a = _art()
    rows = plan_view(a)
    assert [r["seq"] for r in rows] == [s["seq"] for s in a["steps"]]
    assert [(r["kind"], r["pointer"]) for r in rows] == [(s["kind"], s["pointer"]) for s in a["steps"]]


def test_plan_view_dependencies_point_backwards_and_resolve():
    rows = plan_view(_art())
    for r in rows:
        assert all(d < r["seq"] for d in r["dependsOn"])
        assert all(f > r["seq"] for f in r["forwardRefs"])
        assert r["unresolved"] == []


def test_plan_view_entities_depend_on_their_components_and_roles_on_entities():
    a = _art()
    seq = {s["pointer"]: s["seq"] for s in a["steps"]}
    rows = {r["pointer"]: r for r in plan_view(a)}
    assert seq["/components/core.sales_order"] in rows["/entities/sales_order"]["dependsOn"]
    assert seq["/entities/customer"] in rows["/roles/sales_rep"]["dependsOn"]
    assert seq["/roles/general_manager"] in rows["/approvals/discount_approval"]["dependsOn"]


def test_plan_view_forward_references_are_only_the_known_contract_gaps():
    """Open question 5: same-phase references (entities, locations) and later-phase ones (entity -> workflow,
    workflow -> approval) are reported, never hidden."""
    a = _art()
    kind_of = {s["seq"]: s["kind"] for s in a["steps"]}
    allowed = {("entity.add", "entity.add"), ("entity.add", "workflow.upsert"),
               ("location.upsert", "location.upsert"), ("workflow.upsert", "approval.upsert")}
    pairs = {(r["kind"], kind_of[f]) for r in plan_view(a) for f in r["forwardRefs"]}
    assert pairs and pairs <= allowed


# ------------------------------------------------------------------ command line
def _cli(*args, module="compiler"):
    env_path = str(H.REPO / "services" / "blueprint")
    return subprocess.run([sys.executable, "-m", module, *map(str, args)], capture_output=True, text=True,
                          cwd=H.REPO, env={"PYTHONPATH": env_path, "PATH": ""})


def test_cli_writes_the_artifact_and_plan(tmp_path):
    out, plan = tmp_path / "a.json", tmp_path / "p.json"
    p = _cli(H.FIXTURE, "--mapping", H.MAPPING, "--registry", H.REGISTRY_DIR, "--environment", "sandbox",
             "--out", out, "--plan", plan)
    assert p.returncode == 0, p.stdout + p.stderr
    a = json.loads(out.read_text(encoding="utf-8"))
    assert out.read_bytes() == to_bytes(_art()) and p.stdout.startswith(a["artifactId"])
    assert json.loads(plan.read_text(encoding="utf-8")) == plan_view(a)


def test_cli_runs_as_services_blueprint_compiler(tmp_path):
    out = tmp_path / "a.json"
    p = subprocess.run([sys.executable, "-m", "services.blueprint.compiler", str(H.FIXTURE), "--mapping", str(H.MAPPING),
                        "--registry", str(H.REGISTRY_DIR), "--environment", "sandbox", "--out", str(out)],
                       capture_output=True, text=True, cwd=H.REPO, env={"PATH": ""})
    assert p.returncode == 0, p.stdout + p.stderr
    assert out.read_bytes() == to_bytes(_art())


def test_cli_refusal_exits_non_zero_prints_errors_and_writes_nothing(tmp_path):
    out = tmp_path / "a.json"
    p = _cli(H.FIXTURE, "--mapping", H.MAPPING, "--registry", H.REGISTRY_DIR, "--out", out)  # default: production
    assert p.returncode == 1 and not out.exists()
    assert "ERROR CMP-COMP-004" in p.stdout and "ERROR CMP-MAP-005" in p.stdout


def test_cli_unreadable_input_exits_non_zero(tmp_path):
    p = _cli(tmp_path / "missing.json", "--mapping", H.MAPPING, "--registry", H.REGISTRY_DIR, "--out", tmp_path / "a.json")
    assert p.returncode == 1 and "CMP-INPUT-002" in p.stdout


# ------------------------------------------------------------------ round trip through the fake adapter (BPL-025)
def _fake_inputs(adapter_id, drop_attachments):
    """Open question 4: the fixture targets adapter 'change_engine', the fake its own id; the copy is re-targeted.
    The fake declares 'attachment' an unsupported value type, so the full-apply variant drops those fields."""
    bp, mp = H.blueprint(), H.mapping()
    bp["meta"]["engineTarget"]["adapter"] = mp["engine"]["adapter"] = adapter_id
    if drop_attachments:
        for e in bp["entities"]:
            e["fields"] = [f for f in e["fields"] if f["type"] != "attachment"]
    mans = copy.deepcopy(H.manifests())
    for m in mans:
        m["engineCompatibility"]["adapter"] = adapter_id
    return _art(bp=bp, reg=H.registry(mans), mp=mp)


def _fake():
    harness = pytest.importorskip("adapter.harness", reason="fake adapter (BPL-025) is not on this branch")
    tk = pytest.importorskip("adapter.testkit")
    fake = pytest.importorskip("adapter.fake")
    return harness.FakeHarness(), tk, fake.ADAPTER_ID


def test_fake_adapter_accepts_the_compiled_trading_fixture():
    h, tk, adapter_id = _fake()
    a = _fake_inputs(adapter_id, drop_attachments=False)
    assert tk.provision(h, blueprint_id=a["blueprint"]["id"], target=a["engineTarget"], site_class="sandbox")["ok"]
    p = tk.plan(h, a)
    assert p["ok"], p
    assert len(p["result"]["steps"]) == len(a["steps"])
    blocked = {s.get("reasonCode") for s in p["result"]["steps"] if s["disposition"] in ("blocked", "unsupported")}
    assert blocked <= {"unsupported_value_type"}  # the fake's own capability list, not an artifact defect


def test_fake_adapter_applies_the_compiled_fixture_and_every_post_condition_passes():
    h, tk, adapter_id = _fake()
    a = _fake_inputs(adapter_id, drop_attachments=True)
    tk.provision(h, blueprint_id=a["blueprint"]["id"], target=a["engineTarget"], site_class="sandbox")
    preview = tk.plan(h, a, op="preview")
    assert preview["ok"] and preview["result"]["verdict"] != "rejected"
    out = tk.apply_artifact(h, a)
    assert out["ok"] and out["result"]["status"] == "applied", out
    assert all(s["status"] == "applied" for s in out["result"]["steps"])
    assert tk.export(h)["exportHash"] == preview["result"]["predictedExportHash"]
    assert tk.status(h)["applied"]["artifactId"] == a["artifactId"]
