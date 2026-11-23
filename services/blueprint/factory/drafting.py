"""AI drafting of a candidate component into the factory sandbox (BPL-017, first slice; ADR-0065 Proposed).

The model only drafts; this module decides. Deterministic around one model call made through the model-call port
(contracts/model-call.md, PLT-026). The request is untrusted data: it travels only as an `untrusted` block, the
instructions are a platform block by reference. The draft is never trusted either: `provides` must be exactly the
requested need (proven plain by `policy.classify`, never by the model), fixed fields are set here, word lists are a
secondary deny, the manifest must pass admission, files go to a temp folder under the caller's sandbox root (never
components/ or the library) and are renamed into place only after the static check and the audit record succeed.
Candidate code is never run in this slice (no OS sandbox before INF-014). Nothing is promoted: promotion needs a
named reviewer who is not the requester (ADR-0034). Every outcome, including an internal error, is one audit record.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import posixpath
import secrets
import shutil
import stat
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

from component_request import policy
from component_request.text import ar_forms, fold, injection, per_client, personal_data, scope_hits, stems, tokens
from registry.admission import admit
from registry.store import RawManifest

from .errors import FacError
from .runner import check
from .scan import check_relpath

REPO = Path(__file__).resolve().parents[3]
REQUEST_SCHEMA = Draft202012Validator(json.loads(Path(__file__).with_name("request.schema.json").read_text("utf-8")))
PROMPT_VERSION, PROMPT_BLOCK = "factory.drafter.v1", "p_factory_drafter"
TIER, PURPOSE, MAX_OUT, MIN_OUT = "mid", "build", 8000, 2000
MAX_FILES, MAX_BYTES = 20, 200_000
MODEL_KEYS = {"version", "name", "description", "provides", "parameters", "tests", "engineCompatibility", "i18n"}
RESERVED_NAMESPACES = {"core", "country", "compliance", "platform", "system", "library", "engine", "registry", "factory",
                       "components"}            # plus the first segment of every id and capability in components/
SCRIPT_KEYS = {"formula", "expression", "script", "server_script", "python", "code", "condition", "eval", "depends_on",
               "query", "sql", "calc", "template", "default"}
TYPE_KEYS = ("fieldtype", "type", "kind")          # any object with one of these is a field
NAME_KEYS = ("fieldname", "name", "id", "label")
FILE_TYPES = {".py", ".json"}
TEMPLATE_MARKS = ("eval:", "{{", "{%")
STALE_TMP_SECONDS = 3600
PARAM_TYPES = {"string": "text", "enum": "select"}       # other manifest parameter types are never plain here
# Secondary deny lists (a hit refuses, a miss proves nothing): auth and tenancy words, plus money words the shared
# BPL-016 scope list leaves out on purpose (it allows a link to a sales invoice).
AUTH_TOKENS = {"auth", "authentication", "authorization", "authorisation", "login", "logon", "logout", "signin",
               "password", "passcode", "permission", "privilege", "role", "rbac", "acl", "accesscontrol", "admin",
               "administrator", "superuser", "sudo", "tenant", "tenancy", "session", "sso", "mfa", "otp", "oauth", "jwt",
               "credential", "token", "authenticate", "authenticated", "authenticating", "passwd", "2fa", "apikey",
               "user"}
MONEY_TOKENS = policy.RESTRICTED_TOKENS | policy.FINANCIAL_TOKENS | {
    "invoice", "debit", "credit", "posting", "levy", "billing", "pricing", "margin", "bank", "treasury", "fiscal", "postto"}
# Arabic stems, matched per word (and adjacent word pair) after prefix removal, never across word boundaries.
AUTH_AR = tuple(fold(x) for x in ("صلاحي", "مستاجر", "دخول", "كلمهالمرور", "كلمهالسر", "اذون", "اذن", "مصادق",
                                  "مستخدم", "ادوار", "جلسه", "جلسات", "تفويض", "تسجيلالدخول"))
MONEY_AR = tuple(fold(x) for x in ("رصيد", "خصم", "سعر", "اسعار", "مبلغ", "عموله", "دائن", "مدين", "قبض", "ارباح", "ربح",
                                   "ميزانيه", "بدل", "رسوم", "بنك", "نقد", "مصروف", "ايراد", "دفع", "سداد", "تسويه"))

(INVALID, INJECTION, RIGID, UNPROVEN, MODEL_REFUSED, MALFORMED, OUTSIDE, MANIFEST, SANDBOX, INTERNAL, PER_CLIENT,
 PERSONAL, CHECK_FAILED, RESERVED_ID, NOT_STAFF) = (f"FDR-{i:03d}" for i in range(1, 16))
STAFF_REALM = "staff"     # identity Realm.STAFF (services/control-plane/identity/models.py); Q-600: staff only for now


class Refused(Exception):
    def __init__(self, code: str, reason: str, status: str = "refused", hits=()):
        super().__init__(f"{code}:{reason}")
        self.code, self.reason, self.status, self.hits = code, reason, status, sorted(hits)


@dataclass
class Outcome:
    status: str                 # drafted | refused | model_refused
    code: str | None
    reason: str | None
    record: dict
    draft_dir: Path | None = None


def _sha(doc) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def rigid_hits(*texts: str) -> list[str]:
    """Ledger, tax, e-invoicing, payroll, audit, money, auth or tenancy words (with "ta x" and "log in" pairs)."""
    hits = set(scope_hits(*texts))
    for t in texts:
        toks = tokens(t)
        words = {s for w in toks + [a + b for a, b in zip(toks, toks[1:])] for s in stems(w)}
        hits.update(words & (AUTH_TOKENS | MONEY_TOKENS))
        forms = {f for w in toks + [a + b for a, b in zip(toks, toks[1:])] for f in ar_forms(w)}
        hits.update(a for a in AUTH_AR + MONEY_AR if any(f.startswith(a) for f in forms))
        if policy.financial_hit(t):
            hits.add("financial")
        hits.update(m for m in TEMPLATE_MARKS if m in t)
    return sorted(hits)


def _deny(code: str, *texts: str) -> None:
    hits = rigid_hits(*texts)
    if hits:
        raise Refused(code, "route_to_human", hits=hits)


def existing_names() -> set[str]:
    """Every component id and capability already in components/ (a manifest that cannot be read fails closed)."""
    out = set()
    for p in (REPO / "components").rglob("manifest.json"):
        m = json.loads(p.read_text(encoding="utf-8"))
        out.add(m["id"])
        out.update(x["capability"] for x in m.get("provides", []))
    return out


def check_request(req) -> None:
    if not isinstance(req, dict) or next(REQUEST_SCHEMA.iter_errors(req), None) is not None:
        raise Refused(INVALID, "schema")
    text = [req["title"], req["description"]]
    if any(injection(t) or injection(fold(t)) for t in text):
        raise Refused(INJECTION, "instruction_like_text")
    if any(per_client(t) for t in text):
        raise Refused(PER_CLIENT, "per_client_wording")
    if any(personal_data(t) for t in text):
        raise Refused(PERSONAL, "personal_data_or_secret")
    cid, ref = req["component_id"], req["need"]["ref"]
    _deny(RIGID, *text, cid, ref)
    if policy.identifier_hits(cid) or policy.identifier_hits(ref):
        raise Refused(RIGID, "route_to_human", hits=policy.identifier_hits(cid) + policy.identifier_hits(ref))
    if policy.classify(req["need"]["kind"], ref)[0] != "plain":
        raise Refused(UNPROVEN, "route_to_human")
    names = existing_names()
    if cid.split(".")[0] in RESERVED_NAMESPACES | {n.split(".")[0] for n in names} or cid in names:
        raise Refused(RESERVED_ID, "reserved_or_existing_component_id")


def expected_provides(req: dict) -> list:
    art = {"type": req["need"]["kind"], "ref": req["need"]["ref"]}
    if art["type"] == "entity":
        art["riskClass"] = "plain"       # proven by policy.classify on the request, not taken from the model
    return [{"capability": req["component_id"], "artifacts": [art]}]


def _layout(files: list) -> None:
    """Paths compared after normpath, NFC and casefold; no '.', twins or file-versus-folder clashes."""
    seen, dirs = {"manifest.json", "draft.json"}, set()
    for rel, _ in files:
        if rel != posixpath.normpath(rel) or "." in rel.split("/") or rel != unicodedata.normalize("NFC", rel):
            raise Refused(OUTSIDE, "unnormalised_path")
        key = rel.casefold()
        if key in seen:
            raise Refused(MALFORMED, "reserved_or_duplicate_path")
        seen.add(key)
        parts = key.split("/")
        dirs.update("/".join(parts[:i]) for i in range(1, len(parts)))
    if seen & dirs:
        raise Refused(MALFORMED, "file_folder_clash")


def _json_fields(rel: str, content: str) -> None:
    """Declared fields in a JSON artifact must be plain (policy.field_verdict); script-like keys are refused."""
    try:
        doc = json.loads(content)
    except ValueError:
        raise Refused(MALFORMED, "json_file")
    stack = [doc]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            keys = {str(k).casefold() for k in node}
            if SCRIPT_KEYS & keys:
                raise Refused(RIGID, "route_to_human", hits=[f"{rel}:script"])
            low = {str(k).casefold(): v for k, v in node.items()}
            typ = next((low[k] for k in TYPE_KEYS if k in low), None)
            if any(k in low for k in TYPE_KEYS):
                name = next((low[k] for k in NAME_KEYS if isinstance(low.get(k), str)), "")
                f = {"name": name, "type": typ.casefold() if isinstance(typ, str) else "?", "options": low.get("options"),
                     "target": low.get("target")}
                if policy.field_verdict(set(), f)[0] != "plain":
                    raise Refused(RIGID, "route_to_human", hits=[f"{rel}:{name}"])
            stack.extend(node.values())


def check_draft(req: dict, text: str, owner: str) -> tuple[dict, list]:
    """-> (manifest with fixed fields, [(relpath, content)]). Raises Refused; never repairs a draft."""
    try:
        d = json.loads(text)
    except (TypeError, ValueError, RecursionError):
        raise Refused(MALFORMED, "not_json")
    if not isinstance(d, dict) or set(d) != {"manifest", "files"} or not isinstance(d["manifest"], dict):
        raise Refused(MALFORMED, "shape")
    m, files = d["manifest"], d["files"]
    if not set(m) <= MODEL_KEYS or not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise Refused(MALFORMED, "shape")
    out, size = [], 0
    for f in files:
        if not isinstance(f, dict) or set(f) != {"path", "content"} or not isinstance(f["content"], str):
            raise Refused(MALFORMED, "file_shape")
        try:
            rel = check_relpath(f["path"])
        except FacError:
            raise Refused(OUTSIDE, "path_outside_sandbox")
        try:
            size += len(f["content"].encode("utf-8"))
        except UnicodeError:
            raise Refused(MALFORMED, "not_utf8")
        out.append((rel, f["content"]))
    if size > MAX_BYTES:
        raise Refused(MALFORMED, "too_big")
    _layout(out)
    if any(posixpath.splitext(r)[1].casefold() not in FILE_TYPES for r, _ in out):   # .py and .json only here
        raise Refused(MALFORMED, "file_type")
    if m.get("provides") != expected_provides(req):    # exactly the requested need: no extra artifact or capability
        raise Refused(RIGID, "provides_not_the_request")
    for a in m["provides"][0]["artifacts"]:
        if policy.classify(a["type"], a["ref"])[0] != "plain":
            raise Refused(UNPROVEN, "route_to_human")
    for p in m.get("parameters") or []:
        if not isinstance(p, dict) or p.get("type") in policy.MONEY_FIELD_TYPES or p.get("affectsLedgerOrTax"):
            raise Refused(RIGID, "route_to_human", hits=["parameter"])
        f = {"name": p.get("id", ""), "type": PARAM_TYPES.get(p.get("type"), str(p.get("type"))),
             "options": p.get("enumValues")}
        if policy.field_verdict(set(), f)[0] != "plain":
            raise Refused(RIGID, "route_to_human", hits=[f"parameter:{f['name']}"])
    paths = {r for r, _ in out}
    tests = m.get("tests")
    if not isinstance(tests, list) or not tests or any(
            not isinstance(t, dict) or t.get("path") not in paths or not str(t.get("path")).startswith("tests/")
            for t in tests):
        raise Refused(MALFORMED, "tests")
    for rel, content in out:
        if rel.casefold().endswith(".json"):
            _json_fields(rel, content)
    _deny(RIGID, *_strings(m), *(c for _, c in out), *paths)
    manifest = dict(m, id=req["component_id"], kind="configurable", requires=[], owner={"github": owner},
                    tests=[dict(t, blocking=True) for t in tests],
                    **({"i18n": dict(m["i18n"], rtlVerified=False)} if isinstance(m.get("i18n"), dict) else {}), licence={"spdx": "LicenseRef-Proprietary"},
                    origin={"source": "component_factory", "requestId": req["request_id"]},
                    dataHandling={"storesPersonalData": False, "sendsDataToModels": False,
                                  "promotableToLibrary": False},
                    certification={"level": "draft", "touchesLedgerOrTax": False, "reviewedBy": []})
    _, issues = admit([RawManifest("manifest.json", manifest)])
    if any(i.is_error for i in issues):
        raise Refused(MANIFEST, "admission:" + ",".join(sorted({i.code for i in issues if i.is_error})))
    return manifest, out


@dataclass
class Drafter:
    """`port` implements contracts/model-call.md (`complete(request) -> reply`, raises on refusal). `principal` is the
    verified identity the port also holds; the body `caller` only mirrors it. Q-600: only a human platform-staff
    principal may draft (`realm` from the verified identity claims, Realm.STAFF, `mfa_satisfied` True from the same
    claims, and `actor_kind` user); anything else,
    a tenant admin or a principal with no realm included, is refused before any model call. `audit` receives one record per outcome;
    if it raises, no draft is kept. Candidate tests are never run here (no OS sandbox before INF-014)."""
    port: object
    principal: dict
    sandbox_root: Path
    owner: str
    audit: object

    def draft(self, req, now: str) -> Outcome:
        rec = {"type": "factory.draft", "at": now, "request_sha256": None, "request_id": None, "component_id": None,
               "tenant_id": None, "requester": None, "owner": self.owner, "call_id": None, "model": None,
               "manifest_sha256": None, "files_sha256": None, "sandbox": None, "hits": [], "draft_dir": None,
               "reviewed": False, "promotable": False,
               "promotion": "manual only: a named reviewer who is not the requester (ADR-0034)"}
        tmp = placed = None
        try:
            rec.update(tenant_id=self.principal["tenant_id"], requester=self.principal["actor_id"])
            if self.principal.get("realm") != STAFF_REALM or self.principal.get("actor_kind") != "user" \
                    or self.principal.get("mfa_satisfied") is not True:     # as the flag and review-queue staff gates
                raise Refused(NOT_STAFF, "platform_staff_only")
            rec["request_sha256"] = _sha(req)
            if isinstance(req, dict):
                rec.update(request_id=req.get("request_id"), component_id=req.get("component_id"))
            check_request(req)
            root = self._root()
            final = root / f"{req['request_id']}-{rec['request_sha256'][:8]}"
            if os.path.lexists(final):                 # before the model call: no spend on a duplicate
                raise Refused(SANDBOX, "draft_exists")
            reply = self._call(req, rec)
            manifest, files = check_draft(req, reply["text"], self.owner)
            rec.update(manifest_sha256=_sha(manifest), files_sha256=_sha(sorted(
                [r, hashlib.sha256(c.encode("utf-8")).hexdigest()] for r, c in files)))
            tmp = self._write(root, final.name, manifest, files)
            rep = check(tmp / "component", run_tests=True, trusted_source=False)   # static only: FAC-012 expected
            errors = sorted({f.code for f in rep.findings if f.is_error})
            rec["sandbox"] = {"levelReached": rep.level_reached, "testsRun": rep.tests_run,
                              "findings": sorted({f.code for f in rep.findings})}
            if rep.level_reached != "draft" or errors != ["FAC-012"]:
                raise Refused(CHECK_FAILED, "sandbox_check:" + ",".join(errors))
            rec.update(outcome="drafted", status="draft", code=None, reason=None, draft_dir=str(final))
            (tmp / "draft.json").write_text(json.dumps(rec, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
            try:
                os.mkdir(final)                        # atomic reservation: refused if anything is already there
            except FileExistsError:
                raise Refused(SANDBOX, "draft_exists")
            placed = final
            os.rename(tmp / "component", final / "component")
            os.rename(tmp / "draft.json", final / "draft.json")
            os.rmdir(tmp)
            tmp = None
            self.audit(copy.deepcopy(rec))             # `drafted` only after the rename; a failing sink removes it
            placed = None
            return Outcome("drafted", None, None, rec, final)
        except Refused as exc:
            rec.update(outcome=exc.status, status=exc.status, code=exc.code, reason=exc.reason, hits=exc.hits,
                       draft_dir=None)
        except Exception as exc:                       # fail closed: any crash is a refusal with an audit record
            rec.update(outcome="refused", status="refused", code=INTERNAL, reason=type(exc).__name__, draft_dir=None)
        finally:
            for d in (tmp, placed):
                if d is not None:
                    shutil.rmtree(d, ignore_errors=True)
        self.audit(copy.deepcopy(rec))
        return Outcome(rec["outcome"], rec["code"], rec["reason"], rec)

    def _root(self) -> Path:
        root = Path(self.sandbox_root)
        if root.is_symlink() or not root.is_dir():
            raise Refused(SANDBOX, "sandbox_root_missing")
        r = root.resolve()
        if r == REPO or REPO in r.parents:          # never components/, the library or anywhere in the repo
            raise Refused(SANDBOX, "sandbox_root_in_repo")
        for d in r.glob(".tmp-*"):                  # leftovers of a crashed run
            st = os.lstat(d)
            if stat.S_ISDIR(st.st_mode) and time.time() - st.st_mtime > STALE_TMP_SECONDS:
                shutil.rmtree(d, ignore_errors=True)
        return r

    def _call(self, req: dict, rec: dict) -> dict:
        p, key = self.principal, f"factory:{req['request_id']}:{rec['request_sha256'][:16]}"
        rec["call_id"] = key
        caller = {k: p[k] for k in ("tenant_id", "actor_kind", "actor_id", "session_id", "on_behalf_of", "agent_id",
                                    "run_id", "thread_id") if p.get(k) is not None}
        body = {"kind": "request", "contract_version": "0.2.1", "call_id": key, "idempotency_key": key,
                "caller": dict(caller, correlation_id=req["request_id"], role_ids=list(p.get("role_ids", []))),
                "tier": TIER, "purpose": PURPOSE, "prompt_version": PROMPT_VERSION,
                "blocks": [{"content_id": PROMPT_BLOCK, "trust": "platform", "data_class": "C0"},
                           {"content_id": "request", "trust": "untrusted", "role": "user", "turn": 0, "data_class": "C1",
                            "source": f"factory_request:{req['request_id']}", "text": json.dumps(req, ensure_ascii=False)}],
                "max_output_tokens": MAX_OUT, "min_output_tokens": MIN_OUT, "accepts_untrusted": True,
                "thread_tainted": True, "locale": req["locale"], "metadata": {"feature": "factory.draft"}}
        try:
            reply = self.port.complete(body)
        except Exception as exc:                    # any port failure is a refusal: fail closed
            raise Refused(MODEL_REFUSED, f"{getattr(exc, 'code', 'port_error')}:{getattr(exc, 'reason', '')}",
                          "model_refused")
        if not isinstance(reply, dict):
            raise Refused(MALFORMED, "incomplete_reply")
        rec["model"] = {"tier": reply.get("tier"), "prompt_version": PROMPT_VERSION, "call_id": key,
                        "meter_event_id": reply.get("meter_event_id")}   # model id: in the meter event, by design
        if reply.get("kind") != "reply" or reply.get("stop_reason") != "end" or not isinstance(reply.get("text"), str):
            raise Refused(MALFORMED, "incomplete_reply")
        if reply.get("tier") != TIER or not isinstance(reply.get("meter_event_id"), str) or not reply["meter_event_id"]:
            raise Refused(MALFORMED, "untraceable_reply")
        return reply

    def _write(self, root: Path, name: str, manifest: dict, files: list) -> Path:
        tmp = root / f".tmp-{name}-{secrets.token_hex(6)}"
        comp = tmp / "component"
        comp.mkdir(parents=True, exist_ok=False)
        try:
            comp = comp.resolve()
            for rel, content in [("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"), *files]:
                target = (comp / rel).resolve()
                if comp not in target.parents:      # belt and braces after check_relpath and _layout
                    raise Refused(OUTSIDE, "path_outside_sandbox")
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "x", encoding="utf-8") as fh:
                    fh.write(content)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        return tmp
