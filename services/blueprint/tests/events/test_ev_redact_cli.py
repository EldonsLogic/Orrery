import copy
import json
import subprocess
import sys
from pathlib import Path

from evstream import RedactionPolicy, build_event, redact_for_model
from evstream.__main__ import main
from ev_helpers import ctx, make, stamp

EVENTS_DIR = Path(__file__).resolve().parents[2] / "events"


def personal():
    return build_event(
        ctx(kind="agent"), "memory.written", {"memory_id": "m_1", "customer_id": "c_9", "status": "ok",
                                              "amount": 150, "label": "Layla", "nested": {"owner_id": "u_1", "x": "y"}},
        data_class="personal", trace={"model_id": "m", "prompt_version": "p", "tool": None, "audit_id": None})


def test_redact_masks_values_keeps_ids():
    ev = personal()
    r = redact_for_model(ev)
    d = r["data"]
    assert d["memory_id"] == "m_1" and d["customer_id"] == "c_9" and d["status"] == "ok"
    assert d["amount"] == "[REDACTED]" and d["label"] == "[REDACTED]"
    assert d["nested"] == {"owner_id": "u_1", "x": "[REDACTED]"}
    assert d["_redaction"]["policy"] == "default-v1" and d["_redaction"]["masked"] == 3
    assert "Layla" not in json.dumps(r) and "150" not in json.dumps(r["data"])


def test_redact_does_not_mutate_original():
    ev = personal()
    snap = copy.deepcopy(ev)
    redact_for_model(ev)
    assert ev == snap


def test_redact_drop_mode():
    r = redact_for_model(personal(), RedactionPolicy(name="drop", mode="drop"))
    assert "amount" not in r["data"] and "label" not in r["data"] and r["data"]["customer_id"] == "c_9"
    assert r["data"]["nested"] == {"owner_id": "u_1"} and r["data"]["_redaction"]["dropped"] == 3


def test_redact_financial_and_long_id_values():
    ev = make("document.issued")
    ev["data"]["total"] = 1000
    ev["data"]["customer_id"] = "x" * 100
    r = redact_for_model(ev)
    assert r["data"]["total"] == "[REDACTED]" and r["data"]["customer_id"] == "[REDACTED]"
    assert r["data"]["einvoice_status"] == "cleared"


def test_redact_leaves_other_classes_and_copies():
    ev = make("<entity>.updated")
    r = redact_for_model(ev)
    assert r == ev and r is not ev and r["data"] is not ev["data"]
    r["data"]["changes"]["status"] = "x"
    assert ev["data"]["changes"]["status"] == "open"
    assert redact_for_model("junk") == "junk"


def test_redact_policy_classes_configurable():
    p = RedactionPolicy(classes=frozenset({"business"}))
    ev = make("<entity>.updated")
    ev["data"]["changes"]["total"] = 5
    assert redact_for_model(ev, p)["data"]["changes"]["total"] == "[REDACTED]"


# ---- CLI
def run(*args):
    return subprocess.run([sys.executable, "-m", "evstream", *args], cwd=EVENTS_DIR, capture_output=True, text=True,
                          env={"PYTHONPATH": str(EVENTS_DIR), "PATH": ""})


def test_cli_types_lists_registry():
    out = run("types")
    assert out.returncode == 0
    assert "<entity>.created" in out.stdout and "meter.ai_usage" in out.stdout


def test_cli_validate_json_and_jsonl(tmp_path):
    good = [stamp(make("<entity>.created"), 1), stamp(make("<entity>.created"), 2)]
    one = tmp_path / "one.json"
    one.write_text(json.dumps(good[0]))
    many = tmp_path / "many.jsonl"
    many.write_text("\n".join(json.dumps(e) for e in good) + "\n")
    arr = tmp_path / "arr.json"
    arr.write_text(json.dumps(good))
    assert main(["validate", str(one)]) == 0
    assert main(["validate", str(many), "--chain"]) == 0
    assert main(["validate", str(arr)]) == 0
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps(good[0]) + "\n" + json.dumps(good[1]) + "\n" + json.dumps({**good[1], "sequence": 5}) + "\n")
    assert main(["validate", str(bad), "--chain"]) == 1


def test_cli_validate_failures_exit_1(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("{not json")
    assert main(["validate", str(p)]) == 1
    assert main(["validate", str(tmp_path / "missing.json")]) == 1
    p.write_text(json.dumps({"event_id": "x"}))
    assert main(["validate", str(p)]) == 1
    deep = tmp_path / "deep.json"
    deep.write_text("[" * 100000 + "]" * 100000)
    assert main(["validate", str(deep)]) == 1


def test_cli_subprocess_exit_codes(tmp_path):
    f = tmp_path / "e.json"
    f.write_text(json.dumps(stamp(make("<entity>.created"), 1)))
    assert run("validate", str(f)).returncode == 0
    f.write_text("{}")
    assert run("validate", str(f)).returncode == 1
