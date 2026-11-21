import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_component_reviewers as c  # noqa: E402


def manifest(level="reviewed", reviewed_by=("eldonslogic",), owner="sayegh9"):
    cert = {"level": level}
    if reviewed_by is not None:
        cert["reviewedBy"] = list(reviewed_by)
    return {"id": "x/y", "owner": {"github": owner}, "certification": cert}


def test_clean_manifest_passes():
    assert c.check_manifest(manifest(), "m") == []
    assert c.check_manifest(manifest("certified", ["EldonsLogic", "other"]), "m") == []


def test_owner_listed_as_reviewer_fails():
    out = c.check_manifest(manifest(reviewed_by=["sayegh9"]), "m")
    assert len(out) == 1 and "owner.github" in out[0]


def test_owner_match_ignores_case_at_sign_and_whitespace():
    for variant in ["SayEgh9", "@sayegh9", " @SAYEGH9 ", "@ sayegh9\n"]:
        assert c.check_manifest(manifest(reviewed_by=["eldonslogic", variant]), "m"), variant
    assert c.check_manifest(manifest(owner="@SayEgh9", reviewed_by=["sayegh9"]), "m")


def test_empty_reviewer_list_at_reviewed_level_fails():
    for level in ["reviewed", "certified", "regulated"]:
        assert c.check_manifest(manifest(level, []), "m"), level
        assert c.check_manifest(manifest(level, None), "m"), level
        assert c.check_manifest(manifest(level, ["", " @ "]), "m"), level


def test_unreviewed_component_passes():
    for level in ["draft", "tested"]:
        assert c.check_manifest(manifest(level, []), "m") == []
        assert c.check_manifest(manifest(level, None), "m") == []


def test_malformed_manifest_fails_closed():
    bad = [
        [],
        {},
        {"certification": "reviewed", "owner": {"github": "a"}},
        {"certification": {"level": "bogus"}, "owner": {"github": "a"}},
        {"certification": {"level": "reviewed", "reviewedBy": "bob"}, "owner": {"github": "a"}},
        {"certification": {"level": "reviewed", "reviewedBy": [1]}, "owner": {"github": "a"}},
        {"certification": {"level": "reviewed", "reviewedBy": ["bob"]}},
        {"certification": {"level": "reviewed", "reviewedBy": ["bob"]}, "owner": {"github": ""}},
    ]
    for data in bad:
        assert c.check_manifest(data, "m"), data


def test_run_reports_one_line_per_problem_and_exit_code(tmp_path, capsys):
    root = tmp_path
    for name, data in {
        "a/ok": manifest(),
        "b/same": manifest(reviewed_by=["SAYEGH9"]),
        "c/empty": manifest("regulated", []),
    }.items():
        d = root / "components" / name
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps(data))
    bad = root / "components" / "d" / "broken"
    bad.mkdir(parents=True)
    (bad / "manifest.json").write_text("{not json")
    assert c.run(root) == 1
    lines = capsys.readouterr().out.strip().splitlines()
    problems = [ln for ln in lines if ln.startswith("components/")]
    assert len(problems) == 3
    assert not any("a/ok" in ln for ln in problems)


def test_run_passes_on_clean_tree(tmp_path):
    d = tmp_path / "components" / "a"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps(manifest("tested", [])))
    assert c.run(tmp_path) == 0


def test_real_repo_manifests_pass():
    assert c.run(Path(__file__).resolve().parent.parent.parent) == 0
