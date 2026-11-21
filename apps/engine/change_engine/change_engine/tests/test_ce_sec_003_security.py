"""
CE-SEC-003 security regressions: no eval, Tier 0 cannot be overridden, fail closed on store
errors, site and roles only from the request context, tables only from a migration patch.
"""

import types
import unittest
from pathlib import Path

from change_engine.api import endpoints
from change_engine.guarded_apply import policy_store as store_module
from change_engine.guarded_apply.policy_enforcer import (
    POLICY_STORE_UNAVAILABLE,
    PolicyType,
    RuntimePolicy,
    RuntimePolicyViolation,
    evaluate_condition_expr,
    policy_catalog,
)
from change_engine.guarded_apply.policy_expression import PolicyExpressionError, parse_condition
from change_engine.guarded_apply.policy_store import PolicyStore, PolicyStoreError, get_current_site_id

APP_DIR = Path(__file__).resolve().parents[1]
ADMIN = ["System Manager"]


def _policy(policy_id="POLICY_SO_BIG_ORDER", condition="grand_total > 50000", tier=1):
    return RuntimePolicy(
        policy_id=policy_id,
        doctype="Sales Order",
        policy_type=PolicyType.INVARIANT_GUARD,
        governance_tier=tier,
        condition_expr=condition,
        required_role="Sales Manager",
        error_message="Large orders need a Sales Manager.",
    )


def _session_frappe(site="tenant_a.localhost", roles=("System Manager",)):
    f = types.SimpleNamespace()
    f.session = types.SimpleNamespace(user="admin@example.invalid")
    f.local = types.SimpleNamespace(site=site)
    f.get_roles = lambda _user: list(roles)
    return f


class _FailingDB:
    def sql(self, *args, **kwargs):
        raise RuntimeError("database unavailable")


class _RecordingDB:
    def __init__(self):
        self.queries = []

    def sql(self, query, params=None, as_dict=False):
        self.queries.append(" ".join(query.split()))
        return []


class TestConditionGrammar(unittest.TestCase):
    ESCAPES = [
        "__import__('os').system('true')",
        "().__class__.__bases__[0].__subclasses__()",
        "doc.__class__",
        "open('/etc/passwd')",
        "[x for x in items]",
        "(lambda: 1)()",
        "grand_total + 1 > 2",
        "items[0] == 1",
        "has_role(user_role)",
        "is_field_changed('a', 'b')",
        "grand_total is 5",
        "f'{grand_total}' == '1'",
        "_private == 1",
        "eval('1')",
    ]

    def test_escape_attempts_are_rejected(self):
        for expr in self.ESCAPES:
            with self.subTest(expr=expr):
                with self.assertRaises(PolicyExpressionError):
                    parse_condition(expr)

    def test_existing_conditions_still_parse(self):
        for expr in (
            "bypass_credit_limit_check == 1",
            "conversion_rate is not None and conversion_rate <= 0",
            "is_field_changed('conversion_rate') or is_field_changed('party_account_currency')",
            "override_gl_posting == 1 or (docstatus == 1 and (is_field_changed('debit_to') or is_field_changed('cost_center')))",
            "discount_percentage > 15",
            "custom_notes is not None",
            "status in ['Draft', 'Open'] and not has_role('Sales Manager')",
            "margin < -5",
        ):
            with self.subTest(expr=expr):
                parse_condition(expr)

    def test_evaluation(self):
        doc = {"doctype": "Sales Order", "grand_total": 60000, "status": "Draft"}
        self.assertTrue(evaluate_condition_expr("grand_total > 50000", doc, []))
        self.assertTrue(evaluate_condition_expr("status in ['Draft', 'Open']", doc, []))
        self.assertTrue(evaluate_condition_expr("has_role('Sales Manager')", doc, ["Sales Manager"]))
        self.assertTrue(evaluate_condition_expr("0 < grand_total < 70000", doc, []))

    def test_unevaluable_comparisons_raise(self):
        for expr, doc in (
            ("amount > 5", {}),
            ("amount < 5", {}),
            ("amount >= 5", {}),
            ("amount <= 5", {}),
            ("margin < 5", {"margin": None}),
            ("amount > 5", {"amount": "10"}),
            ("'Draft' in statuses", {"statuses": None}),
            ("'Draft' in statuses", {"statuses": 10}),
            ("'Draft' not in statuses", {"statuses": None}),
            ("not (amount > 5)", {}),
            ("0 < 1 < amount < 5", {}),
        ):
            with self.subTest(expr=expr, doc=doc):
                with self.assertRaises(PolicyExpressionError):
                    evaluate_condition_expr(expr, doc, [])

    def test_identity_comparisons_use_the_right_hand_literal(self):
        for expr, expected in (
            ("x is True", (True, False, False, False)),
            ("x is False", (False, True, False, False)),
            ("x is None", (False, False, True, False)),
            ("x is not None", (True, True, False, True)),
            ("x is not False", (True, False, True, True)),
        ):
            for x, matches in zip((True, False, None, 0), expected):
                with self.subTest(expr=expr, x=x):
                    self.assertIs(evaluate_condition_expr(expr, {"x": x}, []), matches)

    def test_missing_field_keeps_equality_semantics(self):
        self.assertTrue(evaluate_condition_expr("amount == None", {}, []))
        self.assertFalse(evaluate_condition_expr("amount != None", {}, []))
        self.assertFalse(evaluate_condition_expr("amount == 5", {}, []))
        self.assertTrue(evaluate_condition_expr("amount != 5", {}, []))

    def test_invalid_stored_condition_is_a_violation(self):
        """A condition that slipped into storage unvalidated denies, never allows."""
        bad = _policy(condition="__import__('os')")
        self.assertFalse(policy_catalog._evaluate_single_policy(bad, {"doctype": "Sales Order"}, "validate", []))


class TestTier0Protection(unittest.TestCase):
    def setUp(self):
        self._orig_frappe = endpoints.frappe
        policy_catalog.reset()

    def tearDown(self):
        endpoints.frappe = self._orig_frappe
        policy_catalog.reset()

    def test_builtin_tier0_id_cannot_be_registered(self):
        with self.assertRaises(PermissionError):
            endpoints.register_runtime_policy(
                _policy("TIER0_SO_CREDIT_LIMIT_BYPASS", "1 == 2"), caller_roles=ADMIN)

    def test_tier0_prefix_is_reserved(self):
        with self.assertRaises(PermissionError):
            policy_catalog.register_policy(_policy("tier0_custom"))

    def test_caller_cannot_set_governance_tier(self):
        data = {"policy_id": "POLICY_X", "doctype": "Sales Order", "policy_type": "INVARIANT_GUARD",
                "condition_expr": "grand_total > 1", "governance_tier": 0}
        with self.assertRaises(PermissionError):
            endpoints.register_runtime_policy(data, caller_roles=ADMIN)
        with self.assertRaises(PermissionError):
            policy_catalog.register_policy(_policy(tier=0))

    def test_stored_row_with_tier0_id_does_not_shadow_the_builtin(self):
        """Even if a row with a Tier 0 id reached the store, the built-in policy still applies."""
        with self.assertRaises(PermissionError):
            store_module.policy_store.save_policy(_policy("TIER0_SO_CREDIT_LIMIT_BYPASS", "1 == 2"))
        # Plant the row directly, as if it had reached the store some other way.
        store_module.policy_store._sites.setdefault("default", {})["TIER0_SO_CREDIT_LIMIT_BYPASS"] = \
            _policy("TIER0_SO_CREDIT_LIMIT_BYPASS", "1 == 2")
        doc = {"doctype": "Sales Order", "bypass_credit_limit_check": 1}
        result = policy_catalog.evaluate_validate(doc, user_roles=["Sales User"], raise_exception=False)
        self.assertIn("TIER0_SO_CREDIT_LIMIT_BYPASS", result.violated_policies)

    def test_tier0_cannot_be_unregistered(self):
        with self.assertRaises(PermissionError):
            endpoints.unregister_runtime_policy("TIER0_SI_GL_POSTING_PROTECTION", caller_roles=ADMIN)

    def test_registration_rejects_an_eval_escape(self):
        with self.assertRaises(PolicyExpressionError):
            endpoints.register_runtime_policy(_policy(condition="__import__('os')"), caller_roles=ADMIN)

    def test_registration_rejects_non_singleton_identity_operands(self):
        for condition in ("grand_total is 1", "grand_total is not 0", "grand_total is amount"):
            with self.subTest(condition=condition):
                with self.assertRaises(PolicyExpressionError):
                    endpoints.register_runtime_policy(_policy(condition=condition), caller_roles=ADMIN)

    def test_registration_needs_an_admin(self):
        with self.assertRaises(PermissionError):
            endpoints.register_runtime_policy(_policy())


class TestRequestContext(unittest.TestCase):
    def setUp(self):
        self._orig_frappe = endpoints.frappe
        policy_catalog.reset()

    def tearDown(self):
        endpoints.frappe = self._orig_frappe
        policy_catalog.reset()

    def test_caller_supplied_site_is_refused(self):
        endpoints.frappe = _session_frappe()
        with self.assertRaises(PermissionError):
            endpoints.register_runtime_policy(_policy(), site_id="tenant_b.localhost")
        with self.assertRaises(PermissionError):
            get_current_site_id("tenant_b.localhost")
        self.assertEqual(get_current_site_id(), "tenant_a.localhost")

    def test_caller_supplied_roles_are_refused(self):
        endpoints.frappe = _session_frappe(roles=("Sales User",))
        with self.assertRaises(PermissionError):
            endpoints.evaluate_document_policies("Sales Order", {"grand_total": 1}, user_roles=["System Manager"])
        with self.assertRaises(PermissionError):
            endpoints.register_runtime_policy(_policy(), caller_roles=["System Manager"])

    def test_session_roles_decide(self):
        endpoints.frappe = _session_frappe(roles=("Sales User",))
        with self.assertRaises(PermissionError):
            endpoints.register_runtime_policy(_policy())
        endpoints.frappe = _session_frappe(roles=("System Manager",))
        self.assertTrue(endpoints.register_runtime_policy(_policy())["success"])

    def test_policies_stay_on_their_site(self):
        endpoints.frappe = _session_frappe(site="tenant_a.localhost")
        endpoints.register_runtime_policy(_policy())
        doc = {"doctype": "Sales Order", "grand_total": 60000}
        on_a = policy_catalog.evaluate_validate(doc, user_roles=[], raise_exception=False)
        self.assertIn("POLICY_SO_BIG_ORDER", on_a.violated_policies)
        endpoints.frappe = _session_frappe(site="tenant_b.localhost")
        on_b = policy_catalog.evaluate_validate(doc, user_roles=[], raise_exception=False)
        self.assertNotIn("POLICY_SO_BIG_ORDER", on_b.violated_policies)


class TestFailClosed(unittest.TestCase):
    def setUp(self):
        self._orig_store = store_module.policy_store
        policy_catalog.reset()

    def tearDown(self):
        store_module.policy_store = self._orig_store
        policy_catalog.reset()

    def test_read_errors_raise(self):
        store = PolicyStore(frappe_module=types.SimpleNamespace(db=_FailingDB()))
        with self.assertRaises(PolicyStoreError):
            store.get_policies(doctype="Sales Order")
        with self.assertRaises(PolicyStoreError):
            store.get_policy("POLICY_X")
        with self.assertRaises(PolicyStoreError):
            store.get_audit_trail()

    def test_store_failure_denies_enforcement(self):
        store_module.policy_store = PolicyStore(frappe_module=types.SimpleNamespace(db=_FailingDB()))
        doc = {"doctype": "Sales Order", "grand_total": 1}
        result = policy_catalog.evaluate_validate(doc, user_roles=[], raise_exception=False)
        self.assertFalse(result.allowed)
        self.assertEqual(result.violated_policies, [POLICY_STORE_UNAVAILABLE])
        with self.assertRaises(RuntimePolicyViolation):
            policy_catalog.evaluate_submit(doc, user_roles=[])

    def test_threshold_gate_with_missing_field_denies_validation(self):
        doc = {"doctype": "Sales Order"}
        for condition, role in (
            ("grand_total > 50000", "Sales User"),
            ("not (grand_total > 5000)", "Sales Manager"),
        ):
            with self.subTest(condition=condition, role=role):
                policy = RuntimePolicy(
                    policy_id="POLICY_ORDER_THRESHOLD",
                    doctype="Sales Order",
                    policy_type=PolicyType.THRESHOLD_GATE,
                    condition_expr=condition,
                    required_role="Sales Manager",
                )
                endpoints.register_runtime_policy(policy, caller_roles=ADMIN)
                with self.assertRaises(RuntimePolicyViolation) as violation:
                    policy_catalog.evaluate_validate(doc, user_roles=[role])
                self.assertEqual(violation.exception.policy_id, policy.policy_id)

    def test_revision_does_not_restart_after_a_read_failure(self):
        store = PolicyStore(frappe_module=types.SimpleNamespace(db=_FailingDB()))
        with self.assertRaises(PolicyStoreError):
            store.save_policy(_policy())

    def test_revision_read_locks_the_row(self):
        db = _RecordingDB()
        store = PolicyStore(frappe_module=types.SimpleNamespace(db=db))
        store.save_policy(_policy())
        self.assertTrue(db.queries[0].startswith("SELECT"))
        self.assertTrue(db.queries[0].endswith("FOR UPDATE"))
        self.assertFalse(any("CREATE TABLE" in q for q in db.queries))


class TestMigration(unittest.TestCase):
    def test_fresh_install_creates_policy_tables_before_model_sync(self):
        from change_engine import hooks
        self.assertEqual(
            hooks.before_install,
            "change_engine.patches.ce_sec_003_create_policy_tables.execute",
        )

    def test_tables_come_from_a_registered_patch(self):
        patches = (APP_DIR / "patches.txt").read_text().splitlines()
        self.assertIn("change_engine.patches.ce_sec_003_create_policy_tables", patches)
        self.assertLess(
            patches.index("change_engine.patches.ce_sec_003_create_policy_tables"),
            patches.index("[post_model_sync]"),
            "Policy tables must exist before document validation during model sync",
        )
        patch = (APP_DIR / "patches" / "ce_sec_003_create_policy_tables.py").read_text()
        self.assertIn("CREATE TABLE IF NOT EXISTS", patch)
        store_src = (APP_DIR / "guarded_apply" / "policy_store.py").read_text()
        self.assertNotIn("CREATE TABLE", store_src)


class TestReviewFollowUps(unittest.TestCase):
    """Findings from the different-model review of the first fix."""

    def setUp(self):
        self._orig_frappe = endpoints.frappe
        policy_catalog.reset()

    def tearDown(self):
        endpoints.frappe = self._orig_frappe
        policy_catalog.reset()

    def test_store_refuses_to_delete_a_tier0_row(self):
        store = store_module.policy_store
        store._sites.setdefault("default", {})["TIER0_SO_CREDIT_LIMIT_BYPASS"] = _policy("TIER0_SO_CREDIT_LIMIT_BYPASS")
        with self.assertRaises(PermissionError):
            store.delete_policy("TIER0_SO_CREDIT_LIMIT_BYPASS")
        self.assertIn("TIER0_SO_CREDIT_LIMIT_BYPASS", store._sites["default"])

    def test_frappe_context_without_session_is_not_standalone(self):
        f = types.SimpleNamespace(session=None, local=types.SimpleNamespace(site="tenant_a.localhost"),
                                  get_roles=lambda _u: ["System Manager"])
        endpoints.frappe = f
        with self.assertRaises(PermissionError):
            endpoints.register_runtime_policy(_policy(), caller_roles=["System Manager"])
        with self.assertRaises(PermissionError):
            endpoints.get_runtime_policies(doctype="Sales Order")

    def test_frappe_runtime_without_db_interface_fails_closed(self):
        broken = types.SimpleNamespace(db=types.SimpleNamespace(), local=types.SimpleNamespace(site="tenant_a.localhost"))
        store = PolicyStore(frappe_module=broken)
        for call in (lambda: store.get_policies(doctype="Sales Order"), lambda: store.get_policy("X"),
                     lambda: store.get_audit_trail(), lambda: store.save_policy(_policy())):
            with self.assertRaises(PolicyStoreError):
                call()

    def test_creation_does_not_upsert(self):
        """A new policy is a plain INSERT, so a concurrent creation fails instead of overwriting."""
        db = _RecordingDB()
        PolicyStore(frappe_module=types.SimpleNamespace(db=db)).save_policy(_policy())
        insert = next(q for q in db.queries if q.startswith("INSERT INTO `tabChange Engine Policy`"))
        self.assertNotIn("ON DUPLICATE KEY UPDATE", insert)


if __name__ == "__main__":
    unittest.main()
