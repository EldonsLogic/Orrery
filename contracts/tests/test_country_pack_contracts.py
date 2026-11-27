"""Schema tests for the country pack store contracts (CMP-038 slice 1, contracts/country-pack-store.md).

Valid examples must pass; every file in examples/invalid/ must fail. The record-local x-validator-rules that
JSON Schema cannot express (distinct signers and assertion refs, MFA binding, publishedBy, statement and
content digests, time order, the domain-separated signer challenge) are checked by `record_rule_errors`, a reference for CMP-038 and CMP-039; the
loader's own checks stay authoritative. Run: uv run --with jsonschema --with referencing --with pytest
python3 -m pytest contracts/tests -q
"""
import base64
import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

C = Path(__file__).resolve().parent.parent
KINDS = ("record", "index", "pin", "change-record")


def _registry():
    reg = Registry()
    for f in C.glob("country-pack-*.schema.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        reg = reg.with_resource(data["$id"], Resource.from_contents(data))
    return reg


REG = _registry()


def validator(kind):
    schema = json.loads((C / f"country-pack-{kind}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=REG)


def kind_of(path):
    """country-pack-<kind>-<name>.json; the longest kind wins (change-record before record)."""
    rest = path.name[len("country-pack-"):]
    return max((k for k in KINDS if rest.startswith(k + "-")), key=len)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical(obj) -> bytes:
    # RFC 8785 for the ASCII-only, integer-only objects used here; the shared vectors (CMP39-T07, T42) bind.
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


SIGNOFF_DOMAIN = b"country-pack-signoff-v1\n"


def signoff_challenge(statement_digest):
    """Contract 0.3.0 assumption 4: base64url (no padding) of SHA-256(domain + LF + ASCII statementDigest)."""
    raw = hashlib.sha256(SIGNOFF_DOMAIN + statement_digest.encode("ascii")).digest()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _client_data(sig):
    return json.loads(base64.urlsafe_b64decode(sig["clientDataJSON"] + "=" * (-len(sig["clientDataJSON"]) % 4)))


def _t(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def record_rule_errors(rec):
    errs = []
    so = rec["signOffs"]
    if len({s["signerId"] for s in so}) != len(so):
        errs.append("signoff_same_person")
    if len({s["mfa"]["assertionRef"] for s in so}) != len(so):
        errs.append("signoff_mfa: repeated assertionRef")
    if rec["publishedBy"] not in {s["signerId"] for s in so}:
        errs.append("publishedBy is not a signer")
    files = sorted(rec["files"], key=lambda f: f["path"])
    content = digest(canonical({"countryCode": rec["countryCode"], "packId": rec["packId"],
                                "version": rec["version"], "files": files}))
    if content != rec["contentDigest"]:
        errs.append("content_digest_mismatch")
    stmt = digest(canonical({k: rec[k] for k in ("packId", "version", "contentDigest", "diffDigest", "changeKind")}))
    for s in so:
        if s["statementDigest"] != stmt:
            errs.append("signoff_statement_mismatch")
        if s["mfa"]["boundTo"] != {"signerId": s["signerId"], "statementDigest": s["statementDigest"]}:
            errs.append("signoff_mfa: boundTo")
        gap = (_t(s["signedAt"]) - _t(s["mfa"]["authTime"])).total_seconds()
        if not 0 <= gap <= 300:
            errs.append("signoff_mfa: authTime window")
        if _t(s["signedAt"]) > _t(rec["publishedAt"]):
            errs.append("signedAt after publishedAt")
        if s["role"] == "market_accountant" and s["market"] != rec["countryCode"]:
            errs.append("signoff_certification_mismatch: market")
        sig = s.get("signerSignature")
        if sig and _client_data(sig).get("challenge") != signoff_challenge(s["statementDigest"]):
            errs.append("signer_signature: challenge")
    return errs


def examples(kind, invalid=False):
    base = C / "examples" / ("invalid" if invalid else "")
    return sorted(p for p in base.glob(f"country-pack-{kind}-*.json") if kind_of(p) == kind)


@pytest.mark.parametrize("kind", KINDS)
def test_schema_is_valid(kind):
    Draft202012Validator.check_schema(json.loads((C / f"country-pack-{kind}.schema.json").read_text(encoding="utf-8")))


@pytest.mark.parametrize("path", [p for k in KINDS for p in examples(k)], ids=lambda p: p.name)
def test_valid_examples_pass(path):
    kind = kind_of(path)
    errors = [e.message for e in validator(kind).iter_errors(load(path))]
    assert errors == []
    if kind == "record":
        assert record_rule_errors(load(path)) == []
    if kind == "change-record":  # same domain-separated challenge as a publish (assumption 4)
        for s in load(path)["signOffs"]:
            if "signerSignature" in s:
                assert _client_data(s["signerSignature"])["challenge"] == signoff_challenge(s["statementDigest"])


@pytest.mark.parametrize("path", [p for k in KINDS for p in examples(k, invalid=True)], ids=lambda p: p.name)
def test_invalid_examples_fail(path):
    assert not validator(kind_of(path)).is_valid(load(path))


def test_every_kind_has_valid_and_invalid_examples():
    for kind in KINDS:
        assert examples(kind) and examples(kind, invalid=True), kind


def test_raw_digest_challenge_refused():
    """A signerSignature over the raw statementDigest (pre-0.3.0) is refused; the domain-separated one passes."""
    rec = load(C / "examples" / "country-pack-record-sa-urgent-production.json")
    s = rec["signOffs"][0]
    raw = base64.urlsafe_b64encode(bytes.fromhex(s["statementDigest"][7:])).rstrip(b"=").decode("ascii")
    cd = {**_client_data(s["signerSignature"]), "challenge": raw}
    s["signerSignature"]["clientDataJSON"] = base64.urlsafe_b64encode(
        json.dumps(cd, separators=(",", ":")).encode()).rstrip(b"=").decode("ascii")
    assert "signer_signature: challenge" in record_rule_errors(rec)


def _dev_record():
    return load(C / "examples" / "country-pack-record-sa-scheduled-dev.json")


def test_same_signer_twice_is_schema_valid_but_refused_by_rule():
    rec = _dev_record()
    acc, fdr = rec["signOffs"]
    acc["signerId"] = fdr["signerId"]
    acc["mfa"]["boundTo"]["signerId"] = fdr["signerId"]
    assert validator("record").is_valid(rec)
    assert "signoff_same_person" in record_rule_errors(rec)


def test_repeated_assertion_ref_and_outsider_publisher_refused():
    rec = _dev_record()
    rec["signOffs"][0]["mfa"]["assertionRef"] = rec["signOffs"][1]["mfa"]["assertionRef"]
    rec["publishedBy"] = "staff:someone-else"
    errs = record_rule_errors(rec)
    assert "signoff_mfa: repeated assertionRef" in errs and "publishedBy is not a signer" in errs


def test_statement_for_other_content_refused():
    rec = _dev_record()
    rec["diffDigest"] = digest(b"another diff")
    assert validator("record").is_valid(rec)
    assert "signoff_statement_mismatch" in record_rule_errors(rec)


@pytest.mark.parametrize("bad", ["SHA256:" + "a" * 64, "sha256:" + "A" * 64, "a" * 64, "sha256:" + "a" * 63,
                                 "sha256:" + "a" * 65, "sha512:" + "a" * 64, "sha256:" + "g" * 64])
def test_digest_format(bad):
    rec = _dev_record()
    rec["contentDigest"] = bad
    assert not validator("record").is_valid(rec)


@pytest.mark.parametrize("where", ["record", "signoff", "mfa", "file", "evidence"])
def test_no_extra_properties(where):
    rec = _dev_record()
    target = {"record": rec, "signoff": rec["signOffs"][0], "mfa": rec["signOffs"][0]["mfa"],
              "file": rec["files"][0], "evidence": rec["evidenceRefs"][0]}[where]
    target["extra"] = 1
    assert not validator("record").is_valid(rec)


def test_both_roles_required_in_either_order():
    rec = _dev_record()
    rec["signOffs"].reverse()
    assert validator("record").is_valid(rec)
    two_acc = copy.deepcopy(rec)
    two_acc["signOffs"] = [copy.deepcopy(rec["signOffs"][1]) for _ in range(2)]
    assert not validator("record").is_valid(two_acc)


def test_trailing_newline_refused_for_digest_and_id():
    # Python re.search lets `$` match before a final "\n"; the schemas use (?![\s\S]) so ECMA-262 agrees.
    rec = _dev_record()
    rec["contentDigest"] = rec["contentDigest"] + "\n"
    assert not validator("record").is_valid(rec)
    rec = _dev_record()
    rec["packId"] = rec["packId"] + "\n"
    assert not validator("record").is_valid(rec)
