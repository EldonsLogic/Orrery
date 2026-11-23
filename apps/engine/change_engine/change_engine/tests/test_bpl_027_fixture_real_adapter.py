"""BPL-027: compile the trading fixture and apply it through the real engine adapter on a bench site.

Flow: compile services/blueprint/fixtures/trading-distribution.blueprint.json with the BPL-004 compiler ->
plan and preview -> DDL plan gate (apply without gateApproved is refused) -> apply through ChangeEngineAdapter
wired to FrappeRuntimeBackend on a real site -> read the site back and compare with the Blueprint -> re-apply
is a no-op -> an incremental change rolls back (BPL-008) to the prior state.

The bench tests need a real, freshly created bench site and skip with an explicit reason otherwise. How to run
them: apps/engine/change_engine/README.md, section "BPL-027 integration test". Synthetic data only.
"""
from __future__ import annotations

import contextlib
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from types import SimpleNamespace

from change_engine.adapter import ADAPTER_ID, ChangeEngineAdapter, FrappeBackendError, FrappeSiteResolver, make_frappe_adapter
from change_engine.adapter import contracts_support as cs
from change_engine.adapter.mapping import (
    ADAPTER_DOCTYPE_MODULE,
    BLUEPRINT_TO_FRAPPE_FIELDTYPE,
    ENGINE_NAME_PREFIX,
    _sanitize_custom_fieldname,
    engine_role_name,
    engine_state_name,
    entity_to_doctype,
)

REPO_ROOT = Path(os.environ.get("PLATFORM_REPO_ROOT") or Path(__file__).resolve().parents[5]).expanduser()
SERVICES_BP_DIR = REPO_ROOT / "services" / "blueprint"
FIXTURE = SERVICES_BP_DIR / "fixtures" / "trading-distribution.blueprint.json"
MAPPING = REPO_ROOT / "contracts" / "examples" / "engine-mapping-golden-path.json"
# Every engine-mapping example is a separate mapping over the same fixture; an entity is mapped in only one of them.
MAPPINGS = (MAPPING, REPO_ROOT / "contracts" / "examples" / "engine-mapping-purchasing.json")


def _contract_native_fields() -> dict:
    """{(entity, field): native engine field or None} for fields the contract stores under another name, read from the files."""
    out = {}
    for path in MAPPINGS:
        for ent in json.loads(path.read_text(encoding="utf-8"))["entities"]:
            for fld in ent["fields"]:
                if fld.get("engineField") != fld["blueprintField"]:
                    out[(ent["blueprintEntity"], fld["blueprintField"])] = fld.get("engineField")
    return out


CONTRACT_NATIVE = _contract_native_fields()
BENCH_SITE = os.environ.get("BPL027_BENCH_SITE", "")
SITES_PATH = os.path.expanduser(os.environ.get("BPL027_SITES_PATH", "~/frappe-bench/sites"))
TENANT = "t_bpl027"
# Blueprint permission action -> engine permission flag.
ACTION_FLAG = {"read": "read", "create": "create", "update": "write", "submit": "submit", "cancel": "cancel", "delete": "delete"}
# Engine permission flags on a rule (ADR-0039 section 2, ADR-0051).
RULE_FLAGS = ("read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import", "share",
              "print", "email", "set_user_permissions")
# Tables whose row counts must not move on a no-op re-apply.
FINGERPRINT_TABLES = ("Role", "Workflow", "Workflow Document State", "Workflow Transition", "Report", "Custom Field",
                      "Property Setter", "DocType", "Warehouse", "Custom DocPerm")


_ENV_PATCH = mock.patch.dict(os.environ, {"CHANGE_ENGINE_ENV": "test"})


def setUpModule():
    _ENV_PATCH.start()  # ERP-027: the offline DDL simulator is refused unless CHANGE_ENGINE_ENV is dev or test


def tearDownModule():
    _ENV_PATCH.stop()


def _import_compiler():
    for p in (SERVICES_BP_DIR, SERVICES_BP_DIR / "diff"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    from compiler import compile_blueprint  # type: ignore[import-not-found]
    from registry import Registry  # type: ignore[import-not-found]
    return compile_blueprint, Registry


def bench_skip_reason() -> str | None:
    """Return why the bench tests cannot run here, or None when a bench site is configured."""
    if not BENCH_SITE:
        return "BPL027_BENCH_SITE is not set: needs a fresh bench site (see change_engine README, BPL-027)"
    try:
        import frappe  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return "frappe is not importable: run inside the bench Python environment (see change_engine README, BPL-027)"
    try:
        _import_compiler()
    except ImportError as exc:
        return f"Blueprint compiler not importable ({exc.name}): mount services/blueprint and install jsonschema"
    return None


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def without_attachments(bp: dict) -> dict:
    """The adapter refuses Blueprint type 'attachment' (unsupported_value_type, same as the fake); swap it for string."""
    bp = copy.deepcopy(bp)
    for ent in bp["entities"]:
        for fld in ent["fields"]:
            if fld["type"] == "attachment":
                fld["type"] = "string"
    return bp


def without_unenforceable_constraints(bp: dict) -> dict:
    """Q-603 (BPL-031 review): entity.add refuses a new unique or indexed field on a built-in engine type, because the
    guarded field path cannot deploy that DDL here and the field must never apply without its constraint. Until Q-603 is
    answered the fixture is adapted in memory, like the attachment type above: the constraint is dropped from every field
    of a contract-mapped entity that the adapter would have to add (customer_code, supplier_code). A field the engine
    already holds under the same name (item_code) needs no DDL and keeps it, so the plan still gates unique_or_index."""
    bp = copy.deepcopy(bp)
    mapped, native = set(), set()
    for path in MAPPINGS:
        for ent in json.loads(path.read_text(encoding="utf-8"))["entities"]:
            mapped.add(ent["blueprintEntity"])
            native |= {(ent["blueprintEntity"], f["blueprintField"]) for f in ent["fields"] if f.get("engineField") == f["blueprintField"]}
    for ent in bp["entities"]:
        for fld in ent["fields"]:
            if ent["id"] in mapped and (ent["id"], fld["id"]) not in native:
                fld.pop("unique", None)
                fld.pop("indexed", None)
    return bp


def apply_ready(bp: dict) -> dict:
    return without_unenforceable_constraints(without_attachments(bp))


def with_unmapped_builtin_role(bp: dict) -> dict:
    """Add an entity named for an ERPNext built-in that is still outside the reviewed mapping (Payment Entry) and a
    role that grants it. Supplier, Price List and the purchase documents are mapped since BPL-034 and plan."""
    bp = copy.deepcopy(bp)
    entity = copy.deepcopy(next(e for e in bp["entities"] if e["id"] == "payment"))
    entity["id"] = "payment_entry"
    bp["entities"].append(entity)
    role = copy.deepcopy(bp["roles"][0])
    role["id"] = "payment_clerk"
    role["permissions"] = [{"entity": "payment_entry", "actions": ["read"]}]
    bp["roles"].append(role)
    return bp


def compile_for_adapter(bp: dict) -> dict:
    """Compile with the real BPL-004 compiler, then retarget to this adapter's id and reseal.

    The compiler passes meta.engineTarget through ("change_engine" in the fixture) while the adapter id is
    "frappe" (compiler open question 4, contract 16.12), so the test retargets and reseals the artifact.
    """
    compile_blueprint, Registry = _import_compiler()
    reg = Registry.from_manifests(
        [json.loads(p.read_text(encoding="utf-8")) for p in sorted((SERVICES_BP_DIR / "fixtures" / "registry").glob("*.json"))]
    )
    result = compile_blueprint(bp, reg, json.loads(MAPPING.read_text(encoding="utf-8")), environment="sandbox")
    if not result.ok:
        raise AssertionError([str(e) for e in result.errors])
    art = copy.deepcopy(result.artifact)
    art["engineTarget"] = {"adapter": ADAPTER_ID, "versionSet": art["engineTarget"]["versionSet"]}
    return seal(art)


def seal(art: dict) -> dict:
    art = copy.deepcopy(art)
    if art.get("inverse"):
        art["inverse"] = seal(art["inverse"])
    digest, art_id = cs.artifact_hashes(art)
    art["artifactId"] = art_id
    art["integrity"] = {"algorithm": "sha256-canonical-json-v1", "contentHash": digest, "signature": None}
    return art


def expected_engine_config(bp: dict) -> dict:
    """What a correct apply must leave on the site, derived from the Blueprint alone.

    Role and workflow-state names are the adapter-owned names (SEC-022, ADR-0051), never the raw Blueprint ids;
    "permissions" lists the Blueprint's own grants (what the Blueprint asks for, before ADR-0051 narrows it).
    """
    role = engine_role_name
    mapped, doctypes = {}, {}
    for path in MAPPINGS:
        if path.exists():
            for ent in json.loads(path.read_text(encoding="utf-8"))["entities"]:
                doctypes[ent["blueprintEntity"]] = ent["engineDocType"]
                for fld in ent["fields"]:
                    if fld.get("engineField"):
                        mapped[(ent["blueprintEntity"], fld["blueprintField"])] = fld["engineField"]
    # BPL-031: expected document types come from the mapping contract, never from the adapter's own mapper, so a
    # duplicate (a custom "Purchase Order Line" beside the built-in "Purchase Order Item") cannot hide. An entity
    # with no mapping becomes an adapter-owned custom document type named by title-casing its id (ADR-0051 item 3).
    custom = {e["id"]: " ".join(w.capitalize() for w in e["id"].split("_")) for e in bp["entities"] if e["id"] not in doctypes}
    return {
        "roles": sorted(role(r["id"]) for r in bp["roles"]),
        "workflows": {
            wf["id"]: {
                "doctype": entity_to_doctype(wf["entity"]),
                "states": sorted(engine_state_name(s["id"]) for s in wf["states"]),
                "transitions": sorted(
                    (engine_state_name(t["from"]), t.get("actionLabels", {}).get("en") or t["id"], engine_state_name(t["to"]), r)
                    for t in wf["transitions"]
                    for r in [role(x) for x in t["allowedRoles"]]
                ),
            }
            for wf in bp["workflows"]
        },
        "reports": {
            r["id"]: {"doctype": entity_to_doctype(r["entity"]) if r.get("entity") else None,
                      "roles": sorted(role(x) for x in r["visibleToRoles"])}
            for r in bp["reports"]
        },
        "warehouses": sorted(loc["id"] for loc in bp["locations"] if loc["kind"] == "warehouse"),
        "entities": {e["id"]: doctypes.get(e["id"]) or custom[e["id"]] for e in bp["entities"]},
        "custom_entities": sorted(custom.values()),
        "fields": {
            (e["id"], f["id"]): {mapped.get((e["id"], f["id"])), f["id"], "custom_" + f["id"]} - {None}
            for e in bp["entities"]
            for f in e["fields"]
            if f["type"] in BLUEPRINT_TO_FRAPPE_FIELDTYPE
        },
        "permissions": sorted(
            (r["id"], entity_to_doctype(p["entity"]), ACTION_FLAG[a])
            for r in bp["roles"]
            for p in r.get("permissions", [])
            for a in p["actions"]
            if a in ACTION_FLAG
        ),
    }


def _attr(obj, key: str):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def name_clashes(f, exp: dict) -> list[str]:
    """Every engine role and workflow state the apply wrote must carry the adapter-owned name exactly (SEC-022).

    The engine matches names without case, so a lookup of a raw Blueprint id can land on a built-in record
    ("auditor" -> "Auditor"); this read-back fails on any such alias, on any transition or report role that is
    not the managed one, and on a state that resolves to a differently spelled record."""
    clashes = [f"role:{r}" for r in exp["roles"] if f.db.get_value("Role", r, "name") != r]
    for wf_id, want in exp["workflows"].items():
        wf = f.get_doc("Workflow", wf_id)
        got_states = {_attr(s, "state") for s in wf.states}
        clashes += [f"{wf_id}:state:{s}" for s in want["states"] if s not in got_states]
        clashes += [f"{wf_id}:record:{s}" for s in want["states"] if f.db.get_value("Workflow State", s, "name") != s]
        got = {(_attr(t, "state"), _attr(t, "action"), _attr(t, "next_state"), _attr(t, "allowed")) for t in wf.transitions}
        clashes += [f"{wf_id}:transition:{t}" for t in want["transitions"] if t not in got]
    for rep_id, want in exp["reports"].items():
        got_roles = sorted(_attr(r, "role") for r in f.get_doc("Report", rep_id).roles)
        if got_roles != want["roles"]:
            clashes.append(f"report:{rep_id}:{got_roles}")
    return clashes


def entity_gaps(f, exp: dict) -> dict:
    """BPL-031 (was BPL-027 finding 2): read the engine back against expected_engine_config, independent of the adapter.

    "missing" lists every expected document type that does not exist and every Blueprint field that is neither a
    native engine field nor a custom field on it. "duplicates" lists every document type the adapter made (custom,
    in its own module) that is not one of the expected custom entities, such as a custom twin of a built-in."""
    missing = []
    for ent_id, dt in exp["entities"].items():
        if not f.db.exists("DocType", dt):
            missing.append(f"doctype {dt} ({ent_id})")
            continue
        names = {_attr(d, "fieldname") for d in f.get_meta(dt).fields}
        missing += [f"{dt}.{fid}" for (eid, fid), cands in exp["fields"].items() if eid == ent_id and not cands & names]
    made = {str(_attr(r, "name")) for r in f.get_all("DocType", filters={"custom": 1, "module": ADAPTER_DOCTYPE_MODULE}, fields=["name"])}
    return {"missing": sorted(missing), "duplicates": sorted(made - set(exp["custom_entities"]))}


def expected_grants(f, bp: dict) -> dict:
    """ADR-0051 grant table, written independently of the adapter: {(role, doctype): {"flags", "if_owner", "hidden"}}.

    Fail closed: location scopes are withheld until record scoping exists; a grant without read, or hiding a field
    the engine does not hold, is withheld; a grant that masks fields gets no create or write (ADR-0039 RM-018);
    submit needs a submittable type and write, cancel needs submit, amend needs create and cancel."""
    out = {}
    for r in bp["roles"]:
        scope = r["scope"]["type"]
        if scope not in ("company", "own_records"):
            continue
        for p in r["permissions"]:
            acts, dt = set(p["actions"]), entity_to_doctype(p["entity"])
            meta = f.get_meta(dt)
            names = {_attr(d, "fieldname") for d in meta.fields}
            hidden, native, withheld = [], [], False
            for h in p.get("hiddenFields", []):
                # Every representation is masked or the grant is withheld (BPL-031 re-review): the native field the contract
                # names (or None: the data lives on another record), a native field of the same name, and the custom twin.
                held = {h} & names
                if (p["entity"], h) in CONTRACT_NATIVE:
                    n = CONTRACT_NATIVE[(p["entity"], h)]
                    withheld |= n is None or n not in names
                    held |= {n} & names
                # a native field is protected only where it already sits above level 0; the adapter never moves it
                withheld |= any(int(_attr(meta.get_field(n), "permlevel") or 0) < 1 for n in held)
                native += sorted(held)
                twin = _sanitize_custom_fieldname(h)
                if twin in names:
                    hidden.append(twin)
                else:
                    withheld |= not held
            if "read" not in acts or withheld:
                continue
            masked = bool(p.get("hiddenFields") or p.get("readOnlyFields"))
            flags = {"read"} | {"export"} & acts | {"delete"} & acts
            if not masked:
                flags |= {"create"} & acts | ({"write"} if "update" in acts else set())
            if int(getattr(meta, "is_submittable", 0) or 0) and "write" in flags and "submit" in acts:
                flags.add("submit")
                if "cancel" in acts:
                    flags.add("cancel")
                    if "create" in flags:
                        flags.add("amend")
            out[(engine_role_name(r["id"]), dt)] = {"flags": flags, "if_owner": int(scope == "own_records"), "hidden": hidden,
                                                    "native": native}
    return out


def grant_gaps(f, bp: dict) -> dict:
    """Compare managed permission rules on the site with expected_grants (BPL-032): missing, extra, field levels."""
    exp = expected_grants(f, bp)
    rules: dict = {}
    for row in f.get_all("Custom DocPerm", fields=["*"]):
        role = str(_attr(row, "role") or "")
        if role.startswith(ENGINE_NAME_PREFIX):
            on = {k for k in RULE_FLAGS if int(_attr(row, k) or 0)}
            rules[(role, _attr(row, "parent"), int(_attr(row, "permlevel") or 0))] = (on, int(_attr(row, "if_owner") or 0))
    act = {(r, dt): v for (r, dt, lvl), v in rules.items() if lvl == 0 and v[0]}
    missing = sorted((r, dt, fl) for (r, dt), e in exp.items() for fl in e["flags"] - act.get((r, dt), (set(), 0))[0])
    extra = sorted((r, dt, fl) for (r, dt), (on, _o) in act.items() for fl in on - exp.get((r, dt), {"flags": set()})["flags"])
    missing += sorted((r, dt, "if_owner") for (r, dt), e in exp.items() if (r, dt) in act and act[(r, dt)][1] != e["if_owner"])
    levels = []
    for (r, dt), e in exp.items():
        meta = f.get_meta(dt)
        readers = [k for k in exp if k[1] == dt]
        for fn in e["hidden"]:
            lvl = int(_attr(meta.get_field(fn), "permlevel") or 0)
            if lvl == 0 or "read" in rules.get((r, dt, lvl), (set(), 0))[0]:
                levels.append((r, dt, fn, "visible"))
            levels += [(o, dt, fn, "hidden") for (o, _d) in readers
                       if fn not in exp[(o, _d)]["hidden"] and lvl and "read" not in rules.get((o, dt, lvl), (set(), 0))[0]]
    for (r, dt), e in exp.items():
        for n in e["native"]:  # a native cost field must not be readable by the role that hides it
            lvl = int(_attr(f.get_meta(dt).get_field(n), "permlevel") or 0)
            if lvl == 0 or "read" in rules.get((r, dt, lvl), (set(), 0))[0]:
                levels.append((r, dt, n, "native visible"))
    return {"missing": missing, "extra": extra, "levels": sorted(set(levels))}


def ctx() -> dict:
    return {
        "contractVersion": "0.1.2",
        "requestId": "01J00000000000000000000027",
        "correlationId": "corr_bpl027_01",
        "tenantId": TENANT,
        "caller": {"service": "control_plane", "onBehalfOf": {"kind": "user", "id": "usr_owner"}},
        "deadlineMs": 120000,
    }


def new_adapter(db_path: str) -> ChangeEngineAdapter:
    return make_frappe_adapter(
        db_path=db_path,
        site_resolver=FrappeSiteResolver(site_map={TENANT: BENCH_SITE}),
        sites_path=SITES_PATH,
        test_hooks=False,
    )


@contextlib.contextmanager
def site_db():
    """Open the bench site directly for read-back (independent of the adapter under test)."""
    import frappe  # type: ignore[import-not-found]

    cwd = os.getcwd()
    os.chdir(SITES_PATH)
    try:
        frappe.init(site=BENCH_SITE, sites_path=".")
        frappe.connect()
        yield frappe
    finally:
        frappe.destroy()
        os.chdir(cwd)


def ensure_synthetic_company() -> None:
    """Tenant provisioning (not the adapter) sets up the company; do it here with synthetic data if missing."""
    with site_db() as f:
        if f.get_all("Company", limit=1):
            return
        from erpnext.setup.setup_wizard.setup_wizard import setup_complete  # type: ignore[import-not-found]

        setup_complete(f._dict({
            "country": "Saudi Arabia", "currency": "SAR", "fy_start_date": "2026-01-01", "fy_end_date": "2026-12-31",
            "company_name": "Synthetic Trading Co", "company_abbr": "STC", "chart_of_accounts": "Standard",
            "domain": "Distribution", "company_tagline": "Synthetic BPL-027 test company", "full_name": "Synthetic Owner",
            "email": "owner.bpl027@example.invalid", "language": "English",
        }))
        f.db.commit()


def fingerprint() -> dict:
    with site_db() as f:
        return {t: f.db.count(t) for t in FINGERPRINT_TABLES}


class TestBpl027Offline(unittest.TestCase):
    """Runs everywhere: the skip is explicit and the expected read-back is derived from the fixture."""

    def test_skip_reason_names_what_is_missing(self) -> None:
        reason = bench_skip_reason()
        if BENCH_SITE:
            self.skipTest("bench configured")
        self.assertIn("BPL027_BENCH_SITE", reason or "")

    def test_expected_config_covers_the_fixture(self) -> None:
        exp = expected_engine_config(load_fixture())
        self.assertEqual(len(exp["roles"]), 8)
        self.assertEqual(sorted(exp["workflows"]), ["purchase_order_flow", "sales_invoice_flow", "sales_order_flow", "stock_transfer_flow"])
        self.assertEqual(exp["warehouses"], ["wh_jeddah", "wh_riyadh"])
        self.assertEqual(exp["workflows"]["sales_order_flow"]["doctype"], "Sales Order")
        self.assertIn(("warehouse_keeper", "Delivery Note", "submit"), exp["permissions"])


    def _apply_fixture_offline(self):
        """Apply the fixture's entities, role grants (mapped, purchasing and custom), workflows and reports through the real backend on a
        simulated engine whose names match without case, like the bench (no compiler needed)."""
        from change_engine.adapter import FrappeRuntimeBackend
        from change_engine.tests.ci_engine_fake import CaseInsensitiveEngine

        bp = apply_ready(load_fixture())
        engine = CaseInsensitiveEngine("bpl027.localhost")
        backend = FrappeRuntimeBackend(site_resolver=FrappeSiteResolver(site_map={TENANT: "bpl027.localhost"}),
                                       frappe_factory=lambda: engine, offline_ddl_simulator=True)
        auditor_before = engine.db.get_value("Role", "Auditor", ["name", "disabled"])
        for section, kind in (("entities", "entity.add"), ("roles", "role.upsert"), ("workflows", "workflow.upsert"),
                              ("reports", "report.upsert")):
            for elem in bp[section]:
                backend.execute_step(TENANT, {"seq": 1, "kind": kind, "pointer": f"/{section}/{elem['id']}",
                                              "subject": {"kind": section[:-1], "id": elem["id"]}, "params": {"definition": elem}})
        self.assertEqual(engine.db.get_value("Role", "Auditor", ["name", "disabled"]), auditor_before)
        return bp, engine

    def test_04b_offline_records_carry_adapter_owned_names(self) -> None:
        """SEC-022: the same read-back as bench test_04b, on a case-insensitive simulated engine."""
        bp, engine = self._apply_fixture_offline()
        self.assertEqual(name_clashes(engine, expected_engine_config(bp)), [])

    def test_06_offline_mapped_grants_reach_the_engine(self) -> None:
        """BPL-032: the same read-back as bench test_06, on a case-insensitive simulated engine."""
        bp, engine = self._apply_fixture_offline()
        self.assertEqual(grant_gaps(engine, bp), {"missing": [], "extra": [], "levels": []})
        granted = expected_grants(engine, bp)
        self.assertIn(("bp-owner", "Sales Order"), granted)  # the check is not vacuous
        self.assertIn(("bp-owner", "Delivery Note"), granted)  # delivery_note is in the reviewed mapping (PR #235 r2)
        self.assertEqual(granted[("bp-sales_rep", "Sales Order")]["if_owner"], 1)
        self.assertNotIn(("bp-warehouse_keeper", "Delivery Note"), granted)  # warehouse scope: withheld

    def test_06c_offline_literal_grants_and_untouched_engine_rules(self) -> None:
        """Review round 1 (item 6) & round 2 (item 4): literal expectations written by hand from the fixture and the
        ADR-0051 table, with no adapter helper; built-in roles' rules, seeded built-in DocTypes, and non-owned field
        levels stay exactly as they were."""
        from change_engine.adapter import FrappeRuntimeBackend
        from change_engine.tests.ci_engine_fake import CaseInsensitiveEngine

        bp = apply_ready(load_fixture())
        engine = CaseInsensitiveEngine("bpl027.localhost")
        engine.add_field("Item", "valuation_secret", permlevel=2)  # an engine field on a level the adapter never owns
        engine.add_field("Customer", "credit_hold", permlevel=1)
        backend = FrappeRuntimeBackend(site_resolver=FrappeSiteResolver(site_map={TENANT: "bpl027.localhost"}),
                                       frappe_factory=lambda: engine, offline_ddl_simulator=True)
        for section, kind in (("entities", "entity.add"), ("roles", "role.upsert")):
            for elem in bp[section]:
                backend.execute_step(TENANT, {"seq": 1, "kind": kind, "pointer": f"/{section}/{elem['id']}",
                                              "subject": {"kind": section[:-1], "id": elem["id"]}, "params": {"definition": elem}})
        rules = {(r["role"], r["parent"], int(r.get("permlevel") or 0)): (
                     {k for k in ("read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import",
                                  "share", "print", "email", "set_user_permissions") if int(r.get(k) or 0)}, int(r.get("if_owner") or 0))
                 for r in engine.rows("Custom DocPerm")}
        self.assertEqual(rules[("bp-owner", "Sales Order", 0)], ({"read", "create", "write", "export"}, 0))
        self.assertEqual(rules[("bp-owner", "Delivery Note", 0)], ({"read", "export"}, 0))
        self.assertEqual(rules[("bp-accountant", "Sales Invoice", 0)], ({"read", "create", "write", "submit", "cancel", "amend", "export"}, 0))
        self.assertEqual(rules[("bp-accountant", "Sales Order", 0)], ({"read", "export"}, 0))  # submit without update: dropped
        self.assertEqual(rules[("bp-accountant", "Delivery Note", 0)], ({"read", "export"}, 0))
        self.assertEqual(rules[("bp-sales_rep", "Sales Order", 0)], ({"read", "create", "write", "submit", "cancel", "amend"}, 1))
        self.assertEqual(rules[("bp-sales_rep", "Delivery Note", 0)], ({"read"}, 1))
        self.assertEqual(rules[("bp-auditor", "Payment", 0)], ({"read", "export"}, 0))  # a document type the adapter made
        # BPL-031: entity.add now gives Customer its credit_limit, so the grant that hides it applies (read only, level 2).
        self.assertEqual(rules[("bp-sales_rep", "Customer", 0)], ({"read"}, 1))
        # BPL-031 review: the contract stores cost_price in the native valuation_rate, which sits on level 0 here (no tenant
        # provisioning ran), so masking the custom twin protects nothing and the sales rep's Item grant is withheld.
        self.assertNotIn(("bp-sales_rep", "Item", 0), rules)
        self.assertFalse([k for k in rules if k[0] in ("bp-warehouse_keeper", "bp-branch_sales_manager")])  # location scopes
        # Field levels are used only where the fixture hides a field the engine now holds (BPL-031): Customer and Item.
        self.assertEqual({(k[1], k[2]) for k in rules if k[0].startswith("bp-") and k[2] != 0}, {("Customer", 2)})
        # BPL-032 after BPL-034: the purchasing and price-list built-ins are in the reviewed mapping and hold the fixture's grants.
        self.assertEqual(rules[("bp-owner", "Supplier", 0)], ({"read", "create", "write", "export"}, 0))
        self.assertEqual(rules[("bp-owner", "Purchase Order", 0)], ({"read", "create", "write", "export"}, 0))  # cancel without submit: dropped
        self.assertEqual(rules[("bp-accountant", "Purchase Order", 0)], ({"read", "export"}, 0))  # submit without update: dropped
        self.assertEqual(rules[("bp-accountant", "Purchase Invoice", 0)], ({"read", "create", "write", "submit", "export"}, 0))
        self.assertEqual(rules[("bp-purchasing_officer", "Purchase Order", 0)],
                         ({"read", "create", "write", "submit", "cancel", "amend", "export"}, 0))
        self.assertEqual(rules[("bp-sales_rep", "Price List", 0)], ({"read"}, 1))
        # Seeded built-in DocTypes remain custom=0 (never overwritten by entity.add).
        doctypes = {d["name"]: d for d in engine.rows("DocType")}
        for dt in ("Delivery Note", "Supplier", "Price List", "Purchase Order", "Purchase Receipt", "Purchase Invoice"):
            self.assertEqual(doctypes[dt]["custom"], 0, dt)
        builtin = {k: v for k, v in rules.items() if not k[0].startswith("bp-")}
        self.assertEqual(builtin, {("Auditor", "Customer", 0): ({"read"}, 0),
                                   ("Sales User", "Customer", 0): ({"read", "write", "create"}, 0),
                                   ("Sales User", "Item", 0): ({"read"}, 0)})
        levels = {fn: int(getattr(engine.get_meta(dt).get_field(fn), "permlevel", 0) or 0)
                  for dt, fn in (("Item", "valuation_secret"), ("Customer", "credit_hold"))}
        self.assertEqual(levels, {"valuation_secret": 2, "credit_hold": 1})
        # The only Property Setter is the field level of the hidden field entity.add created on Customer (BPL-031), placed on
        # the free level (Customer.credit_hold holds 1).
        self.assertEqual({(r["doc_type"], r["field_name"], r["property"], int(r["value"])) for r in engine.rows("Property Setter")},
                         {("Customer", "custom_credit_limit", "permlevel", 2)})

    def test_06d_offline_purchasing_grants_plan_and_unmapped_builtins_are_still_refused(self) -> None:
        """ADR-0051 item 3 after BPL-034 and BPL-032: Supplier, Price List and the purchase documents are in the reviewed
        mapping, so the fixture roles that grant them apply and plan like the sales ones; a built-in engine document type
        outside the mapping (Payment Entry) is still refused at both plan and apply time."""
        from change_engine.adapter import FrappeRuntimeBackend
        from change_engine.tests.ci_engine_fake import CaseInsensitiveEngine

        bp, engine = self._apply_fixture_offline()
        backend = FrappeRuntimeBackend(site_resolver=FrappeSiteResolver(site_map={TENANT: "bpl027.localhost"}),
                                       frappe_factory=lambda: engine, offline_ddl_simulator=True)
        granted = expected_grants(engine, bp)
        for doctype in ("Supplier", "Price List", "Purchase Order", "Purchase Receipt", "Purchase Invoice"):
            self.assertIn(("bp-owner", doctype), granted)

        bp_x = with_unmapped_builtin_role(bp)
        clerk = next(r for r in bp_x["roles"] if r["id"] == "payment_clerk")
        with self.assertRaises(FrappeBackendError) as err:
            backend.execute_step(TENANT, {"seq": 1, "kind": "role.upsert", "pointer": "/roles/payment_clerk",
                                          "subject": {"kind": "role", "id": "payment_clerk"}, "params": {"definition": clerk}})
        self.assertEqual(err.exception.details.get("reasonCode"), "protected_subject")
        self.assertTrue(err.exception.side_effect_free)
        self.assertIsNone(engine.db.get_value("Role", "bp-payment_clerk", "name"))

        # Plan time on the compiled trading fixture: every role plans (gated, never blocked); with the Payment Entry
        # grant added, only that one role.upsert step is blocked, with no writes.
        adapter = make_frappe_adapter(
            site_resolver=FrappeSiteResolver(site_map={TENANT: "bpl027.localhost"}),
            frappe_factory=lambda: engine,
            offline_ddl_simulator=True,
            test_hooks=False,
        )
        art = compile_for_adapter(bp)
        prov = adapter.call("provision_site", ctx(), {
            "idempotencyKey": "idemp_bpl027_06d_prov", "engineTarget": art["engineTarget"],
            "blueprintId": art["blueprint"]["id"], "siteClass": "sandbox", "countryPack": "sa",
        })
        self.assertTrue(prov["ok"], prov)
        planned = adapter.call("plan", ctx(), {"artifact": art})
        self.assertTrue(planned["ok"], planned)
        self.assertEqual(planned["result"]["verdict"], "needs_gate_approval")
        self.assertFalse([s for s in planned["result"]["steps"] if s["disposition"] in ("blocked", "unsupported")])

        art_x = compile_for_adapter(bp_x)
        planned_x = adapter.call("plan", ctx(), {"artifact": art_x})
        self.assertTrue(planned_x["ok"], planned_x)
        self.assertEqual(planned_x["result"]["verdict"], "rejected")
        blocked = [s for s in planned_x["result"]["steps"] if s["disposition"] == "blocked"]
        by_seq = {s["seq"]: s for s in art_x["steps"]}
        self.assertEqual([by_seq[s["seq"]]["pointer"] for s in blocked], ["/roles/payment_clerk"])
        self.assertEqual(blocked[0].get("reasonCode"), "protected_subject")
        self.assertIsNone(engine.db.get_value("Role", "bp-payment_clerk", "name"))

    @staticmethod
    def _two_warehouse_artifact(target: dict) -> dict:
        steps = [
            {"seq": i, "phase": 3, "kind": "location.upsert", "subject": {"kind": "location", "id": wid, "parents": []},
             "pointer": f"/locations/{wid}", "impact": "config", "ddlImpact": "none", "reversible": True,
             "params": {"definition": {"id": wid, "kind": "warehouse", "labels": {"en": wid, "ar": wid}}},
             "sourceOps": [f"/locations/{wid}"]}
            for i, wid in ((1, "wh_a"), (2, "wh_b"))
        ]
        counts = dict.fromkeys(("cosmetic", "config", "data_shape", "destructive", "compliance", "access", "branding"), 0)
        counts["config"] = 2
        return seal({"artifactSchema": "0.1.0", "kind": "forward", "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
                     "blueprint": {"id": "bp-offline", "base": None, "target": {"hash": "sha256:" + "1" * 64, "revision": 1},
                                   "diffHash": None},
                     "engineTarget": target, "components": [], "steps": steps, "skippedOps": [], "postConditions": [],
                     "risk": {"counts": counts, "total": 2, "maxImpact": "config", "needsDdlPlanGate": False,
                              "touchesCompliance": False, "touchesAccess": False, "touchesLedgerOrTax": False,
                              "requiresTeamReview": False, "irreversibleSteps": 0},
                     "inverse": None})

    def test_engine_failure_mid_apply_compensates_when_proven_side_effect_free(self) -> None:
        """A proven pre-write failure (side_effect_free=True) compensates prior steps cleanly without mutating or aliasing site.config."""
        adapter = make_frappe_adapter(simulated=True, test_hooks=False)
        target = {"adapter": ADAPTER_ID, "versionSet": "set-example"}
        res = adapter.call("provision_site", ctx(), {"idempotencyKey": "idemp_bpl027_off_prov", "engineTarget": target,
                                                    "blueprintId": "bp-offline", "siteClass": "sandbox", "countryPack": "sa"})
        self.assertTrue(res["ok"], res)
        art = self._two_warehouse_artifact(target)
        backend = adapter.frappe_backend
        real = backend.execute_step

        def failing_pre_write(tenant_id, step):
            if step["seq"] == 2 and step["kind"] == "location.upsert":
                raise FrappeBackendError("site_not_ready", stage="execute", side_effect_free=True)
            return real(tenant_id, step)

        backend.execute_step = failing_pre_write
        plan = adapter.call("plan", ctx(), {"artifact": art})["result"]
        out = adapter.call("apply", ctx(), {"idempotencyKey": "idemp_bpl027_off_apply", "artifact": art,
                                            "planToken": plan["planToken"],
                                            "approvals": {"changeApproved": "01J00000000000000000000010"}})["result"]
        self.assertEqual(out["status"], "compensated", out)
        self.assertEqual(out["site"]["state"], "ready", out)

    def test_engine_failure_after_db_write_rolls_back_and_enters_recovery_required(self) -> None:
        """Fail closed: if execute_step raises after a DB write, rollback runs and the site enters recovery_required."""
        adapter = make_frappe_adapter(simulated=True, test_hooks=False)
        target = {"adapter": ADAPTER_ID, "versionSet": "set-example"}
        res = adapter.call("provision_site", ctx(), {"idempotencyKey": "idemp_bpl027_off_prov_rr", "engineTarget": target,
                                                    "blueprintId": "bp-offline", "siteClass": "sandbox", "countryPack": "sa"})
        self.assertTrue(res["ok"], res)
        art = self._two_warehouse_artifact(target)
        backend = adapter.frappe_backend
        sim_frappe = backend._acquire_frappe()

        rollbacks = []
        orig_rollback = sim_frappe.db.rollback

        def spy_rollback():
            rollbacks.append(True)
            return orig_rollback()

        sim_frappe.db.rollback = spy_rollback

        writes = []
        orig_get_doc = sim_frappe.get_doc

        def partial_write_then_fail(payload, *args, **kwargs):
            doc = orig_get_doc(payload, *args, **kwargs)
            if isinstance(payload, dict) and payload.get("doctype") == "Warehouse" and payload.get("warehouse_name") == "wh_b":
                orig_insert = doc.insert

                def insert_then_boom(*iargs, **ikwargs):
                    orig_insert(*iargs, **ikwargs)
                    writes.append(payload["warehouse_name"])
                    raise RuntimeError("simulated crash after DB write")

                object.__setattr__(doc, "insert", insert_then_boom)
            return doc

        sim_frappe.get_doc = partial_write_then_fail
        plan = adapter.call("plan", ctx(), {"artifact": art})["result"]
        out = adapter.call("apply", ctx(), {"idempotencyKey": "idemp_bpl027_off_apply_rr", "artifact": art,
                                            "planToken": plan["planToken"],
                                            "approvals": {"changeApproved": "01J00000000000000000000010"}})["result"]
        self.assertEqual(writes, ["wh_b"], "test precondition: DB write must have happened before raising")
        self.assertEqual(out["status"], "recovery_required", out)
        self.assertEqual(out["site"]["state"], "recovery_required", out)
        self.assertTrue(rollbacks, "execute_step must call f.db.rollback() when a step raises")

    def test_warehouse_lookup_fails_closed_on_zero_or_multiple_companies_and_disable_noops_without_company(self) -> None:
        """Fail closed on 0 or >1 companies unless named; location.disable is a documented no-op when 0 companies exist."""
        calls = []
        meta = SimpleNamespace(get_field=lambda name: SimpleNamespace(fieldname=name) if name == "company" else None)

        def stub(companies, existing, default_company=None):
            db = SimpleNamespace(
                get_value=lambda dt, flt, field: calls.append(flt) or existing,
                set_value=lambda *a, **kw: calls.append(("set_value", a)),
                commit=lambda: None,
                rollback=lambda: None,
                sql=lambda *a, **kw: [(1,)],
            )
            return SimpleNamespace(
                get_meta=lambda dt: meta,
                get_all=lambda dt, **kw: list(companies),
                defaults=SimpleNamespace(get_global_default=lambda key: default_company),
                db=db,
            )

        backend = make_frappe_adapter(simulated=True).frappe_backend

        # 0 companies: upsert fails closed (site_not_ready, side_effect_free=True)
        with self.assertRaises(FrappeBackendError) as err:
            backend._find_warehouse(stub([], None), "wh_riyadh", require_company=True)
        self.assertEqual(err.exception.code, "site_not_ready")
        self.assertTrue(err.exception.side_effect_free)

        # 0 companies: location.disable is a safe no-op (no company-scoped warehouse can exist)
        self.assertEqual(backend._find_warehouse(stub([], None), "wh_riyadh", require_company=False), (None, None))
        zero_co_backend = make_frappe_adapter(simulated=True).frappe_backend
        zero_co_backend._frappe_factory = lambda: stub([], None)
        zero_co_backend.execute_step(
            TENANT,
            {"kind": "location.disable", "pointer": "/locations/wh_riyadh", "subject": {"kind": "location", "id": "wh_riyadh"}, "params": {}},
        )

        # >1 companies without explicit company: fails closed even if global default is set
        with self.assertRaises(FrappeBackendError) as err_multi:
            backend._find_warehouse(stub(["Alpha Co", "Beta Co"], None, default_company="Alpha Co"), "wh_riyadh", require_company=True)
        self.assertEqual(err_multi.exception.code, "site_not_ready")
        self.assertTrue(err_multi.exception.side_effect_free)

        with self.assertRaises(FrappeBackendError) as err_multi_dis:
            backend._find_warehouse(stub(["Alpha Co", "Beta Co"], None, default_company="Alpha Co"), "wh_riyadh", require_company=False)
        self.assertEqual(err_multi_dis.exception.code, "site_not_ready")

        # >1 companies WITH explicit company: selects the named company (or fails closed if unknown)
        self.assertEqual(
            backend._find_warehouse(stub(["Alpha Co", "Beta Co"], "wh_riyadh - BC"), "wh_riyadh", company_name="Beta Co"),
            ("wh_riyadh - BC", "Beta Co"),
        )
        self.assertEqual(calls[-1], {"warehouse_name": "wh_riyadh", "company": "Beta Co"})
        with self.assertRaises(FrappeBackendError) as err_unknown:
            backend._find_warehouse(stub(["Alpha Co", "Beta Co"], None), "wh_riyadh", company_name="Gamma Co")
        self.assertEqual(err_unknown.exception.code, "site_not_ready")

        # Exactly 1 company: uses that sole company
        self.assertEqual(backend._find_warehouse(stub(["Synthetic Co"], "wh_riyadh - SC"), "wh_riyadh"),
                         ("wh_riyadh - SC", "Synthetic Co"))
        self.assertEqual(calls[-1], {"warehouse_name": "wh_riyadh", "company": "Synthetic Co"})


@unittest.skipIf(bench_skip_reason() is not None, bench_skip_reason() or "")
class TestBpl027FixtureRealAdapter(unittest.TestCase):
    """End to end on a real bench site. Tests run in name order and share one site."""

    state: dict = {}

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp.name, "adapter.sqlite")
        cls.bp_raw = load_fixture()
        cls.bp_full = apply_ready(cls.bp_raw)
        cls.bp = cls.bp_full
        cls.art_raw = compile_for_adapter(cls.bp_raw)
        cls.art = compile_for_adapter(cls.bp)
        cls.art_builtin = compile_for_adapter(with_unmapped_builtin_role(cls.bp))
        cls.expected = expected_engine_config(cls.bp)
        cls.adapter = new_adapter(cls.db_path)
        ensure_synthetic_company()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def need(self, key: str) -> None:
        if key not in self.state:
            self.skipTest(f"earlier step did not reach {key!r}")

    def call(self, op: str, inp: dict, adapter: ChangeEngineAdapter | None = None) -> dict:
        return (adapter or self.adapter).call(op, ctx(), inp)

    def plan(self, art: dict) -> dict:
        res = self.call("plan", {"artifact": art})
        self.assertTrue(res["ok"], res)
        return res["result"]

    def _plan_preview_and_refuse_without_gate(self) -> None:
        plan = self.plan(self.art)
        self.assertEqual(plan["verdict"], "needs_gate_approval", plan)
        gated = {(s["seq"], s.get("reasonCode")) for s in plan["steps"] if s["disposition"] == "gated"}
        reasons = {r for _, r in gated}
        self.assertIn("unique_or_index", reasons)  # item_code, customer_code, supplier_code are unique
        self.assertIn("protected_subject", reasons)  # role.upsert is gated by the adapter
        self.assertFalse([s for s in plan["steps"] if s["disposition"] in ("blocked", "unsupported")], plan)
        preview = self.call("preview", {"artifact": self.art})
        self.assertTrue(preview["ok"], preview)
        self.assertEqual(preview["result"]["verdict"], "needs_gate_approval")
        before = fingerprint()
        refused = self.call("apply", {
            "idempotencyKey": "idemp_bpl027_apply_nogate",
            "artifact": self.art,
            "planToken": plan["planToken"],
            "approvals": {"changeApproved": "01J00000000000000000000010", "teamReviewed": "01J00000000000000000000012"},
        })
        self.assertEqual(refused["result"]["status"], "rejected", refused)
        self.assertEqual(refused["result"]["error"]["code"], "approval_missing")
        self.assertIn("/approvals/gateApproved", refused["result"]["error"]["details"]["fields"])
        self.assertEqual(fingerprint(), before, "a refused apply changed the site")
        self.state.update(plan=plan, predicted=preview["result"]["predictedExportHash"])

    def _apply_planned_artifact(self) -> None:
        res = self.call("apply", {
            "idempotencyKey": "idemp_bpl027_apply_v1",
            "artifact": self.art,
            "planToken": self.state["plan"]["planToken"],
            "approvals": {
                "changeApproved": "01J00000000000000000000010",
                "gateApproved": "01J00000000000000000000011",
                "teamReviewed": "01J00000000000000000000012",
            },
        })
        self.assertTrue(res["ok"], res)
        out = res["result"]
        failed = [s for s in out["steps"] if s["status"] != "applied"]
        self.assertEqual(out["status"], "applied", {"error": out.get("error"), "failed": failed[:3]})
        self.assertEqual(out["exportHash"], self.state["predicted"])
        self.state.update(applied=out)

    def test_01_provision_fresh_site_and_raw_fixture_is_refused(self) -> None:
        res = self.call("provision_site", {
            "idempotencyKey": "idemp_bpl027_provision",
            "engineTarget": self.art["engineTarget"],
            "blueprintId": self.art["blueprint"]["id"],
            "siteClass": "sandbox",
            "countryPack": "sa",
        })
        self.assertTrue(res["ok"], f"provision failed (is the site fresh?): {res}")
        raw = self.plan(self.art_raw)
        self.assertEqual(raw["verdict"], "rejected")
        bad = [s for s in raw["steps"] if s["disposition"] != "ok" and s.get("reasonCode") == "unsupported_value_type"]
        seqs = {s["seq"]: s["pointer"] for s in self.art_raw["steps"]}
        self.assertEqual([seqs[s["seq"]] for s in bad], ["/entities/purchase_invoice"])
        self.state["provisioned"] = True

    def test_01b_plan_allows_mapped_purchasing_grants_and_refuses_unmapped_builtins(self) -> None:
        """SEC-022 / BPL-032 after BPL-034: on a real site, plan lets role.upsert grants on Supplier, Price List and the
        purchase documents through (gated, never blocked), and still refuses a grant on a built-in DocType outside the
        reviewed mapping (Payment Entry) with protected_subject, before any write."""
        self.need("provisioned")
        before = fingerprint()
        mapped_plan = self.plan(self.art)
        self.assertEqual(mapped_plan["verdict"], "needs_gate_approval", mapped_plan)
        self.assertFalse([s for s in mapped_plan["steps"] if s["disposition"] in ("blocked", "unsupported")], mapped_plan)
        self.assertEqual(fingerprint(), before, "plan modified the site")

        plan = self.plan(self.art_builtin)
        self.assertEqual(plan["verdict"], "rejected", plan)
        blocked = [s for s in plan["steps"] if s["disposition"] == "blocked"]
        by_seq = {s["seq"]: s for s in self.art_builtin["steps"]}
        self.assertEqual([by_seq[s["seq"]]["pointer"] for s in blocked], ["/roles/payment_clerk"])
        self.assertEqual(blocked[0].get("reasonCode"), "protected_subject")
        self.assertEqual(fingerprint(), before, "plan modified the site")

    def test_02_plan_preview_and_ddl_gate_refuses_without_gate_approval(self) -> None:
        self.need("provisioned")
        self._plan_preview_and_refuse_without_gate()

    def test_03_apply_through_real_adapter(self) -> None:
        self.need("plan")
        self._apply_planned_artifact()

    def test_04_readback_roles_workflows_reports_locations_settings(self) -> None:
        """Compared case-insensitively: the engine matches record names without case (see test_04b)."""
        self.need("applied")
        exp, low = self.expected, (lambda items: sorted(tuple(str(x).lower() for x in i) if isinstance(i, tuple) else str(i).lower() for i in items))
        with site_db() as f:
            for role in exp["roles"]:
                self.assertEqual(f.db.get_value("Role", role, "disabled"), 0, role)
            for wf_id, want in exp["workflows"].items():
                wf = f.get_doc("Workflow", wf_id)
                self.assertEqual((wf.document_type, int(wf.is_active)), (want["doctype"], 1), wf_id)
                self.assertEqual(low(s.state for s in wf.states), low(want["states"]), wf_id)
                got = [(t.state, t.action, t.next_state, t.allowed) for t in wf.transitions]
                self.assertEqual(low(got), low(want["transitions"]), wf_id)
            for rep_id, want in exp["reports"].items():
                rep = f.get_doc("Report", rep_id)
                self.assertEqual(int(rep.disabled), 0, rep_id)
                if want["doctype"]:  # a report without an entity (stock_on_hand) has no Blueprint-defined doctype
                    self.assertEqual(rep.ref_doctype, want["doctype"], rep_id)
                self.assertEqual(low(r.role for r in rep.roles), low(want["roles"]), rep_id)
            for wh in exp["warehouses"]:
                rows = f.get_all("Warehouse", filters={"warehouse_name": wh}, fields=["name", "disabled"])
                self.assertEqual([int(r.disabled) for r in rows], [0], wh)
            sys_settings = f.get_doc("System Settings")
            self.assertEqual(
                (sys_settings.language, sys_settings.country, sys_settings.time_zone),
                ("ar", "Saudi Arabia", "Asia/Riyadh"),
            )

    def test_04b_engine_records_carry_adapter_owned_names(self) -> None:
        """SEC-022 (was BPL-027 finding 1): Blueprint role 'auditor' must become the managed 'bp-auditor', never the
        built-in 'Auditor', and state 'approved' 'bp-approved', never the built-in 'Approved' (ADR-0051). Fails only
        on a name that resolves to another record; existence of the records is checked in test_04."""
        self.need("applied")
        with site_db() as f:
            self.assertEqual(name_clashes(f, self.expected), [])

    def test_05_readback_entities_and_fields(self) -> None:
        """BPL-031 (was BPL-027 finding 2): every Blueprint entity is on the engine under the document type the
        mapping contract names (an entity without a mapping is an adapter-owned custom type), every Blueprint field
        is a native or custom field on it, and the adapter made no custom twin of a built-in type. Expected values
        come from contracts/examples/engine-mapping-*.json, not from the adapter's mapper. Fails only on a gap."""
        self.need("applied")
        with site_db() as f:
            self.assertEqual(entity_gaps(f, self.expected), {"missing": [], "duplicates": []})

    def test_06_readback_role_permissions(self) -> None:
        """BPL-032 (was BPL-027 finding 3): every grant the ADR-0051 table derives from the Blueprint is a rule on the
        managed role, nothing more, and hidden fields sit on levels the hiding role cannot read. Fails only on a
        missing, extra or mis-levelled managed rule."""
        self.need("applied")
        with site_db() as f:
            self.assertEqual(grant_gaps(f, self.bp), {"missing": [], "extra": [], "levels": []})

    def test_07_reapply_is_a_noop(self) -> None:
        self.need("applied")
        before = fingerprint()
        inp = {
            "idempotencyKey": "idemp_bpl027_apply_v1",
            "artifact": self.art,
            "planToken": self.state["plan"]["planToken"],
            "approvals": {"changeApproved": "01J00000000000000000000010", "gateApproved": "01J00000000000000000000011",
                          "teamReviewed": "01J00000000000000000000012"},
        }
        replay = self.call("apply", inp)
        self.assertEqual(replay["result"]["operationId"], self.state["applied"]["operationId"], replay)
        # A restarted adapter (empty local store) hydrates from the site and reports already_applied.
        fresh = new_adapter(os.path.join(self.tmp.name, "restarted.sqlite"))
        again = self.call("apply", {**inp, "idempotencyKey": "idemp_bpl027_apply_v1_again"}, adapter=fresh)
        self.assertEqual(again["result"]["status"], "already_applied", again)
        self.assertEqual(again["result"]["exportHash"], self.state["applied"]["exportHash"])
        self.assertEqual(fingerprint(), before, "re-apply changed the site")

    def test_08_incremental_change_rolls_back_to_prior_state(self) -> None:
        self.need("applied")
        v1_rev = self.art["blueprint"]["target"]
        v2_rev = {"hash": "sha256:" + "2" * 64, "revision": v1_rev["revision"] + 1}
        field = {"id": "delivery_notes", "type": "string", "labels": {"en": "Delivery notes", "ar": "ملاحظات التسليم"}}
        subject = {"kind": "field", "id": "delivery_notes", "parents": [{"kind": "entity", "id": "customer"}]}
        pointer = "/entities/customer/fields/delivery_notes"

        def art(kind, base, target, step_kind, phase, impact, ddl, check, inverse=None):
            step = {"seq": 1, "phase": phase, "kind": step_kind, "subject": subject, "pointer": pointer, "impact": impact,
                    "ddlImpact": ddl, "reversible": True, "params": {"definition": field}, "sourceOps": [pointer]}
            counts = dict.fromkeys(("cosmetic", "config", "data_shape", "destructive", "compliance", "access", "branding"), 0)
            counts[impact] = 1
            return seal({
                "artifactSchema": "0.1.0", "kind": kind, "compiler": self.art["compiler"],
                "blueprint": {"id": self.art["blueprint"]["id"], "base": base, "target": target, "diffHash": "sha256:" + "3" * 64},
                "engineTarget": self.art["engineTarget"], "components": self.art["components"], "steps": [step],
                "skippedOps": [], "postConditions": [{"id": "pc_001", "check": check, "pointer": pointer}],
                "risk": {"counts": counts, "total": 1, "maxImpact": impact, "needsDdlPlanGate": ddl != "none",
                         "touchesCompliance": False, "touchesAccess": False, "touchesLedgerOrTax": False,
                         "requiresTeamReview": False, "irreversibleSteps": 0},
                "inverse": inverse,
            })

        inverse = art("inverse", v2_rev, v1_rev, "field.quarantine", 15, "destructive", "none", "quarantined")
        fwd = art("forward", v1_rev, v2_rev, "field.add", 5, "data_shape", "additive", "exists", inverse)
        plan = self.plan(fwd)
        self.assertEqual(plan["verdict"], "auto_approved", plan)
        res = self.call("apply", {"idempotencyKey": "idemp_bpl027_apply_v2", "artifact": fwd,
                                  "planToken": plan["planToken"], "approvals": {"changeApproved": "01J00000000000000000000020"}})
        self.assertEqual(res["result"]["status"], "applied", res)
        with site_db() as f:
            cf = f.db.get_value("Custom Field", {"dt": "Customer", "fieldname": "custom_delivery_notes"}, "name")
            self.assertTrue(cf, "custom field not created")
            self.assertIn("custom_delivery_notes", f.db.get_table_columns("Customer"))
            self.assertFalse(f.get_meta("Customer").get_field("custom_delivery_notes").hidden)
        rb = self.call("rollback", {"idempotencyKey": "idemp_bpl027_rollback_v2", "forwardArtifact": fwd,
                                    "reason": "owner_request", "approvals": {"rollbackApproved": "01J00000000000000000000060"}})
        self.assertEqual(rb["result"]["status"], "applied", rb)
        self.assertEqual(rb["result"]["exportHash"], self.state["applied"]["exportHash"])
        self.assertEqual(rb["result"]["site"]["applied"], {"artifactId": self.art["artifactId"], "revision": v1_rev})
        with site_db() as f:
            meta_field = f.get_meta("Customer").get_field("custom_delivery_notes")
            self.assertTrue(meta_field.hidden, "rolled-back field still visible")
            self.assertFalse(meta_field.reqd)
            self.assertIn("custom_delivery_notes", f.db.get_table_columns("Customer"))  # soft quarantine keeps data


if __name__ == "__main__":
    unittest.main()
