"""Policy tables. Data only: change a risk class, an effect or a label here, not in the generator.

Risk classes follow docs/security/action-policy-table.md section 4:
R0 read or draft; R1 record change; R2 stock movement or ledger posting from an operational document;
R3 direct ledger posting, external send, money movement; R4 reversal of posted history, permission change,
Blueprint publish. Agents never get an R4 tool (ALP-029, prompt-injection-defence 4.5).
"""
from __future__ import annotations

RISK_ORDER = ("R0", "R1", "R2", "R3", "R4")

# --- entity classes --------------------------------------------------------------------------------------------
# The Blueprint has no "posts to the ledger" flag, so classes are keyed by entity id here. An entity that is not
# listed is "plain" (lowest risk). A registry may add or override entries (see generate_tool_api).
ENTITY_CLASSES = {"plain", "stock", "ledger"}
ENTITY_CLASS_DEFAULTS = {
    "sales_invoice": "ledger",
    "purchase_invoice": "ledger",
    "credit_note": "ledger",
    "payment": "ledger",
    "delivery_note": "stock",
    "purchase_receipt": "stock",
    "stock_transfer": "stock",
}
# Extra effects beyond the class. ledger is implied by class stock and ledger.
ENTITY_EFFECT_DEFAULTS = {
    "sales_invoice": {"tax": True, "external_send": True},
    "credit_note": {"tax": True, "external_send": True},
    "purchase_invoice": {"tax": True},
}
EFFECT_KEYS = ("ledger", "tax", "external_send")

# --- risk by (entity class, verb kind) -------------------------------------------------------------------------
# Verb kinds: get list export create update submit cancel delete, and for workflow transitions:
# advance approve reject cancel (from a non-initial state) cancel_draft (cancel from the initial state).
RISK = {
    "plain": {"get": "R0", "list": "R0", "export": "R1", "create": "R1", "update": "R1", "submit": "R1",
              "cancel": "R2", "delete": "R3", "advance": "R1", "approve": "R2", "reject": "R1",
              "cancel_draft": "R1"},
    "stock": {"get": "R0", "list": "R0", "export": "R1", "create": "R1", "update": "R1", "submit": "R2",
              "cancel": "R4", "delete": "R4", "advance": "R2", "approve": "R3", "reject": "R2",
              "cancel_draft": "R1"},
    "ledger": {"get": "R0", "list": "R0", "export": "R2", "create": "R1", "update": "R1", "submit": "R3",
               "cancel": "R4", "delete": "R4", "advance": "R3", "approve": "R3", "reject": "R2",
               "cancel_draft": "R1"},
}
PLATFORM_RISK = {"report.run": "R0", "metric.query": "R0", "approval.list_mine": "R0",
                 "approval.decide": "R3", "blueprint.propose_change": "R4"}

# Verbs an agent may never call, whatever the risk (agents never approve or reject: ALP, PI-017).
AGENT_FORBIDDEN_KINDS = {"approve", "reject"}
AGENT_FORBIDDEN_TOOLS = {"approval.decide", "blueprint.propose_change"}
MAX_AGENT_RISK = "R3"

# --- transition kind from the transition id (token match, first hit wins) ---------------------------------------
TRANSITION_TOKENS = (("approve", "approve"), ("reject", "reject"), ("cancel", "cancel"))

# --- Blueprint permission action -> tool verbs ---------------------------------------------------------------------
PERMISSION_VERBS = {
    "read": ("get", "list"), "create": ("create",), "update": ("update",), "delete": ("delete",),
    "submit": ("submit",), "cancel": ("cancel",), "export": ("export",),
}
# Verbs replaced by workflow transitions when the entity has a workflow.
WORKFLOW_REPLACES = {"submit", "cancel"}
# Approval rule appliesTo.action -> verbs it gates. chat_action gates every write verb of the entity.
WRITE_VERBS = ("create", "update", "submit", "cancel", "delete", "transition")
APPROVAL_ACTION_VERBS = {
    "submit": ("submit",), "cancel": ("cancel",), "update": ("update",), "delete": ("delete",),
    "payment": ("create", "submit"), "chat_action": WRITE_VERBS,
}

# --- limits (contract section 9): writes stricter than reads --------------------------------------------------
LIMITS = {
    "read": {"rate_per_minute": 120, "max_rows": 200},
    "write": {"rate_per_minute": 30, "max_rows": 0},
    "admin": {"rate_per_minute": 10, "max_rows": 0},
}
MEDIUM_BUDGET_VERBS = {"list", "export", "report.run", "metric.query"}

# --- display labels (never used for ids) -------------------------------------------------------------------------
VERB_LABELS = {
    "get": {"ar": "عرض", "en": "View"}, "list": {"ar": "قائمة", "en": "List"},
    "create": {"ar": "إنشاء", "en": "Create"}, "update": {"ar": "تعديل", "en": "Update"},
    "delete": {"ar": "حذف", "en": "Delete"}, "submit": {"ar": "تقديم", "en": "Submit"},
    "cancel": {"ar": "إلغاء", "en": "Cancel"}, "export": {"ar": "تصدير", "en": "Export"},
    "transition": {"ar": "نقل حالة", "en": "Move"},
}

# --- names ----------------------------------------------------------------------------------------------------------
PLATFORM_DOMAINS = {"blueprint", "approval", "report", "metric", "memory", "help"}
# Argument names a tool never accepts (compared after lower-casing and removing "_" and "-").
FORBIDDEN_ARG_NAMES = {"caller", "role", "roles", "roleid", "roleids", "tenant", "tenantid", "userid", "scope"}
# Names the generator itself puts in an input or output schema; a Blueprint field may not reuse them.
RESERVED_ARG_NAMES = {"id", "version", "expected_version", "state"}
# Engine names must not appear anywhere in a definition (ADR-0016).
ENGINE_NAMES = ("frappe", "erpnext")

# --- field type -> schema (names only; shapes are built in schema.py) -----------------------------------------
FIELD_TYPES = ("string", "text", "integer", "decimal", "money", "percent", "boolean", "date", "datetime",
               "select", "link", "attachment", "phone", "email")
DEFAULT_TEXT_MAX = 10000
DEFAULT_STRING_MAX = 255
DEFAULT_PRECISION = 6
ID_PATTERN = "^[A-Za-z0-9][A-Za-z0-9_./-]{0,63}$"
