import json
import os

import pytest

from registry import MAX_FILE_BYTES, Registry
from registry_helpers import REGISTRY_DIR, codes, fixture_manifest, variant, write


def test_load_folder_round_trip(tmp_path):
    m = fixture_manifest("core.item")
    write(tmp_path, "core.item.json", m)
    reg = Registry.load(tmp_path)
    assert reg.ok and reg.get("core.item", "0.1.0") == m


def test_missing_folder_raises(tmp_path):
    with pytest.raises(OSError):
        Registry.load(tmp_path / "nope")


def test_non_json_files_ignored(tmp_path):
    write(tmp_path, "README.md", "hello")
    assert Registry.load(tmp_path).issues == []


def test_bad_file_names_rejected(tmp_path):
    m = fixture_manifest("core.item")
    for name in ("..json", "Core.Item.json", "core.item..json", "core item.json", "a.json", "core.item@1.0.0@x.json"):
        write(tmp_path, name, m)
    reg = Registry.load(tmp_path)
    assert codes(reg.errors) == ["REG-007"] and len(reg.errors) == 6 and reg.list_components() == []


def test_id_with_traversal_in_manifest_rejected(tmp_path):
    write(tmp_path, "core.item.json", variant(id="../../etc/passwd"))
    reg = Registry.load(tmp_path)
    assert "REG-001" in codes(reg.errors) and reg.list_components() == []


def test_lookups_with_traversal_ids_are_inert():
    reg = Registry.load(REGISTRY_DIR)
    for bad in ("../core.item", "core.item/../x", "", None, 5):
        assert reg.versions(bad) == [] and reg.get(bad, "0.1.0") is None


def test_file_name_must_match_manifest(tmp_path):
    write(tmp_path, "core.customer.json", fixture_manifest("core.item"))
    assert codes(Registry.load(tmp_path).errors) == ["REG-007"]
    write(tmp_path, "core.item@0.9.0.json", fixture_manifest("core.item"))
    assert len(Registry.load(tmp_path).errors) == 2


def test_oversize_file_rejected(tmp_path):
    p = write(tmp_path, "core.item.json", fixture_manifest("core.item"))
    with open(p, "ab") as fh:
        fh.write(b" " * (MAX_FILE_BYTES + 1))
    reg = Registry.load(tmp_path)
    assert codes(reg.errors) == ["REG-007"] and reg.list_components() == []


def test_not_json_and_not_object(tmp_path):
    write(tmp_path, "core.item.json", "{not json")
    write(tmp_path, "core.customer.json", "[1, 2]")
    (tmp_path / "core.supplier.json").write_bytes(b"\xff\xfe\x00")
    deep = "[" * 100000 + "]" * 100000
    write(tmp_path, "stock.ledger.json", deep)
    reg = Registry.load(tmp_path)
    assert codes(reg.errors) == ["REG-007"] and len(reg.errors) == 4


def test_symlink_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = write(outside, "target.json", fixture_manifest("core.item"))
    folder = tmp_path / "reg"
    folder.mkdir()
    os.symlink(target, folder / "core.item.json")
    reg = Registry.load(folder)
    assert codes(reg.errors) == ["REG-007"] and reg.list_components() == []


def test_subfolders_not_read(tmp_path):
    sub = tmp_path / "core.item.json"
    sub.mkdir()
    assert Registry.load(tmp_path).list_components() == []


def test_multiple_versions_in_one_folder(tmp_path):
    write(tmp_path, "core.item.json", fixture_manifest("core.item"))
    write(tmp_path, "core.item@0.10.0.json", variant(version="0.10.0"))
    write(tmp_path, "core.item@0.2.0.json", variant(version="0.2.0"))
    reg = Registry.load(tmp_path)
    assert reg.ok and reg.versions("core.item") == ["0.1.0", "0.2.0", "0.10.0"]


def test_manifest_is_data_only(tmp_path):
    marker = tmp_path / "executed"
    m = variant(description=f"__import__('os').system('touch {marker}') and more text")
    m["provides"][0]["artifacts"][0]["ref"] = "../../../etc/passwd"
    write(tmp_path, "core.item.json", m)
    Registry.load(tmp_path)
    assert not marker.exists()


def test_deterministic_ordering(tmp_path):
    names = ["stock.ledger", "core.item", "core.customer", "sales.quote"]
    for n in reversed(names):
        write(tmp_path, f"{n}.json", fixture_manifest(n))
    write(tmp_path, "zz.bad.json", "oops")
    a, b = Registry.load(tmp_path), Registry.load(tmp_path)
    assert a.list_components() == sorted(names)
    assert [str(i) for i in a.issues] == [str(i) for i in b.issues]
    assert json.dumps(a.as_validation_context_registry()) == json.dumps(b.as_validation_context_registry())
