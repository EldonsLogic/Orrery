"""AI drafting of a candidate component into the factory sandbox (BPL-017, first slice; ADR-0065 Proposed).

The model only drafts; this module decides. Deterministic around one model call made through the model-call port
(contracts/model-call.md, PLT-026). The request is untrusted data: it travels only as an `untrusted` block, the
instructions are a platform block by reference, and a rigid-zone or injection hit refuses it before any call.
The draft is never trusted either: closed shape, fixed fields set here, rigid-zone scan, manifest admission, then
written only under the caller's sandbox root (never into components/ or the library) and checked by the BPL-015
runner. Nothing is promoted: the record says draft and unreviewed; promotion needs a named reviewer who is not the
requester (ADR-0034). Every outcome is one audit record.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

from component_request import policy
from component_request.text import injection, scope_hits, stems, tokens
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
MODEL_KEYS = {"version", "name", "description", "provides", "parameters", "tests", "engineCompatibility", "i18n",
              "dataHandling"}
RIGID_CLASSES = {"stock", "ledger", "tax", "permission"}
# Auth and tenancy words (ledger, tax, e-invoicing, payroll and audit come from scope_hits). Secondary deny list:
# a hit refuses, a miss proves nothing; the structural checks (artifact types, risk class, admission) still run.
AUTH_TOKENS = {"auth", "authentication", "authorization", "authorisation", "login", "logout", "password", "permission",
               "role", "tenant", "tenancy", "session", "sso", "mfa", "otp", "oauth", "jwt", "credential", "token"}
AUTH_AR = ("صلاحي", "مستاجر", "الدخول", "كلمهالمرور")

INVALID, INJECTION, RIGID, UNPROVEN, MODEL_REFUSED = "FDR-001", "FDR-002", "FDR-003", "FDR-004", "FDR-005"
MALFORMED, OUTSIDE, MANIFEST, SANDBOX = "FDR-006", "FDR-007", "FDR-008", "FDR-009"


class Refused(Exception):
    def __init__(self, code: str, reason: str, status: str = "refused"):
        super().__init__(f"{code}:{reason}")
        self.code, self.reason, self.status = code, reason, status


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
    """Ledger, tax, e-invoicing, payroll, audit, auth or tenancy words. Deterministic; never the model's judgement."""
    hits = set(scope_hits(*texts))
    for t in texts:
        toks = tokens(t)
        hits.update(s for w in toks for s in stems(w) if s in AUTH_TOKENS)
        hits.update(a for a in AUTH_AR if a in "".join(toks))
    return sorted(hits)


def check_request(req) -> None:
    if not isinstance(req, dict) or next(REQUEST_SCHEMA.iter_errors(req), None) is not None:
        raise Refused(INVALID, "schema")
    text = [req["title"], req["description"]]
    if any(injection(t) for t in text):
        raise Refused(INJECTION, "instruction_like_text")
    ids = [req["component_id"], req["need"]["ref"]]
    if rigid_hits(*text, *ids) or any(policy.identifier_hits(i) for i in ids):
        raise Refused(RIGID, "route_to_human")
    if policy.classify(req["need"]["kind"], req["need"]["ref"])[0] != "plain":
        raise Refused(UNPROVEN, "route_to_human")


def check_draft(req: dict, text: str, owner: str) -> tuple[dict, list]:
    """-> (manifest with fixed fields, [(relpath, content)]). Raises Refused; never repairs a draft."""
    try:
        d = json.loads(text)
    except (TypeError, ValueError):
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
        if rel in ("manifest.json", "draft.json") or rel in {r for r, _ in out}:
            raise Refused(MALFORMED, "reserved_or_duplicate_path")
        size += len(f["content"].encode("utf-8"))
        out.append((rel, f["content"]))
    if size > MAX_BYTES:
        raise Refused(MALFORMED, "too_big")
    for p in m.get("provides") or []:
        for a in (p.get("artifacts") or []) if isinstance(p, dict) else []:
            if not isinstance(a, dict) or a.get("type") not in policy.ALLOWED_ARTIFACTS or \
                    a.get("riskClass", "plain") in RIGID_CLASSES:
                raise Refused(RIGID, "route_to_human")
            if policy.identifier_hits(str(a.get("ref", ""))) or policy.identifier_hits(str(p.get("capability", ""))):
                raise Refused(RIGID, "route_to_human")
    if rigid_hits(*_strings(m), *(c for _, c in out)):
        raise Refused(RIGID, "route_to_human")
    manifest = dict(m, id=req["component_id"], kind="configurable", requires=[], owner={"github": owner},
                    licence={"spdx": "LicenseRef-Proprietary"},
                    origin={"source": "component_factory", "requestId": req["request_id"]},
                    certification={"level": "draft", "touchesLedgerOrTax": False, "reviewedBy": []})
    _, issues = admit([RawManifest("manifest.json", manifest)])
    if any(i.is_error for i in issues):
        raise Refused(MANIFEST, "admission:" + ",".join(sorted({i.code for i in issues if i.is_error})))
    return manifest, out


@dataclass
class Drafter:
    """`port` implements contracts/model-call.md (`complete(request) -> reply`, raises on refusal). `principal` is the
    verified identity the port also holds; the body `caller` only mirrors it. `audit` receives one record per draft.
    `run_candidate_tests` stays False wherever requests come from customers until the OS sandbox (INF-014) exists."""
    port: object
    principal: dict
    sandbox_root: Path
    owner: str
    audit: object
    run_candidate_tests: bool = False

    def draft(self, req, now: str) -> Outcome:
        rec = {"type": "factory.draft", "at": now, "request_sha256": _sha(req), "requester": self.principal["actor_id"],
               "request_id": req.get("request_id") if isinstance(req, dict) else None, "model": None,
               "sandbox": None, "status": "draft", "reviewed": False, "promotable": False,
               "promotion": "manual only: a named reviewer who is not the requester (ADR-0034)"}
        try:
            check_request(req)
            root = self._root()
            reply = self._call(req, rec)
            manifest, files = check_draft(req, reply["text"], self.owner)
            out_dir = self._write(root, req, manifest, files)
            rep = check(out_dir / "component", run_tests=True, trusted_source=self.run_candidate_tests)
            rec["sandbox"] = {"levelReached": rep.level_reached, "testsRun": rep.tests_run,
                              "testsPassed": rep.tests_run and all(t["passed"] for t in rep.tests),
                              "findings": sorted({f.code for f in rep.findings})}
            rec.update(outcome="drafted", code=None, reason=None, draft_dir=str(out_dir))
            (out_dir / "draft.json").write_text(json.dumps(rec, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                                                encoding="utf-8")
            result = Outcome("drafted", None, None, rec, out_dir)
        except Refused as exc:
            rec.update(outcome=exc.status, code=exc.code, reason=exc.reason, draft_dir=None)
            result = Outcome(exc.status, exc.code, exc.reason, rec)
        self.audit(rec)
        return result

    def _root(self) -> Path:
        root = Path(self.sandbox_root)
        if root.is_symlink() or not root.is_dir():
            raise Refused(SANDBOX, "sandbox_root_missing")
        r = root.resolve()
        if r == REPO or REPO in r.parents:          # never components/, the library or anywhere in the repo
            raise Refused(SANDBOX, "sandbox_root_in_repo")
        return r

    def _call(self, req: dict, rec: dict) -> dict:
        p, key = self.principal, f"factory:{req['request_id']}:{_sha(req)[:16]}"
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
        rec["model"] = {"tier": reply.get("tier"), "prompt_version": PROMPT_VERSION, "call_id": key,
                        "meter_event_id": reply.get("meter_event_id")}   # model id: in the meter event, by design
        if reply.get("kind") != "reply" or reply.get("stop_reason") != "end" or not isinstance(reply.get("text"), str):
            raise Refused(MALFORMED, "incomplete_reply")
        return reply

    def _write(self, root: Path, req: dict, manifest: dict, files: list) -> Path:
        out = root / f"{req['request_id']}-{_sha(req)[:8]}"
        try:
            (out / "component").mkdir(parents=True, exist_ok=False)
        except OSError:
            raise Refused(SANDBOX, "draft_exists")
        comp = (out / "component").resolve()
        for rel, content in [("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"), *files]:
            target = (comp / rel).resolve()
            if comp not in target.parents:          # belt and braces after check_relpath
                raise Refused(OUTSIDE, "path_outside_sandbox")
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "x", encoding="utf-8") as fh:
                fh.write(content)
        return out
