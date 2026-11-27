import json
from pathlib import Path

try:  # the control-plane CI step installs only pytest; the schema checks then skip (see test_schemas_checked)
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    HAVE_SCHEMA = True
except ImportError:  # pragma: no cover
    HAVE_SCHEMA = False

from packpublish import Actor, PackPublisher
from packpublish.canon import canonical
from packpublish.fakes import (FakeAuditStore, FakePackStore, FakeSignerVerifier, FakeTrustedSigners,
                               fake_signature)

CONTRACTS = Path(__file__).resolve().parents[4] / "contracts"
T0 = 1_900_000_000  # 2030-03-17T17:46:40Z
ACC, FDR, FDR2 = "staff:acct-sa-01", "staff:founder-a", "staff:founder-b"


def _reg():
    reg = Registry()
    for f in CONTRACTS.glob("country-pack-*.schema.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        reg = reg.with_resource(d["$id"], Resource.from_contents(d))
    return reg


def schema_errors(kind, doc):
    if not HAVE_SCHEMA:
        return []
    schema = json.loads((CONTRACTS / f"country-pack-{kind}.schema.json").read_text(encoding="utf-8"))
    return [e.message for e in Draft202012Validator(schema, registry=_reg()).iter_errors(doc)]


def bundle(version="0.1.0"):
    pack = {"packId": "sa", "componentId": "country.sa", "countryCode": "SA", "version": version,
            "tax": {"roundingRule": "half_up", "codes": ["S", "Z"]}, "formats": {"numberSystem": "latn"}}
    return {"pack.json": canonical(pack) + b"\n", "manifest.json": canonical({"id": "country.sa", "version": version}) + b"\n",
            "evidence.json": canonical({"facts": []}) + b"\n"}


EVIDENCE = [{"id": "evidence:sa:0.2.0:01", "sha256": "sha256:" + "ab" * 32}]
EDITS = [{"file": "pack.json", "path": "formats.numberSystem", "op": "set", "value": "arab"},
         {"file": "pack.json", "path": "tax.roundingRule", "op": "set", "value": "half_even"}]


class World:
    def __init__(self, key_env="dev"):
        self.now = T0
        self.audit, self.store = FakeAuditStore(), FakePackStore()
        self.trusted = FakeTrustedSigners({("SA", ACC): "Fictional Accountant"}, {FDR: "EldonsLogic", FDR2: "sayegh9"})
        self.key_env = key_env
        self.pub = PackPublisher(trusted=self.trusted, verifier=FakeSignerVerifier(), audit=self.audit, store=self.store,
                                 clock=lambda: self.now, key_env=key_env, kid=f"cpk-{key_env}-01",
                                 product_choice_paths={"SA": ["formats.numberSystem"]})

    def draft(self, base=None, version="0.2.0", **kw):
        return self.pub.draft(base_files=base or bundle(), edits=kw.pop("edits", EDITS), evidence_refs=EVIDENCE,
                              new_version=version, **kw)

    def mfa(self, who, n=1, ago=60):
        from packpublish.workflow import _stamp
        return {"assertionRef": f"stepup:{who}:{n}", "method": "webauthn", "authTime": _stamp(self.now - ago)}

    def sign(self, d, who, role, sig=True, **kw):
        s = fake_signature(who, d.statement_digest) if sig else None
        return self.pub.sign_off(d, role=role, signer_id=who, mfa=kw.pop("mfa", None) or self.mfa(who), signature=s)

    def signed(self, d, **kw):
        return [self.sign(d, ACC, "market_accountant", **kw), self.sign(d, FDR, "founder", **kw)]

    def publish(self, d=None, rid="req-1", actor=None, sos=None):
        d = d or self.draft()
        r = self.pub.publish(rid, d, sos or self.signed(d), actor or Actor(FDR, "tok:1"))
        self.last, self.last_files = r, d.files  # the published files are the base of the next draft
        return d, r
