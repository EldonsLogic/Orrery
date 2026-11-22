"""SEC-022 / BPL-032 review follow-ups 2 (ADR-0051), from the two reviews of merged PR #252.

1. Identifier checks refuse a trailing newline (`$` matches before a final "\\n"; `.match` is not `fullmatch`).
2. The in-memory adapter and the offline engine-backed adapter plan own-entity role grants the same way.
Synthetic data only.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

from change_engine.adapter import ChangeEngineAdapter, FrappeRuntimeBackend, FrappeSiteResolver
from change_engine.adapter import contracts_support as cs
from change_engine.adapter.mapping import _DECIMAL_ADD_RE, entity_to_doctype, is_protected_entity
from change_engine.guarded_apply.safety_guardrails import (
    VALID_FIELDNAME_RE,
    ZONE_2_LOCKED_DOCTYPES,
    ZoneSafetyViolation,
    validate_mutation_safety,
)
from change_engine.tests.ci_engine_fake import CaseInsensitiveEngine

TENANT = "t_sec022f2"
SITE = "ci.localhost"
ULID = "01J00000000000000000000024"


def _ctx(**over: object) -> dict:
    ctx = {
        "contractVersion": "0.1.2", "requestId": ULID, "correlationId": "corr_sec022_f2", "tenantId": TENANT,
        "caller": {"service": "control_plane", "onBehalfOf": {"kind": "user", "id": "usr_owner"}}, "deadlineMs": 120000,
    }
    ctx.update(over)
    return ctx


def _support_ctx(grant: str) -> dict:
    return _ctx(caller={"service": "control_plane",
                        "onBehalfOf": {"kind": "support", "id": "usr_support", "supportGrantId": grant}})


class TestTrailingNewlineIdentifiers(unittest.TestCase):
    """Item 1: every identifier check in the envelope context and the field-name guard is a full match."""

    CASES = (
        ("tenantId", "t_abcd\n", "/context/tenantId"),
        ("requestId", ULID + "\n", "/context/requestId"),
        ("correlationId", "corr_x\n", "/context/correlationId"),
        ("contractVersion", "0.1.2\n", "/context/contractVersion"),
    )

    def _both_paths(self):
        """Run with the schema validator and with the pure-Python fallback (no schema registry available)."""
        yield "schema", mock.patch.object(cs, "_validator_for", wraps=cs._validator_for)
        yield "fallback", mock.patch.object(cs, "_validator_for", return_value=None)

    def test_clean_context_is_accepted_on_both_paths(self) -> None:
        for name, patcher in self._both_paths():
            with self.subTest(path=name), patcher:
                self.assertEqual(cs.validate_context(_ctx()), [])
                self.assertEqual(cs.validate_context(_support_ctx("grant_12345678")), [])

    def test_context_fields_refuse_trailing_newline(self) -> None:
        for name, patcher in self._both_paths():
            for key, value, pointer in self.CASES:
                with self.subTest(path=name, field=key), patcher:
                    self.assertIn(pointer, cs.validate_context(_ctx(**{key: value})))

    def test_support_grant_id_refuses_trailing_newline(self) -> None:
        for name, patcher in self._both_paths():
            with self.subTest(path=name), patcher:
                bad = cs.validate_context(_support_ctx("grant_12345678\n"))
                self.assertTrue(any(p.startswith("/context/caller/onBehalfOf") for p in bad), bad)

    def test_provision_site_refuses_tenant_with_trailing_newline(self) -> None:
        with mock.patch.dict(os.environ, {"CHANGE_ENGINE_ENV": "test"}):
            adapter = ChangeEngineAdapter(test_hooks=False, environment="test")
            body = {"idempotencyKey": "idemp_sec022_f2_prov", "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
                    "blueprintId": "bp-f2", "siteClass": "sandbox", "countryPack": "sa"}
            refused = adapter.call("provision_site", _ctx(tenantId="t_abcd\n"), body)
            self.assertFalse(refused["ok"], refused)
            ok = adapter.call("provision_site", _ctx(tenantId="t_abcd"), body)
            self.assertTrue(ok["ok"], ok)

    def test_custom_fieldname_guard_refuses_trailing_newline(self) -> None:
        self.assertIsNone(VALID_FIELDNAME_RE.fullmatch("custom_abc\n"))
        self.assertIsNotNone(VALID_FIELDNAME_RE.fullmatch("custom_abc"))
        for fieldname in ("custom_abc\n", "custom_abc\n\n"):
            with self.subTest(fieldname=fieldname), self.assertRaises(ZoneSafetyViolation):
                validate_mutation_safety({
                    "intent": "add_custom_fields", "target_doctype": "Sales Order", "user_roles": ["Finance Director"],
                    "changes": [{"fieldname": fieldname, "fieldtype": "Data", "label": "Abc"}],
                })

    def test_decimal_add_statement_pattern_refuses_trailing_newline(self) -> None:
        stmt = "ALTER TABLE `tabWidget` ADD COLUMN `custom_cost` decimal(21,9) not null default 0"
        self.assertTrue(_DECIMAL_ADD_RE.match(stmt))
        self.assertIsNone(_DECIMAL_ADD_RE.match(stmt + "\n"))


def _artifact(steps: list[dict], *, base: dict | None = None, target: dict | None = None, inverse: dict | None = None) -> dict:
    counts = dict.fromkeys(("cosmetic", "config", "data_shape", "destructive", "compliance", "access", "branding"), 0)
    for s in steps:
        counts[s["impact"]] += 1
    art = {"artifactSchema": "0.1.0", "kind": "forward", "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
           "blueprint": {"id": "bp-f2", "base": base,
                         "target": target or {"hash": "sha256:" + "5" * 64, "revision": 1},
                         "diffHash": ("sha256:" + "7" * 64) if base else None},
           "engineTarget": {"adapter": "frappe", "versionSet": "set-example"}, "components": [], "steps": steps,
           "skippedOps": [], "postConditions": [],
           "risk": {"counts": counts, "total": len(steps), "maxImpact": "access", "needsDdlPlanGate": True,
                    "touchesCompliance": False, "touchesAccess": counts["access"] > 0, "touchesLedgerOrTax": False,
                    "requiresTeamReview": False, "irreversibleSteps": 0},
           "inverse": inverse}
    digest, art_id = cs.artifact_hashes(art)
    art.update(artifactId=art_id, integrity={"algorithm": "sha256-canonical-json-v1", "contentHash": digest, "signature": None})
    return art


def _inverse_for(base: dict, target: dict, steps: list[dict]) -> dict:
    counts = dict.fromkeys(("cosmetic", "config", "data_shape", "destructive", "compliance", "access", "branding"), 0)
    for s in steps:
        counts[s["impact"]] += 1
    inv = {"artifactSchema": "0.1.0", "kind": "inverse", "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
           "blueprint": {"id": "bp-f2", "base": target, "target": base, "diffHash": "sha256:" + "8" * 64},
           "engineTarget": {"adapter": "frappe", "versionSet": "set-example"}, "components": [], "steps": steps,
           "skippedOps": [], "postConditions": [],
           "risk": {"counts": counts, "total": len(steps), "maxImpact": "destructive", "needsDdlPlanGate": False,
                    "touchesCompliance": False, "touchesAccess": False, "touchesLedgerOrTax": False,
                    "requiresTeamReview": False, "irreversibleSteps": 0},
           "inverse": None}
    digest, art_id = cs.artifact_hashes(inv)
    inv.update(artifactId=art_id, integrity={"algorithm": "sha256-canonical-json-v1", "contentHash": digest, "signature": None})
    return inv


def _entity(seq: int, eid: str, *, subject_id: str | None = None) -> dict:
    sid = eid if subject_id is None else subject_id
    return {"seq": seq, "phase": 4, "kind": "entity.add", "subject": {"kind": "entity", "id": sid, "parents": []},
            "pointer": f"/entities/{eid}", "impact": "data_shape", "ddlImpact": "additive", "reversible": True,
            "params": {"definition": {"id": eid, "labels": {"en": eid, "ar": eid}, "fields": [], "relations": []}},
            "sourceOps": [f"/entities/{eid}"]}


def _entity_quarantine(seq: int, eid: str) -> dict:
    return {"seq": seq, "phase": 16, "kind": "entity.quarantine", "subject": {"kind": "entity", "id": eid, "parents": []},
            "pointer": f"/entities/{eid}", "impact": "destructive", "ddlImpact": "none", "reversible": True,
            "params": {"definition": {"id": eid, "labels": {"en": eid, "ar": eid}, "fields": []}},
            "sourceOps": [f"/entities/{eid}"]}


def _field_step(
    seq: int,
    pointer_entity: str,
    fid: str,
    *,
    parent_entity: str | None = None,
    parents: list[dict] | None = None,
    kind: str = "field.add",
) -> dict:
    ps = [{"kind": "entity", "id": pointer_entity if parent_entity is None else parent_entity}] if parents is None else parents
    pointer = f"/entities/{pointer_entity}/fields" if kind == "field.reorder" else f"/entities/{pointer_entity}/fields/{fid}"
    if kind == "field.add":
        phase, impact, ddl = 5, "data_shape", "additive"
        params = {"definition": {"id": fid, "type": "string", "labels": {"en": fid, "ar": fid}}}
    elif kind == "field.set_property":
        phase, impact, ddl = 6, "cosmetic", "none"
        params = {"property": "/readOnly", "before": False, "after": True}
    elif kind == "field.reorder":
        phase, impact, ddl = 6, "cosmetic", "none"
        params = {"order": [fid], "previousOrder": [fid]}
    else:  # field.quarantine
        phase, impact, ddl = 15, "destructive", "none"
        params = {"definition": {"id": fid, "type": "string", "labels": {"en": fid, "ar": fid}}}
    return {"seq": seq, "phase": phase, "kind": kind, "subject": {"kind": "field", "id": fid, "parents": ps},
            "pointer": pointer, "impact": impact, "ddlImpact": ddl, "reversible": True,
            "params": params, "sourceOps": [pointer]}


def _relation_step(
    seq: int,
    pointer_entity: str,
    rid: str,
    *,
    parent_entity: str | None = None,
    parents: list[dict] | None = None,
    kind: str = "relation.add",
) -> dict:
    ps = [{"kind": "entity", "id": pointer_entity if parent_entity is None else parent_entity}] if parents is None else parents
    pointer = f"/entities/{pointer_entity}/relations/{rid}"
    if kind == "relation.add":
        phase, impact, ddl = 5, "data_shape", "additive"
        params = {"definition": {"id": rid, "target": "item", "kind": "many_to_one", "labels": {"en": rid, "ar": rid}}}
    elif kind == "relation.set_property":
        phase, impact, ddl = 6, "cosmetic", "none"
        params = {"property": "/labels/en", "before": rid, "after": rid + "2"}
    else:  # relation.quarantine
        phase, impact, ddl = 15, "destructive", "none"
        params = {"definition": {"id": rid, "target": "item", "kind": "many_to_one", "labels": {"en": rid, "ar": rid}}}
    return {"seq": seq, "phase": phase, "kind": kind, "subject": {"kind": "relation", "id": rid, "parents": ps},
            "pointer": pointer, "impact": impact, "ddlImpact": ddl, "reversible": True,
            "params": params, "sourceOps": [pointer]}


_OMIT = object()


def _workflow(seq: int, wid: str, entity: object = "sales_order") -> dict:
    defn: dict = {
        "id": wid, "labels": {"en": wid, "ar": wid},
        "states": [
            {"id": "draft", "kind": "initial", "labels": {"en": "Draft", "ar": "مسودة"}},
            {"id": "done", "kind": "final", "labels": {"en": "Done", "ar": "تم"}},
        ],
        "transitions": [{"id": "t_done", "from": "draft", "to": "done", "allowedRoles": ["sales_rep"]}],
    }
    if entity is not _OMIT:
        defn["entity"] = entity
    return {"seq": seq, "phase": 8, "kind": "workflow.upsert", "subject": {"kind": "workflow", "id": wid, "parents": []},
            "pointer": f"/workflows/{wid}", "impact": "config", "ddlImpact": "none", "reversible": True,
            "params": {"definition": defn}, "sourceOps": [f"/workflows/{wid}"]}


def _report(seq: int, rid: str, entity: object = _OMIT) -> dict:
    defn: dict = {
        "id": rid, "kind": "report", "labels": {"en": rid, "ar": rid},
        "metrics": [{"ref": "order_count"}], "visibleToRoles": ["sales_rep"],
    }
    if entity is not _OMIT:
        defn["entity"] = entity
    return {"seq": seq, "phase": 10, "kind": "report.upsert", "subject": {"kind": "report", "id": rid, "parents": []},
            "pointer": f"/reports/{rid}", "impact": "config", "ddlImpact": "none", "reversible": True,
            "params": {"definition": defn}, "sourceOps": [f"/reports/{rid}"]}


def _role(seq: int, rid: str, entity: str) -> dict:
    defn = {"id": rid, "labels": {"en": rid, "ar": rid}, "scope": {"type": "company"},
            "permissions": [{"entity": entity, "actions": ["read"]}]}
    return {"seq": seq, "phase": 7, "kind": "role.upsert", "subject": {"kind": "role", "id": rid, "parents": []},
            "pointer": f"/roles/{rid}", "impact": "access", "ddlImpact": "none", "reversible": True,
            "params": {"definition": defn}, "sourceOps": [f"/roles/{rid}"]}


class TestOwnEntityGrantsAgreeAcrossBackends(unittest.TestCase):
    """Item 2: a role grant on an entity the same Blueprint creates is allowed on the in-memory adapter and on the
    offline engine-backed adapter alike; an unmapped built-in the Blueprint does not create is refused on both; a
    backend that has an engine but no checker still fails closed."""

    def setUp(self) -> None:
        env = mock.patch.dict(os.environ, {"CHANGE_ENGINE_ENV": "test"})
        env.start()
        self.addCleanup(env.stop)

    def _adapters(self):
        engine = CaseInsensitiveEngine(SITE)
        backend = FrappeRuntimeBackend(site_resolver=FrappeSiteResolver(site_map={TENANT: SITE}),
                                       frappe_factory=lambda: engine, offline_ddl_simulator=True)
        yield "in_memory", ChangeEngineAdapter(test_hooks=False, environment="test")
        yield "offline_engine", ChangeEngineAdapter(test_hooks=False, environment="test", frappe_backend=backend)

    def _plan(self, adapter: ChangeEngineAdapter, steps: list[dict], key: str) -> dict:
        prov = adapter.call("provision_site", _ctx(), {
            "idempotencyKey": key, "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
            "blueprintId": "bp-f2", "siteClass": "sandbox", "countryPack": "sa"})
        self.assertTrue(prov["ok"], prov)
        planned = adapter.call("plan", _ctx(), {"artifact": _artifact(steps)})
        self.assertTrue(planned["ok"], planned)
        return planned["result"]

    def test_own_entity_grant_allowed_and_unmapped_builtin_refused_on_both(self) -> None:
        steps = [
            _entity(1, "widget"),
            _role(2, "r_wid", "widget"),        # own entity of this Blueprint: allowed
            _role(3, "r_sup", "supplier"),      # unmapped built-in, not created here: refused
            _role(4, "r_cust", "customer"),     # reviewed mapped entity: allowed
        ]
        seen = {}
        for name, adapter in self._adapters():
            with self.subTest(adapter=name):
                result = self._plan(adapter, steps, f"idemp_f2_{name}")
                got = {s["seq"]: (s["disposition"], s.get("reasonCode")) for s in result["steps"]}
                seen[name] = got
                self.assertEqual(got[2][0], "gated", result)
                self.assertEqual(got[3], ("blocked", "protected_subject"), result)
                self.assertEqual(got[4][0], "gated", result)
                self.assertEqual(result["verdict"], "rejected")
        self.assertEqual(seen["in_memory"], seen["offline_engine"])

    def test_own_entity_grant_alone_needs_gate_approval_on_both(self) -> None:
        steps = [_entity(1, "widget"), _role(2, "r_wid", "widget")]
        for name, adapter in self._adapters():
            with self.subTest(adapter=name):
                result = self._plan(adapter, steps, f"idemp_f2_only_{name}")
                self.assertEqual(result["verdict"], "needs_gate_approval", result)

    def test_protected_own_entity_stays_refused_in_memory(self) -> None:
        steps = [_entity(1, "journal_entry"), _role(2, "r_je", "journal_entry")]
        for name, adapter in self._adapters():
            with self.subTest(adapter=name):
                result = self._plan(adapter, steps, f"idemp_f2_prot_{name}")
                by_seq = {s["seq"]: (s["disposition"], s.get("reasonCode")) for s in result["steps"]}
                self.assertEqual(by_seq[2], ("blocked", "protected_subject"), result)


class TestProtectedEntityIsCaseInsensitive(unittest.TestCase):
    """Review Low L2 (pre-existing): `gl_entry` derives `Gl Entry`, which the engine (MariaDB collation) treats as
    `GL Entry`; the protected check must not be case-sensitive."""

    def test_gl_entry_spellings_are_protected(self) -> None:
        for eid in ("gl_entry", "GL_ENTRY", "Gl Entry", "GL Entry", "gl-entry"):
            with self.subTest(entity=eid):
                self.assertTrue(is_protected_entity(eid))

    def test_every_zone_2_doctype_is_protected_under_its_derived_spellings(self) -> None:
        checked = 0
        for doctype in ZONE_2_LOCKED_DOCTYPES:
            for eid in (doctype.replace(" ", "_").lower(), doctype.replace(" ", "_").upper(), doctype.replace(" ", "_")):
                if entity_to_doctype(eid).casefold() != doctype.casefold():
                    continue  # derives a different name (e.g. `doc_perm` is `Doc Perm`, not `DocPerm`)
                checked += 1
                with self.subTest(doctype=doctype, entity=eid):
                    self.assertTrue(is_protected_entity(eid))
        self.assertGreater(checked, len(ZONE_2_LOCKED_DOCTYPES))

    def test_mixed_case_acronym_names_are_protected(self) -> None:
        for eid in ("docperm", "DOCPERM", "docshare", "custom_docperm", "Custom_DocPerm"):
            with self.subTest(entity=eid):
                self.assertTrue(is_protected_entity(eid))

    def test_protected_ids_are_case_insensitive(self) -> None:
        for eid in ("general_ledger", "General_Ledger", "AUDIT_LOG", "Tax_Ledger"):
            with self.subTest(entity=eid):
                self.assertTrue(is_protected_entity(eid))

    def test_ordinary_entities_stay_unprotected(self) -> None:
        for eid in ("widget", "customer", "sales_order", "supplier", "payment_entry", "server_script", "has_role"):
            with self.subTest(entity=eid):
                self.assertFalse(is_protected_entity(eid))


class TestCaseVariantLedgerEntityBlockedAtPlanOnBothBackends(TestOwnEntityGrantsAgreeAcrossBackends):
    """L2 at plan time: `entity.add gl_entry` and a grant on it are blocked on the in-memory adapter and on the
    offline engine-backed adapter alike."""

    def test_case_variant_protected_entity_and_grant_blocked(self) -> None:
        for eid in ("gl_entry", "payment_ledger_entry", "docperm"):
            steps = [_entity(1, eid), _role(2, "r_gl", eid)]
            for name, adapter in self._adapters():
                with self.subTest(entity=eid, adapter=name):
                    result = self._plan(adapter, steps, f"idemp_f2_l2_{eid}_{name}")
                    got = {s["seq"]: (s["disposition"], s.get("reasonCode")) for s in result["steps"]}
                    self.assertEqual(got, {1: ("blocked", "protected_subject"), 2: ("blocked", "protected_subject")}, result)
                    self.assertEqual(result["verdict"], "rejected")

    def test_grant_alone_on_case_variant_protected_entity_blocked(self) -> None:
        steps = [_role(1, "r_gl", "gl_entry")]
        for name, adapter in self._adapters():
            with self.subTest(adapter=name):
                result = self._plan(adapter, steps, f"idemp_f2_l2_alone_{name}")
                self.assertEqual(result["steps"][0]["disposition"], "blocked", result)
                self.assertEqual(result["steps"][0].get("reasonCode"), "protected_subject", result)

    # inherited tests of the parent class are not repeated
    test_own_entity_grant_allowed_and_unmapped_builtin_refused_on_both = None
    test_own_entity_grant_alone_needs_gate_approval_on_both = None
    test_protected_own_entity_stays_refused_in_memory = None


WHITESPACE_IDS = ("gl_entry ", " gl_entry", "gl _entry", "GL Entry ", "general_ledger ")
NON_PROTECTED_INVALID_IDS = ("widget ", "widget\n", "Widget", "wid-get")


class TestWhitespaceEntityIdsRefusedAtPlan(TestOwnEntityGrantsAgreeAcrossBackends):
    """Review of e792eb9 (finding 1) and re-review of 2767110 (findings 1-4): entity ids on every plan-time
    entity path must satisfy the Blueprint id grammar `^[a-z][a-z0-9_]{1,63}$` (`unsupported_value_type`),
    must not name a protected entity (`protected_subject`), and must agree between pointer and subject/parent."""

    def _seed_customer(self, adapter: ChangeEngineAdapter, key: str) -> dict:
        prov = adapter.call("provision_site", _ctx(), {
            "idempotencyKey": key, "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
            "blueprintId": "bp-f2", "siteClass": "sandbox", "countryPack": "sa"})
        self.assertTrue(prov["ok"], prov)
        rev1 = {"hash": "sha256:" + "5" * 64, "revision": 1}
        art1 = _artifact([_entity(1, "customer")], target=rev1)
        pl = adapter.call("plan", _ctx(), {"artifact": art1})
        self.assertTrue(pl["ok"] and pl["result"]["verdict"] == "auto_approved", pl)
        ap = adapter.call("apply", _ctx(), {
            "idempotencyKey": key + "_apply", "planToken": pl["result"]["planToken"],
            "artifact": art1, "approvals": {"changeApproved": "01J00000000000000000000010"}})
        self.assertTrue(ap["ok"] and ap["result"]["status"] == "applied", ap)
        return rev1

    def _plan_on_customer(self, adapter: ChangeEngineAdapter, steps: list[dict], key: str) -> dict:
        rev1 = self._seed_customer(adapter, key)
        rev2 = {"hash": "sha256:" + "6" * 64, "revision": 2}
        inv = _inverse_for(rev1, rev2, [_field_step(1, "customer", "note", kind="field.quarantine")])
        art2 = _artifact(steps, base=rev1, target=rev2, inverse=inv)
        planned = adapter.call("plan", _ctx(), {"artifact": art2})
        self.assertTrue(planned["ok"], planned)
        return planned["result"]

    def test_protected_key_is_normalised(self) -> None:
        for eid in WHITESPACE_IDS + ("GL  Entry", "gl__entry", "Gl\tEntry", "gl-entry"):
            with self.subTest(entity=eid):
                self.assertTrue(is_protected_entity(eid))

    def test_ordinary_ids_stay_unprotected(self) -> None:
        for eid in ("customer", "sales_invoice", "delivery_note"):
            self.assertFalse(is_protected_entity(eid))

    def test_whitespace_ids_refused_at_plan_on_both_backends(self) -> None:
        for eid in WHITESPACE_IDS:
            steps = [_entity(1, eid), _role(2, "r_ws", eid)]
            for name, adapter in self._adapters():
                with self.subTest(entity=eid, adapter=name):
                    result = self._plan(adapter, steps, f"idemp_f3_ws_{abs(hash((eid, name)))}")
                    got = {s["seq"]: (s["disposition"], s.get("reasonCode")) for s in result["steps"]}
                    self.assertEqual(
                        got,
                        {1: ("blocked", "unsupported_value_type"), 2: ("blocked", "unsupported_value_type")},
                        result,
                    )
                    self.assertEqual(result["verdict"], "rejected")

    def test_whitespace_entity_alone_and_grant_alone_refused(self) -> None:
        for eid in WHITESPACE_IDS:
            for label, steps in (("entity", [_entity(1, eid)]), ("grant", [_role(1, "r_ws", eid)])):
                for name, adapter in self._adapters():
                    with self.subTest(entity=eid, step=label, adapter=name):
                        result = self._plan(adapter, steps, f"idemp_f3_ws1_{abs(hash((eid, label, name)))}")
                        self.assertEqual(result["steps"][0]["disposition"], "blocked", result)
                        self.assertEqual(result["steps"][0].get("reasonCode"), "unsupported_value_type", result)
                        self.assertEqual(result["verdict"], "rejected")

    def test_non_protected_invalid_ids_refused_with_unsupported_value_type(self) -> None:
        """Finding 3: pin the grammar check with non-protected invalid ids so protected-key checks cannot mask it."""
        for eid in NON_PROTECTED_INVALID_IDS:
            for label, steps in (("entity", [_entity(1, eid)]), ("grant", [_role(1, "r_inv", eid)])):
                for name, adapter in self._adapters():
                    with self.subTest(entity=eid, step=label, adapter=name):
                        result = self._plan(adapter, steps, f"idemp_f3_inv_{abs(hash((eid, label, name)))}")
                        self.assertEqual(result["steps"][0]["disposition"], "blocked", result)
                        self.assertEqual(result["steps"][0].get("reasonCode"), "unsupported_value_type", result)
                        self.assertEqual(result["verdict"], "rejected")

    def test_entity_pointer_and_subject_mismatches_refused(self) -> None:
        """Findings 3 and 4: pointer segment and subject id on entity.add must both pass grammar, be unprotected,
        and agree; non-add entity steps still validate the pointer segment."""
        cases = (
            ("subject_invalid", [_entity(1, "widget", subject_id="widget ")], "unsupported_value_type"),
            ("subject_newline", [_entity(1, "widget", subject_id="widget\n")], "unsupported_value_type"),
            ("pointer_invalid", [_entity(1, "widget ", subject_id="widget")], "unsupported_value_type"),
            ("pointer_newline", [_entity(1, "widget\n", subject_id="widget")], "unsupported_value_type"),
            ("quarantine_pointer_invalid", [_entity_quarantine(1, "widget ")], "unsupported_value_type"),
            ("subject_protected_mismatch", [_entity(1, "widget", subject_id="user")], "protected_subject"),
            ("subject_unprotected_mismatch", [_entity(1, "widget", subject_id="customer")], "definition_conflict"),
        )
        for label, steps, expected_reason in cases:
            for name, adapter in self._adapters():
                with self.subTest(case=label, adapter=name):
                    result = self._plan(adapter, steps, f"idemp_f3_ent_{label}_{name}")
                    self.assertEqual(result["steps"][0]["disposition"], "blocked", result)
                    self.assertEqual(result["steps"][0].get("reasonCode"), expected_reason, result)
                    self.assertEqual(result["verdict"], "rejected")

    def test_field_and_relation_parent_checked_at_plan_on_both_backends(self) -> None:
        """Finding 1: field.* and relation.* steps must match subject.parents[0].id to the pointer segment,
        pass is_valid_entity_id, and not target a protected entity."""
        bad_cases = (
            ("field_add_parent_user", _field_step(1, "customer", "note", parent_entity="user"), "protected_subject"),
            ("field_add_parent_gl_ws", _field_step(1, "customer", "note", parent_entity="gl_entry "), "unsupported_value_type"),
            ("field_add_parent_widget_nl", _field_step(1, "customer", "note", parent_entity="widget\n"), "unsupported_value_type"),
            ("field_add_parent_mismatch", _field_step(1, "customer", "note", parent_entity="item"), "definition_conflict"),
            ("field_add_no_parents", _field_step(1, "customer", "note", parents=[]), "unsupported_value_type"),
            ("field_set_prop_parent_user", _field_step(1, "customer", "note", parent_entity="user", kind="field.set_property"), "protected_subject"),
            ("field_quarantine_parent_gl_ws", _field_step(1, "customer", "note", parent_entity="gl_entry ", kind="field.quarantine"), "unsupported_value_type"),
            ("field_reorder_parent_user", _field_step(1, "customer", "note", parent_entity="user", kind="field.reorder"), "protected_subject"),
            ("relation_add_parent_user", _relation_step(1, "customer", "rel_a", parent_entity="user"), "protected_subject"),
            ("relation_add_parent_gl_ws", _relation_step(1, "customer", "rel_a", parent_entity="gl_entry "), "unsupported_value_type"),
            ("relation_set_prop_parent_user", _relation_step(1, "customer", "rel_a", parent_entity="user", kind="relation.set_property"), "protected_subject"),
            ("relation_quarantine_parent_mismatch", _relation_step(1, "customer", "rel_a", parent_entity="item", kind="relation.quarantine"), "definition_conflict"),
        )
        for label, step, expected_reason in bad_cases:
            seen = {}
            for name, adapter in self._adapters():
                with self.subTest(case=label, adapter=name):
                    result = self._plan_on_customer(adapter, [step], f"idemp_f3_par_{label}_{name}")
                    got = (result["steps"][0]["disposition"], result["steps"][0].get("reasonCode"), result["verdict"])
                    seen[name] = got
                    self.assertEqual(got, ("blocked", expected_reason, "rejected"), result)
            if len(seen) == 2:
                self.assertEqual(seen["in_memory"], seen["offline_engine"])

        # Control: matching valid unprotected parent plans ok on both adapters
        for label, step in (
            ("field_add_ok", _field_step(1, "customer", "note")),
            ("relation_add_ok", _relation_step(1, "customer", "rel_a")),
        ):
            for name, adapter in self._adapters():
                with self.subTest(case=label, adapter=name):
                    result = self._plan_on_customer(adapter, [step], f"idemp_f3_parok_{label}_{name}")
                    self.assertEqual(result["steps"][0]["disposition"], "ok", result)
                    self.assertEqual(result["verdict"], "auto_approved", result)

    def test_field_and_relation_parent_refusal_writes_nothing_to_engine(self) -> None:
        for label, step in (
            ("field_user", _field_step(1, "customer", "note", parent_entity="user")),
            ("field_gl_ws", _field_step(1, "customer", "note", parent_entity="gl_entry ")),
            ("relation_user", _relation_step(1, "customer", "rel_a", parent_entity="user")),
            ("relation_gl_ws", _relation_step(1, "customer", "rel_a", parent_entity="gl_entry ")),
        ):
            engine = CaseInsensitiveEngine(SITE)
            backend = FrappeRuntimeBackend(site_resolver=FrappeSiteResolver(site_map={TENANT: SITE}),
                                           frappe_factory=lambda e=engine: e, offline_ddl_simulator=True)
            adapter = ChangeEngineAdapter(test_hooks=False, environment="test", frappe_backend=backend)
            rev1 = self._seed_customer(adapter, f"idemp_f3_pw_{label}")
            before = repr(engine.ensure_site(SITE).rows)
            rev2 = {"hash": "sha256:" + "6" * 64, "revision": 2}
            inv = _inverse_for(rev1, rev2, [_field_step(1, "customer", "note", kind="field.quarantine")])
            art2 = _artifact([step], base=rev1, target=rev2, inverse=inv)
            with self.subTest(case=label):
                planned = adapter.call("plan", _ctx(), {"artifact": art2})
                self.assertTrue(planned["ok"], planned)
                self.assertEqual(planned["result"]["verdict"], "rejected", planned)
                self.assertEqual(repr(engine.ensure_site(SITE).rows), before)

    def test_workflow_and_report_definition_entity_checked_at_plan(self) -> None:
        """Finding 2: workflow.upsert and report.upsert check definition.entity against is_valid_entity_id
        and is_protected_entity at plan time."""
        bad_entities = (
            ("gl_entry", "protected_subject"),
            ("gl_entry ", "unsupported_value_type"),
            ("user", "protected_subject"),
            ("GL Entry", "unsupported_value_type"),
            ("widget\n", "unsupported_value_type"),
        )
        for kind_name, builder in (("workflow", _workflow), ("report", _report)):
            for eid, expected_reason in bad_entities:
                seen = {}
                for name, adapter in self._adapters():
                    with self.subTest(kind=kind_name, entity=eid, adapter=name):
                        result = self._plan(adapter, [builder(1, "x_bad", eid)], f"idemp_f3_def_{kind_name}_{abs(hash((eid, name)))}")
                        got = (result["steps"][0]["disposition"], result["steps"][0].get("reasonCode"), result["verdict"])
                        seen[name] = got
                        self.assertEqual(got, ("blocked", expected_reason, "rejected"), result)
                if len(seen) == 2:
                    self.assertEqual(seen["in_memory"], seen["offline_engine"])

        # Workflow requires definition.entity; report allows omitting it (optional in Blueprint schema)
        for name, adapter in self._adapters():
            with self.subTest(case="workflow_missing_entity", adapter=name):
                result = self._plan(adapter, [_workflow(1, "wf_no_ent", _OMIT)], f"idemp_f3_wf_noent_{name}")
                self.assertEqual(result["steps"][0]["disposition"], "blocked", result)
                self.assertEqual(result["steps"][0].get("reasonCode"), "unsupported_value_type", result)
            with self.subTest(case="workflow_valid_entity", adapter=name):
                result = self._plan(adapter, [_workflow(1, "wf_ok", "sales_order")], f"idemp_f3_wf_ok_{name}")
                self.assertEqual(result["steps"][0]["disposition"], "ok", result)
            with self.subTest(case="report_valid_entity", adapter=name):
                result = self._plan(adapter, [_report(1, "rep_ok", "sales_order")], f"idemp_f3_rep_ok_{name}")
                self.assertEqual(result["steps"][0]["disposition"], "ok", result)
            with self.subTest(case="report_omitted_entity", adapter=name):
                result = self._plan(adapter, [_report(1, "rep_no_ent")], f"idemp_f3_rep_noent_{name}")
                self.assertEqual(result["steps"][0]["disposition"], "ok", result)

    def test_workflow_and_report_refusal_writes_nothing_to_engine(self) -> None:
        for kind_name, builder in (("workflow", _workflow), ("report", _report)):
            for eid in ("gl_entry", "gl_entry ", "user", "GL Entry", "widget\n"):
                engine = CaseInsensitiveEngine(SITE)
                backend = FrappeRuntimeBackend(site_resolver=FrappeSiteResolver(site_map={TENANT: SITE}),
                                               frappe_factory=lambda e=engine: e, offline_ddl_simulator=True)
                adapter = ChangeEngineAdapter(test_hooks=False, environment="test", frappe_backend=backend)
                prov = adapter.call("provision_site", _ctx(), {
                    "idempotencyKey": f"idemp_f3_wrw_{kind_name}_{abs(hash(eid))}",
                    "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
                    "blueprintId": "bp-f2", "siteClass": "sandbox", "countryPack": "sa"})
                self.assertTrue(prov["ok"], prov)
                before = repr(engine.ensure_site(SITE).rows)
                with self.subTest(kind=kind_name, entity=eid):
                    planned = adapter.call("plan", _ctx(), {"artifact": _artifact([builder(1, "x_bad", eid)])})
                    self.assertTrue(planned["ok"], planned)
                    self.assertEqual(planned["result"]["verdict"], "rejected", planned)
                    self.assertEqual(repr(engine.ensure_site(SITE).rows), before)

    def test_whitespace_refusal_writes_nothing_to_the_engine(self) -> None:
        for eid in WHITESPACE_IDS:
            engine = CaseInsensitiveEngine(SITE)
            backend = FrappeRuntimeBackend(site_resolver=FrappeSiteResolver(site_map={TENANT: SITE}),
                                           frappe_factory=lambda e=engine: e, offline_ddl_simulator=True)
            adapter = ChangeEngineAdapter(test_hooks=False, environment="test", frappe_backend=backend)
            prov = adapter.call("provision_site", _ctx(), {
                "idempotencyKey": f"idemp_f3_w_{abs(hash(eid))}",
                "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
                "blueprintId": "bp-f2", "siteClass": "sandbox", "countryPack": "sa"})
            self.assertTrue(prov["ok"], prov)
            before = repr(engine.ensure_site(SITE).rows)
            with self.subTest(entity=eid):
                planned = adapter.call("plan", _ctx(), {"artifact": _artifact([_entity(1, eid), _role(2, "r_ws", eid)])})
                self.assertTrue(planned["ok"], planned)
                self.assertEqual(planned["result"]["verdict"], "rejected")
                self.assertEqual(repr(engine.ensure_site(SITE).rows), before)

    def test_legitimate_ids_still_plan_on_both_backends(self) -> None:
        for eid in ("customer", "sales_invoice", "delivery_note"):
            for name, adapter in self._adapters():
                with self.subTest(entity=eid, adapter=name):
                    result = self._plan(adapter, [_role(1, "r_ok", eid)], f"idemp_f3_ok_{eid}_{name}")
                    self.assertNotEqual(result["steps"][0].get("reasonCode"), "unsupported_value_type", result)
                    self.assertEqual(result["steps"][0]["disposition"], "gated", result)

    # inherited tests of the parent class are not repeated
    test_own_entity_grant_allowed_and_unmapped_builtin_refused_on_both = None
    test_own_entity_grant_alone_needs_gate_approval_on_both = None
    test_protected_own_entity_stays_refused_in_memory = None


if __name__ == "__main__":
    unittest.main()
