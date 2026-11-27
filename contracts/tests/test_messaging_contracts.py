"""Schema tests for the messaging and SMS connector contract (DSC-022, contracts/connector-messaging.md, ADR-0078).

Valid examples must pass; every connector-messaging file in examples/invalid/ must fail. Also checks that the
Markdown and JSON versions agree, that every error code the examples use is in the catalog, and that every event
type the contract names is registered in events.md. Run: python3 -m pytest contracts/tests -q
"""
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

C = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((C / "connector-messaging.schema.json").read_text(encoding="utf-8"))
DOC = (C / "connector-messaging.md").read_text(encoding="utf-8")
V = Draft202012Validator(SCHEMA, format_checker=Draft202012Validator.FORMAT_CHECKER)
VALID = sorted(C.glob("examples/connector-messaging-*.json"))
INVALID = sorted(C.glob("examples/invalid/connector-messaging-*.json"))


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def test_schema_is_valid():
    Draft202012Validator.check_schema(SCHEMA)


def test_every_kind_has_a_valid_example():
    assert {load(p)["kind"] for p in VALID} == set(SCHEMA["properties"]["kind"]["enum"])


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_examples(path):
    assert [e.message for e in V.iter_errors(load(path))] == []


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_invalid_examples_fail(path):
    assert not V.is_valid(load(path))


def test_versions_agree():
    assert re.search(r"^Version: (\S+)$", DOC, re.M).group(1) == SCHEMA["version"]
    assert SCHEMA["$id"].endswith(":" + SCHEMA["version"])


def test_error_codes_in_catalog():
    catalog = set(re.findall(r"^\| `(MSG-\d{3})` \|", DOC, re.M))
    assert len(catalog) >= 10
    used = {load(p).get("errorCode") for p in VALID} - {None}
    assert used <= catalog


def test_event_types_registered():
    events = (C / "events.md").read_text(encoding="utf-8")
    section = DOC.split("## 10. Audit and events", 1)[1].split("\n## ", 1)[0]
    named = set(re.findall(r"`((?:message|consent|meter)\.[a-z_]+)`", section))
    assert named, "the contract names its events"
    assert {n for n in named if f"`{n}`" not in events} == set()
