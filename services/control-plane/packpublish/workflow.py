"""Staff country-pack publishing workflow for one pack version (CMP-038 slice 2, Tier 3 compliance).

draft -> diff -> two sign-offs -> publish (record plus next index entry), and a one-founder rollback pin request.
Deterministic and fail closed: any refusal or port error raises `PublishError` and changes nothing. The workflow
moves and signs data; it never computes, converts or interprets a tax value (ADR-0031). Contract:
contracts/country-pack-store.md."""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from . import canon
from .canon import DIGEST_RE, REF_RE, SUBJECT_RE, canonical, digest
from .changerecord import validate_change_record
from .errors import PublishError

STEP_UP_SECONDS = 300
CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ROLES = ("market_accountant", "founder")


@dataclass(frozen=True)
class Actor:
    subject: str  # staff-realm subject (never an email)
    token_id: str


@dataclass(frozen=True)
class Draft:
    country: str
    pack_id: str
    component_id: str
    version: str
    base_version: str
    base_digest: str
    files: dict  # path -> exact stored bytes
    changes: tuple  # the field-level diff against the base, each classed statutory or product_choice
    diff_digest: str
    content_digest: str
    change_kind: str
    review_ref: str | None
    evidence_refs: tuple
    statement_digest: str


@dataclass(frozen=True)
class Change:
    """A withdrawal, floor raise or follow-up closure, bound to the exact index it was proposed against."""
    country: str
    kind: str
    target: dict
    reason_ref: str
    base_seq: int
    base_index_digest: str
    statement_digest: str


KINDS = ("withdrawal", "floor_raise", "follow_up_closure")
TARGET_KEYS = {"withdrawal": "version", "floor_raise": "version", "follow_up_closure": "publishId"}


def _change_statement(country, kind, target, reason_ref, base_index_digest) -> str:
    return digest(canonical({"op": "pack_change", "countryCode": country, "kind": kind, "target": target,
                             "reasonRef": reason_ref, "baseIndexDigest": base_index_digest}))


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _stamp(now: int) -> str:
    return datetime.fromtimestamp(now, tz=__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _derive_id(request_id: str, tag: str) -> str:
    n = int.from_bytes(hashlib.sha256(f"seshna.packpublish.{tag}\n{request_id}".encode()).digest()[:16], "big")
    return "".join(CROCKFORD[(n >> (5 * i)) & 31] for i in reversed(range(26)))


def _check(cond, code):
    if not cond:
        raise PublishError(code)


def _port(code, fn, *args):
    try:
        return fn(*args)
    except PublishError:
        raise
    except Exception:
        raise PublishError(code) from None


def _closed(fn):
    """Any unexpected exception from a public call is a refusal, never a crash or a partial result."""
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except PublishError:
            raise
        except Exception:
            raise PublishError("PP-001") from None
    wrapper.__name__, wrapper.__doc__ = fn.__name__, fn.__doc__
    return wrapper


class PackPublisher:
    def __init__(self, *, trusted, verifier, audit, store, clock: Callable[[], int], key_env: str, kid: str,
                 product_choice_paths: dict):
        _check(key_env in ("production", "staging", "dev") and isinstance(kid, str) and kid, "PP-001")
        self.trusted, self.verifier, self.audit, self.store, self.clock = trusted, verifier, audit, store, clock
        self.key_env, self.kid = key_env, kid
        self.paths = {k: frozenset(v) for k, v in product_choice_paths.items()}

    # 1. draft -----------------------------------------------------------------------------------------------
    @_closed
    def draft(self, *, base_files: dict, edits: list, evidence_refs: list, new_version: str,
              change_kind: str = "scheduled", review_ref: str | None = None) -> Draft:
        base = canon.parse_files(base_files)
        ident = {k: base["pack.json"].get(k) for k in ("packId", "countryCode", "componentId", "version")}
        _check(all(isinstance(v, str) for v in ident.values()), "PP-002")
        _check(canon.semver(new_version) > canon.semver(ident["version"]), "PP-021")
        _check(change_kind in ("scheduled", "urgent") and (review_ref is not None) == (change_kind == "urgent"), "PP-022")
        _check(review_ref is None or (isinstance(review_ref, str) and REF_RE.match(review_ref)), "PP-022")
        refs = self._evidence(evidence_refs)
        new = copy.deepcopy(base)
        for e in edits:
            canon.apply_edit(new, e)
        for f in ("pack.json", "manifest.json"):
            if "version" in new[f] or f == "pack.json":
                new[f]["version"] = new_version
        files = {p: canonical(v) + b"\n" for p, v in new.items()}
        country = ident["countryCode"]
        changes = canon.diff(base, canon.parse_files(files), self.paths.get(country, frozenset()))
        return self._build(country, ident, new_version, base_files, files, tuple(changes), change_kind, review_ref, refs)

    def _evidence(self, refs) -> tuple:
        ok = isinstance(refs, list) and refs and all(
            isinstance(r, dict) and set(r) == {"id", "sha256"} and isinstance(r["id"], str) and REF_RE.match(r["id"])
            and isinstance(r["sha256"], str) and DIGEST_RE.match(r["sha256"]) for r in refs)
        _check(ok and len({canonical(r) for r in refs}) == len(refs), "PP-001")
        return tuple(sorted((dict(r) for r in refs), key=lambda r: r["id"]))

    def _build(self, country, ident, version, base_files, files, changes, kind, review_ref, refs) -> Draft:
        cd = canon.content_digest(country, ident["packId"], version, files)
        dd = digest(canonical(list(changes)))
        stmt = digest(canonical({"packId": ident["packId"], "version": version, "contentDigest": cd,
                                 "diffDigest": dd, "changeKind": kind}))
        base_cd = canon.content_digest(country, ident["packId"], ident["version"], base_files)
        return Draft(country, ident["packId"], ident["componentId"], version, ident["version"], base_cd, files,
                     changes, dd, cd, kind, review_ref, refs, stmt)

    def _recheck_draft(self, d: Draft) -> None:
        """Rebuild every digest from the bytes; a draft changed after it was made is refused."""
        try:
            parsed = canon.parse_files(d.files)
            ok = (canon.content_digest(d.country, d.pack_id, d.version, d.files) == d.content_digest
                  and digest(canonical(list(d.changes))) == d.diff_digest
                  and parsed["pack.json"].get("version") == d.version and parsed["pack.json"].get("packId") == d.pack_id
                  and parsed["pack.json"].get("countryCode") == d.country
                  and parsed["pack.json"].get("componentId") == d.component_id)
            stmt = digest(canonical({"packId": d.pack_id, "version": d.version, "contentDigest": d.content_digest,
                                     "diffDigest": d.diff_digest, "changeKind": d.change_kind}))
        except PublishError:
            raise PublishError("PP-020") from None
        _check(ok and stmt == d.statement_digest and d.country in ("SA", "AE", "EG", "QA"), "PP-020")

    # 2. sign-off --------------------------------------------------------------------------------------------
    @_closed
    def sign_off(self, draft: Draft, *, role: str, signer_id: str, mfa: dict, signature: dict | None = None) -> dict:
        """One sign-off in the record's format. mfa: {assertionRef, method, authTime} from the step-up."""
        self._recheck_draft(draft)
        return self._signoff(draft, f"signoff:{draft.pack_id}:{draft.version}:{signer_id}", role, signer_id, mfa, signature)

    def _signoff(self, d, ref: str, role: str, signer_id: str, mfa: dict, signature: dict | None) -> dict:
        """`d` is a Draft or a Change: both carry `country` and `statement_digest`."""
        _check(role in ROLES and isinstance(signer_id, str) and SUBJECT_RE.match(signer_id), "PP-001")
        _check(isinstance(mfa, dict) and set(mfa) == {"assertionRef", "method", "authTime"}
               and isinstance(mfa["assertionRef"], str) and REF_RE.match(mfa["assertionRef"])
               and mfa["method"] in ("totp", "webauthn") and isinstance(mfa["authTime"], str), "PP-013")
        so = {"role": role, "signerId": signer_id, "signedAt": _stamp(self.clock()),
              "statementDigest": d.statement_digest,
              "mfa": {**mfa, "boundTo": {"signerId": signer_id, "statementDigest": d.statement_digest}}}
        if role == "market_accountant":
            name = _port("PP-031", self.trusted.accountant_name, d.country, signer_id)
            _check(isinstance(name, str) and name.strip(), "PP-010")
            so.update(name=name, market=d.country, signOffRef=ref)
        else:
            login = _port("PP-031", self.trusted.founder_login, signer_id)
            _check(isinstance(login, str) and login, "PP-010")
            so["founderLogin"] = login
        if signature is not None:
            so["signerSignature"] = copy.deepcopy(signature)
        self._check_signoff(d, so)
        return so

    def _check_signoff(self, d: Draft, so: dict) -> None:
        role, sid = so["role"], so["signerId"]
        if role == "market_accountant":
            _check(so.get("market") == d.country and _port("PP-031", self.trusted.accountant_name, d.country, sid), "PP-010")
            _check(_port("PP-031", self.trusted.founder_login, sid) is None, "PP-010")  # a founder is not the accountant
        else:
            _check(bool(_port("PP-031", self.trusted.founder_login, sid)), "PP-010")
        _check(so["statementDigest"] == d.statement_digest and so["mfa"]["boundTo"] ==
               {"signerId": sid, "statementDigest": d.statement_digest}, "PP-015")
        try:
            gap = (_t(so["signedAt"]) - _t(so["mfa"]["authTime"])).total_seconds()
        except (ValueError, KeyError, TypeError):
            raise PublishError("PP-013") from None
        _check(0 <= gap <= STEP_UP_SECONDS, "PP-013")
        sig = so.get("signerSignature")
        if self.key_env == "production":  # Q-652: each signer's own WebAuthn credential
            _check(sig is not None and so["mfa"]["method"] == "webauthn", "PP-014")
        _check(_port("PP-031", self.verifier.verify, sid, d.statement_digest, sig, self.key_env) is True, "PP-014")

    # 4. publish ---------------------------------------------------------------------------------------------
    @_closed
    def publish(self, request_id: str, draft: Draft, sign_offs: list, actor: Actor) -> dict:
        """Returns {record, index, auditId, replayed}. Audit is written before the store changes (Q-656)."""
        self._check_request_actor(request_id, actor)
        fp = digest(canonical({"op": "publish", "statement": draft.statement_digest, "actor": [actor.subject, actor.token_id],
                               "signOffs": list(sign_offs)}))
        done = self._replay(request_id, fp)
        if done:
            return done
        self._recheck_draft(draft)
        now = self._check_pair(draft, sign_offs, actor)
        raw = _port("PP-031", self.store.latest_index, draft.country)
        prev = json.loads(raw) if raw else None
        publish_id, audit_id = _derive_id(request_id, "publish"), "audit:" + _derive_id(request_id, "audit")
        index, predecessor = self._next_index(draft, prev, raw, publish_id, now)
        record = {
            "v": 1, "typ": "country_pack_version", "kid": self.kid, "keyEnv": self.key_env, "publishId": publish_id,
            "publishedAt": _stamp(now), "publishedBy": actor.subject, "packId": draft.pack_id,
            "countryCode": draft.country, "componentId": draft.component_id, "version": draft.version,
            "contentDigest": draft.content_digest, "files": canon.file_entries(draft.files), "predecessor": predecessor,
            "supersedes": None, "changeKind": draft.change_kind,
            "followUp": {"required": True, "reviewRef": draft.review_ref} if draft.change_kind == "urgent"
            else {"required": False},
            "diffDigest": draft.diff_digest, "evidenceRefs": [dict(r) for r in draft.evidence_refs],
            "signOffs": sorted((copy.deepcopy(s) for s in sign_offs), key=lambda s: s["role"]),
        }
        entry = {"action": "country_pack.publish", "at": record["publishedAt"], "countryCode": draft.country,
                 "packId": draft.pack_id, "version": draft.version, "contentDigest": draft.content_digest,
                 "publishId": publish_id, "indexSeq": index["indexSeq"],
                 "actor": {"kind": "staff", "subject": actor.subject, "tokenId": actor.token_id}}
        _port("PP-030", self.audit.write, audit_id, entry)  # failure: refuse, index untouched
        result = {"record": record, "index": index, "auditId": audit_id, "replayed": False}
        _port("PP-031", self.store.commit_publish, draft.country, index["indexSeq"] - 1, record,
              canonical(index), request_id, fp, result)
        return copy.deepcopy(result)

    def _check_pair(self, d, sign_offs, actor) -> int:
        """Exactly one accountant and one founder, two people, two step-ups, the actor one of them. Returns now."""
        _check(isinstance(sign_offs, list) and len(sign_offs) == 2 and all(isinstance(s, dict) for s in sign_offs)
               and sorted(s.get("role") for s in sign_offs) == sorted(ROLES), "PP-012")
        _check(len({s["signerId"] for s in sign_offs}) == 2, "PP-011")
        _check(len({s["mfa"]["assertionRef"] for s in sign_offs}) == 2, "PP-013")
        _check(actor.subject in {s["signerId"] for s in sign_offs}, "PP-012")
        for s in sign_offs:
            self._check_signoff(d, s)
        now = self.clock()
        _check(all(_t(s["signedAt"]) <= _t(_stamp(now)) for s in sign_offs), "PP-013")
        return now

    def _check_request_actor(self, request_id, actor):
        _check(isinstance(request_id, str) and REF_RE.match(request_id) and isinstance(actor, Actor)
               and SUBJECT_RE.match(actor.subject) and REF_RE.match(actor.token_id), "PP-001")

    def _replay(self, request_id, fp):
        prior = _port("PP-031", self.store.get_request, request_id)
        if prior is None:
            return None
        _check(prior[0] == fp, "PP-040")
        return {**prior[1], "replayed": True}

    def _next_index(self, d: Draft, prev, raw, publish_id, now):
        pub, wd = (prev["published"], prev["withdrawn"]) if prev else ([], [])
        known = sorted(pub + wd, key=lambda e: canon.semver(e["version"]))
        top = known[-1] if known else None
        _check(top is None or canon.semver(d.version) > canon.semver(top["version"]), "PP-021")
        _check(top is None or (top["version"], top["contentDigest"]) == (d.base_version, d.base_digest), "PP-021")
        index = {
            "v": 1, "typ": "country_pack_index", "kid": self.kid, "keyEnv": self.key_env, "countryCode": d.country,
            "indexSeq": prev["indexSeq"] + 1 if prev else 1, "predecessorDigest": digest(raw) if prev else None,
            "issuedAt": _stamp(now),
            "published": [*pub, {"version": d.version, "contentDigest": d.content_digest, "publishId": publish_id}],
            "withdrawn": list(wd), "floor": prev["floor"] if prev else d.version,
            "followUpOpen": [*(prev["followUpOpen"] if prev else []), *([publish_id] if d.change_kind == "urgent" else [])],
            "changeRecords": [],
        }
        pred = {"version": top["version"], "contentDigest": top["contentDigest"]} if top else None
        return index, pred

    # 5. rollback pin request --------------------------------------------------------------------------------
    @_closed
    def rollback_pin(self, request_id: str, *, tenant_id: str, country: str, target_version: str, actor: Actor,
                     step_up: dict, reason_ref: str, approval_ref: str) -> dict:
        """One founder, fresh step-up and a written reason (Q-655). Returns {pin, auditId, replayed}. The pin
        goes to the registry only; this does not run any tenant upgrade."""
        self._check_request_actor(request_id, actor)
        _check(isinstance(tenant_id, str) and 0 < len(tenant_id) <= 64 and country in ("SA", "AE", "EG", "QA")
               and isinstance(target_version, str), "PP-001")
        _check(all(isinstance(x, str) and REF_RE.match(x) for x in (reason_ref, approval_ref)), "PP-051")
        _check(isinstance(step_up, dict) and set(step_up) == {"ref", "authTime"} and isinstance(step_up["ref"], str)
               and REF_RE.match(step_up["ref"]) and isinstance(step_up["authTime"], str), "PP-051")
        fp = digest(canonical({"op": "rollback", "tenant": tenant_id, "country": country, "target": target_version,
                               "actor": [actor.subject, actor.token_id], "stepUp": step_up,
                               "reason": reason_ref, "approval": approval_ref}))
        done = self._replay(request_id, fp)
        if done:
            return done
        _check(bool(_port("PP-031", self.trusted.founder_login, actor.subject)), "PP-051")
        now = self.clock()
        try:
            age = now - int(_t(step_up["authTime"]).timestamp())
        except ValueError:
            raise PublishError("PP-051") from None
        _check(0 <= age <= STEP_UP_SECONDS, "PP-051")
        raw = _port("PP-031", self.store.latest_index, country)
        _check(raw is not None, "PP-050")
        idx = json.loads(raw)
        cur = _port("PP-031", self.store.get_pin, tenant_id, country)
        _check(cur is not None and cur["source"] == "store", "PP-050")
        t = canon.semver(target_version)
        entry = next((e for e in idx["published"] if e["version"] == target_version), None)
        _check(entry is not None and not any(w["version"] == target_version for w in idx["withdrawn"])
               and t >= canon.semver(idx["floor"]) and t < canon.semver(cur["version"]), "PP-050")
        audit_id = "audit:" + _derive_id(request_id, "audit")
        pin = {"v": 1, "typ": "country_pack_pin", "tenantId": tenant_id, "source": "store", "countryCode": country,
               "packId": cur["packId"], "version": target_version, "contentDigest": entry["contentDigest"],
               "publishId": entry["publishId"], "indexSeqAtPin": idx["indexSeq"], "pinSeq": cur["pinSeq"] + 1,
               "changeKind": "rollback",
               "changedBy": {"actorKind": "staff", "subject": actor.subject, "tokenId": actor.token_id},
               "approval": {"kind": "founder_rollback", "ref": approval_ref, "approvedBy": actor.subject,
                            "stepUpRef": step_up["ref"], "reasonRef": reason_ref},
               "changedAt": _stamp(now), "auditId": audit_id}
        _port("PP-030", self.audit.write, audit_id, {
            "action": "country_pack.pin_rollback", "at": pin["changedAt"], "tenantId": tenant_id, "countryCode": country,
            "version": target_version, "pinSeq": pin["pinSeq"],
            "actor": {"kind": "staff", "subject": actor.subject, "tokenId": actor.token_id}})
        result = {"pin": pin, "auditId": audit_id, "replayed": False}
        _port("PP-031", self.store.commit_pin, tenant_id, country, cur["pinSeq"], pin, request_id, fp, result)
        return copy.deepcopy(result)

    # 6. change records: withdrawal, floor raise, follow-up closure ----------------------------------------------
    @_closed
    def propose_change(self, *, kind: str, country: str, target: dict, reason_ref: str) -> Change:
        """Validates the change against the latest index and binds it to that index. Per-market only: a change
        names a country and a version or publish id, never a tenant."""
        key = TARGET_KEYS.get(kind)
        _check(key is not None and country in ("SA", "AE", "EG", "QA") and isinstance(target, dict)
               and set(target) == {key} and isinstance(target[key], str)
               and isinstance(reason_ref, str) and REF_RE.match(reason_ref), "PP-001")
        raw = _port("PP-031", self.store.latest_index, country)
        _check(raw is not None, "PP-060")
        self._apply_to_index(json.loads(raw), kind, dict(target), reason_ref)  # refuses a target that is not allowed
        base = digest(raw)
        return Change(country, kind, dict(target), reason_ref, json.loads(raw)["indexSeq"], base,
                      _change_statement(country, kind, target, reason_ref, base))

    @staticmethod
    def _apply_to_index(idx: dict, kind: str, target: dict, reason_ref: str) -> dict:
        """The next index body (without seq, digest or change records). Withdrawals stay forever, the floor only
        goes up, and an open follow-up is closed only by its own change."""
        pub, wd = list(idx["published"]), list(idx["withdrawn"])
        floor, open_fu = idx["floor"], list(idx["followUpOpen"])
        if kind == "follow_up_closure":
            _check(target["publishId"] in open_fu, "PP-060")
            open_fu.remove(target["publishId"])
        else:
            hit = next((e for e in pub if e["version"] == target["version"]), None)
            _check(hit is not None, "PP-060")  # unpublished, unknown or already withdrawn
            if kind == "withdrawal":
                _check(len(pub) > 1, "PP-060")  # never leave a market with nothing to pin to
                pub.remove(hit)
                wd.append({"version": hit["version"], "contentDigest": hit["contentDigest"], "reasonRef": reason_ref})
                open_fu = [p for p in open_fu if p != hit["publishId"]]  # a withdrawn version is no longer reviewable
            else:
                _check(canon.semver(target["version"]) > canon.semver(floor), "PP-060")
                floor = target["version"]
        return {**idx, "published": pub, "withdrawn": wd, "floor": floor, "followUpOpen": open_fu}

    @_closed
    def sign_change(self, change: Change, *, role: str, signer_id: str, mfa: dict, signature: dict | None = None) -> dict:
        self._recheck_change(change)
        return self._signoff(change, f"signoff:{change.statement_digest[7:39]}:{signer_id}", role, signer_id, mfa, signature)

    def _recheck_change(self, c: Change) -> None:
        ok = (isinstance(c, Change) and c.kind in KINDS and c.country in ("SA", "AE", "EG", "QA")
              and isinstance(c.target, dict) and set(c.target) == {TARGET_KEYS[c.kind]}
              and c.statement_digest == _change_statement(c.country, c.kind, c.target, c.reason_ref, c.base_index_digest))
        _check(ok, "PP-020")

    @_closed
    def apply_change(self, request_id: str, change: Change, sign_offs: list, actor: Actor) -> dict:
        """Same two-person rule as a publish. Returns {changeRecord, index, auditId, replayed}; audit first."""
        self._check_request_actor(request_id, actor)
        _check(isinstance(change, Change), "PP-001")
        fp = digest(canonical({"op": "change", "statement": change.statement_digest,
                               "actor": [actor.subject, actor.token_id], "signOffs": list(sign_offs)}))
        done = self._replay(request_id, fp)
        if done:
            return done
        self._recheck_change(change)
        now = self._check_pair(change, sign_offs, actor)
        raw = _port("PP-031", self.store.latest_index, change.country)
        _check(raw is not None and digest(raw) == change.base_index_digest, "PP-061")
        idx = json.loads(raw)
        new = self._apply_to_index(idx, change.kind, change.target, change.reason_ref)
        change_id, audit_id = "change:" + _derive_id(request_id, "change"), "audit:" + _derive_id(request_id, "audit")
        rec = {"v": 1, "typ": "country_pack_change_record", "id": change_id, "kind": change.kind,
               "countryCode": change.country, "target": dict(change.target), "reasonRef": change.reason_ref,
               "baseIndexSeq": idx["indexSeq"], "baseIndexDigest": change.base_index_digest,
               "statementDigest": change.statement_digest, "requestedBy": actor.subject, "recordedAt": _stamp(now),
               "signOffs": sorted((copy.deepcopy(s) for s in sign_offs), key=lambda s: s["role"])}
        index = {**new, "indexSeq": idx["indexSeq"] + 1, "predecessorDigest": change.base_index_digest,
                 "issuedAt": _stamp(now), "kid": self.kid, "keyEnv": self.key_env,
                 "changeRecords": [{"id": change_id, "kind": change.kind, "sha256": digest(canonical(rec))}]}
        validate_change_record(rec)  # fail closed before audit or store change
        _port("PP-030", self.audit.write, audit_id, {
            "action": f"country_pack.change.{change.kind}", "at": rec["recordedAt"], "countryCode": change.country,
            "changeId": change_id, "target": dict(change.target), "indexSeq": index["indexSeq"],
            "actor": {"kind": "staff", "subject": actor.subject, "tokenId": actor.token_id}})
        result = {"changeRecord": rec, "index": index, "auditId": audit_id, "replayed": False}
        _port("PP-031", self.store.commit_change, change.country, idx["indexSeq"], rec, canonical(index),
              request_id, fp, result)
        return copy.deepcopy(result)
