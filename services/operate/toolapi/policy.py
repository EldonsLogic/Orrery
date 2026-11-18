"""Policy tables. Data only: change a risk class, an effect or a label here, not in the generator.

Risk classes follow docs/security/action-policy-table.md section 4:
R0 read or draft; R1 record change; R2 stock movement or ledger posting from an operational document;
R3 direct ledger posting, external send, money movement; R4 reversal of posted history, permission change,
Blueprint publish. Agents never get an R4 tool (ALP-029, prompt-injection-defence 4.5).
"""
from __future__ import annotations

RISK_ORDER = ("R0", "R1", "R2", "R3", "R4")

# --- entity classes --------------------------------------------------------------------------------------------
# The Blueprint has no "posts to the ledger" flag yet. Interim rule (fail closed), until the reviewed component
# manifest supplies the class: an entity id listed below has that class; an unlisted id with a ledger token (see
# LEDGER_NAME_TOKENS) is "ledger"; any other non-child entity is refused (TAPI-CLASS-001). Unknown never means plain.
# The lookup lives in classify.default_entity_class, the single point to replace by the manifest.
ENTITY_CLASSES = {"plain", "stock", "ledger"}
CLASS_RANK = {"plain": 0, "stock": 1, "ledger": 2}
# Reviewed: masters and documents that never post to the ledger or move stock themselves.
KNOWN_PLAIN = (
    "customer", "supplier", "item", "price_list", "sales_quote", "sales_order", "purchase_order",  # fixtures
    "quotation", "supplier_quotation", "request_for_quotation", "material_request", "lead", "opportunity",
    "project", "task", "warehouse", "uom", "brand", "item_group", "customer_group", "supplier_group",
    "bank_account", "bill_of_materials",
)
# Reviewed: documents that move stock (and post its value).
KNOWN_STOCK = ("delivery_note", "purchase_receipt", "stock_transfer", "stock_entry", "stock_reconciliation", "goods_receipt")
# Reviewed: documents that post to the ledger, move money or run payroll.
KNOWN_LEDGER = (
    "sales_invoice", "purchase_invoice", "credit_note", "debit_note", "payment", "payment_entry", "journal_entry",
    "pos_invoice", "expense_claim", "payroll_entry", "salary_slip", "landed_cost_voucher", "period_closing_voucher",
    "payment_request", "bank_transaction",
)
ENTITY_CLASS_DEFAULTS = {**{e: "plain" for e in KNOWN_PLAIN}, **{e: "stock" for e in KNOWN_STOCK},
                         **{e: "ledger" for e in KNOWN_LEDGER}}
# An unlisted (tenant-named) entity id containing one of these "_" tokens is ledger class.
LEDGER_NAME_TOKENS = {
    "invoice", "invoices", "bill", "bills", "receipt", "receipts", "voucher", "vouchers", "entry", "entries",
    "payment", "payments", "payroll", "ledger", "journal", "salary", "payslip", "expense", "expenses", "refund",
    "credit", "debit", "tax", "vat", "depreciation", "settlement", "remittance", "payout", "disbursement", "cheque",
    "pos", "stock", "inventory", "delivery", "shipment", "dispatch", "transfer", "adjustment", "reconciliation",
    "closing", "accrual", "provision", "cash",
}
# Entity ids in the identity and permission domain are never generated (AP-PERM-01, ALP-011): refused.
IDENTITY_ENTITY_PREFIXES = ("user", "role", "permission", "grant", "agent")
IDENTITY_ENTITY_TOKENS = {"role", "roles", "permission", "permissions", "grant", "grants", "privilege", "privileges", "acl"}
# Extra effects beyond the class. ledger is implied by class stock and ledger.
ENTITY_EFFECT_DEFAULTS = {
    "sales_invoice": {"tax": True, "external_send": True},
    "credit_note": {"tax": True, "external_send": True},
    "debit_note": {"tax": True, "external_send": True},
    "pos_invoice": {"tax": True, "external_send": True},
    "purchase_invoice": {"tax": True},
}
EFFECT_KEYS = ("ledger", "tax", "external_send")

# --- risk by (entity class, verb kind) -------------------------------------------------------------------------
# Verb kinds: get list export create update submit cancel delete, the protected update_* verbs, and for workflow
# transitions: advance approve reject cancel reversal (leaving a non-initial state) cancel_draft (discarding a
# record in the initial state into a cancel-named state).
# Writes that touch a sensitive field (bank target, contact, access) are their own R4 tool (policy table section 4,
# prompt-injection-defence 5.1). A create that must carry a required sensitive field is R4 as a whole.
SENSITIVE_VERBS = {"bank_details": "update_bank_details", "contact_details": "update_contact_details",
                   "access": "update_access"}
_PROTECTED = {v: "R4" for v in SENSITIVE_VERBS.values()}
RISK = {
    "plain": {"get": "R0", "list": "R0", "export": "R1", "create": "R1", "update": "R1", "submit": "R1",
              "cancel": "R2", "delete": "R3", "advance": "R1", "approve": "R2", "reject": "R1",
              "cancel_draft": "R1", "reversal": "R2", **_PROTECTED},
    "stock": {"get": "R0", "list": "R0", "export": "R1", "create": "R1", "update": "R1", "submit": "R2",
              "cancel": "R4", "delete": "R4", "advance": "R2", "approve": "R3", "reject": "R2",
              "cancel_draft": "R1", "reversal": "R4", **_PROTECTED},
    "ledger": {"get": "R0", "list": "R0", "export": "R2", "create": "R1", "update": "R1", "submit": "R3",
               "cancel": "R4", "delete": "R4", "advance": "R3", "approve": "R3", "reject": "R2",
               "cancel_draft": "R1", "reversal": "R4", **_PROTECTED},
}
# Single source for platform tool risk; the generator and the checker both read it.
PLATFORM_RISK = {"report.run": "R0", "metric.query": "R0", "approval.list_mine": "R0",
                 "approval.decide": "R3", "blueprint.propose_change": "R4"}

# Verbs an agent may never call, whatever the risk (agents never approve or reject: ALP, PI-017).
AGENT_FORBIDDEN_KINDS = {"approve", "reject"}
AGENT_FORBIDDEN_TOOLS = {"approval.decide", "blueprint.propose_change"}
MAX_AGENT_RISK = "R3"

# --- transition kind ------------------------------------------------------------------------------------------------
# The Blueprint has no transition kind yet. A transition may carry an explicit `kind` (one of TRANSITION_KINDS); name
# tokens from the id only ever add restriction. On stock and ledger entities, without an explicit kind, a transition
# that has its own approval rule is an approval, and one that leaves a non-initial state or enters a final or
# cancel-named state is a reversal (R4), except discarding a record in the initial state into a cancel-named state.
TRANSITION_KINDS = ("advance", "approve", "reject", "cancel", "reversal")
APPROVE_TOKENS = {"approve", "approved", "approval", "authorise", "authorize", "authorised", "authorized", "accept",
                  "accepted", "confirm", "confirmed", "release", "released", "signoff"}
APPROVE_PHRASES = (("sign", "off"),)
REJECT_TOKENS = {"reject", "rejected", "decline", "declined", "deny", "denied"}
CANCEL_TOKENS = {"cancel", "cancelled", "canceled"}
REVERSAL_TOKENS = {"void", "voided", "reverse", "reversed", "reversal", "refund", "refunded", "return", "returned",
                   "amend", "amended", "writeoff", "unpost", "reopen", "undo", "rollback"}
REVERSAL_PHRASES = (("write", "off"), ("written", "off"))
# A state whose id has one of these tokens is a cancel-named state.
CANCEL_STATE_TOKENS = CANCEL_TOKENS | REVERSAL_TOKENS | {"discarded", "deleted", "closed_lost"}
# When several kinds apply, the one with the highest risk wins; ties go to the first in this order.
KIND_PRECEDENCE = ("cancel", "reversal", "approve", "reject", "advance", "cancel_draft")

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
    "export": {"rate_per_minute": 10, "max_rows": 10000},
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
    "update_bank_details": {"ar": "تعديل البيانات البنكية", "en": "Change bank details of"},
    "update_contact_details": {"ar": "تعديل بيانات التواصل", "en": "Change contact details of"},
    "update_access": {"ar": "تعديل الصلاحيات", "en": "Change access of"},
}

# --- names ----------------------------------------------------------------------------------------------------------
PLATFORM_DOMAINS = {"blueprint", "approval", "report", "metric", "memory", "help"}
# Argument names a tool never accepts. A name is split into "_", "-" and camelCase tokens; it is refused when any
# token is in FORBIDDEN_ARG_TOKENS, when two adjacent tokens form a FORBIDDEN_ARG_PHRASE, or when the whole name
# with separators removed is in FORBIDDEN_ARG_NAMES (PI-RULE-4: no text chooses an approver or names a role).
FORBIDDEN_ARG_NAMES = {"caller", "role", "roles", "roleid", "roleids", "tenant", "tenantid", "userid", "scope"}
FORBIDDEN_ARG_TOKENS = {
    "caller", "callers", "role", "roles", "tenant", "tenants", "user", "users", "owner", "owners", "approver",
    "approvers", "scope", "scopes", "permission", "permissions", "grant", "grants", "actor", "actors", "agent",
    "agents", "behalf", "userid", "tenantid", "roleid", "roleids", "impersonate", "sudo",
}
_ACTOR_VERBS = ("approved", "created", "modified", "updated", "owned", "assigned", "requested", "submitted", "decided",
                "signed", "authorised", "authorized", "reviewed", "verified", "posted", "cancelled", "run")
FORBIDDEN_ARG_PHRASES = tuple((v, w) for v in _ACTOR_VERBS for w in ("by", "to"))
# Reviewed exceptions: exact names allowed although a token matches. Each entry needs a reason in a comment.
# (None yet. Add an entry only with a reviewed reason; never for a name that selects a person, role or tenant.)
ARG_NAME_ALLOW = frozenset()
# Names the generator itself puts in an input or output schema; a Blueprint field may not reuse them.
RESERVED_ARG_NAMES = {"id", "version", "expected_version", "state"}
# --- field sensitivity ----------------------------------------------------------------------------------------------
# A field (or relation) is sensitive when its id, its field type or its link target matches. Order is precedence.
SENSITIVE_CLASSES = ("bank_details", "access", "contact_details")
SENSITIVE_TOKENS = {
    "bank_details": {"iban", "swift", "bic", "beneficiary", "routing"},
    "access": {"admin", "administrator", "privilege", "privileges", "access", "superuser", "password", "credential",
               "credentials", "secret", "apikey"},
    "contact_details": {"email", "emails", "phone", "phones", "mobile", "whatsapp", "fax", "webhook", "msisdn"},
}
SENSITIVE_PHRASES = {
    "bank_details": (("bank", "account"), ("account", "number"), ("account", "no"), ("payment", "account"),
                     ("sort", "code"), ("bank", "details")),
    "access": (("api", "key"), ("access", "level")),
    "contact_details": (("e", "mail"), ("notify", "to"), ("send", "to")),
}
SENSITIVE_FIELD_TYPES = {"email": "contact_details", "phone": "contact_details"}
# --- status-like fields -----------------------------------------------------------------------------------------------
# On an entity with a workflow, a field with one of these tokens is output only (the workflow is the only way to move
# the record). On every entity, these exact ids are output only.
WORKFLOW_STATUS_TOKENS = {"status", "state", "docstatus", "workflow"}
ENGINE_STATUS_FIELDS = {"docstatus", "workflow_state"}

# Engine names must not appear anywhere in a definition (ADR-0016).
ENGINE_NAMES = ("frappe", "erpnext")

# --- field type -> schema (names only; shapes are built in schema.py) -----------------------------------------
FIELD_TYPES = ("string", "text", "integer", "decimal", "money", "percent", "boolean", "date", "datetime",
               "select", "link", "attachment", "phone", "email")
DEFAULT_TEXT_MAX = 10000
DEFAULT_STRING_MAX = 255
DEFAULT_PRECISION = 6
ID_PATTERN = "^[A-Za-z0-9][A-Za-z0-9_./-]{0,63}$"
