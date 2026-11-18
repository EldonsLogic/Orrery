# Tool API

Version: 0.2.0
Status: draft
Owner: eldon

Contract 3. The typed actions the chat (and scheduled agents) may call. Tools are **generated per tenant from the Blueprint** and component manifests; nobody hand-writes a tool for one client. The model chooses a tool and fills arguments; code executes it. Principle 6: numbers come from code, words come from the model.

## 1. Tool definition format
Each tool is a JSON object (shown as YAML here for readability). The generator emits JSON.

```yaml
name: sales_order.create          # <entity>.<verb>
version: 1                        # integer, bumps when input/output shape changes
kind: write                       # read | write | admin
labels: {ar: "...", en: "Create a sales order"}
description: "..."                # shown to the model; generated, localised
entity: sales_order
requires:
  permission: {entity: sales_order, action: create}
  scope: from_caller              # always evaluated for the caller, never widened
approval:
  required: false                 # true if an approval rule matches (see section 5)
  rule: null
idempotency: required             # required for write/admin tools
input_schema: {...}               # JSON Schema generated from entity fields
output_schema: {...}
limits: {rate_per_minute: 30, max_rows: 200, token_budget_class: small}
effects: {ledger: false, tax: false, external_send: false}
source: {blueprint_revision: 12, component: core.sales_order@0.1.3}
```

## 2. Naming
- Pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`: `<entity or domain>.<verb>`.
- Standard verbs: `get`, `list`, `search`, `create`, `update`, `submit`, `cancel`, `transition` (workflow move; argument `transition_id`), `approve`, `reject`, `export`, `report.run`, `metric.query`.
- Platform tools (not entity-bound): `blueprint.propose_change`, `blueprint.explain_diff`, `approval.list_mine`, `approval.decide`, `report.run`, `metric.query`, `memory.note`, `help.explain`.
- Tool names are stable; a rename is a new tool plus a deprecation.

## 3. Per-tenant generation
1. Input: Blueprint revision N + resolved component manifests.
2. For each entity and each action permitted to at least one role: emit a tool. Fields become `input_schema` (types, required, enums from select options, link fields become ids with an `entity_ref` hint). Computed fields are never input; they appear in output only.
3. For each workflow transition: emit `<entity>.transition` options (one tool, `transition_id` enum).
4. For each report and metric visible to some role: `report.run`, `metric.query` with enums for allowed ids.
5. Components may contribute extra tools via `provides[].artifacts[type=tool]`.
6. The tool set is stored with the Blueprint revision; applying a new revision regenerates it atomically. The chat only sees tools its caller may use (filtered by role); the filter is a convenience, the check in section 4 is the guarantee.

### Example tools generated from `examples/blueprint-trading-minimal.json`

| Tool | Kind | Who may call | Notes |
|---|---|---|---|
| `customer.search` | read | owner, sales_rep, accountant | `credit_limit` is stripped from output for `sales_rep` (hiddenFields) |
| `sales_order.create` | write | owner, sales_rep | `subtotal` etc. are not inputs; totals come from the component function `core.sales.order_total` |
| `sales_order.transition` | write | per transition `allowedRoles` | `transition_id` in {submit_small, submit_large, approve_large, deliver, cancel_draft}; guard `total_amount < 50000` evaluated by code |
| `sales_order.transition` with `approve_large` | write | owner | `approval.required = true`, rule `large_order_approval`; self-approval refused |
| `sales_invoice.create` | write | accountant | `effects.ledger = true`, `effects.tax = true`; always `approval.required = true` for chat callers (agents draft, humans approve) |
| `metric.query` | read | by report visibility | `metric` enum: `sales.revenue`, `sales.order_count`, `sales.revenue_by_customer`, `finance.receivables_aging`, `sales.order_list` |
| `blueprint.propose_change` | admin | roles with `isAdmin` | Produces a diff, never applies directly |

Sample call and result:

```json
{
  "tool": "sales_order.transition",
  "idempotency_key": "01J...-uuid",
  "arguments": {"id": "SO-00017", "transition_id": "submit_large"},
  "caller": {"user_id": "u_123", "role_ids": ["sales_rep"], "tenant_id": "t_abc"}
}
```
```json
{
  "status": "ok",
  "result": {"id": "SO-00017", "state": "pending_approval", "total_amount": {"value": "61200.00", "currency": "SAR"}},
  "approval": {"id": "ap_881", "rule": "large_order_approval", "status": "pending", "approver_role": "owner"},
  "audit_id": "aud_..."
}
```
Money is a decimal string plus currency, never a float, and always comes from the engine.

## 4. Role and scope check (every call)
Executed by the tool API gateway in Part 4, before anything reaches the engine:
1. Authenticate the caller (tenant id + user id from the session, never from the request body).
2. Load the caller's roles for that tenant from identity. Roles supplied by the client are ignored. (Known prototype bug: CE-SEC-001.)
3. Check `requires.permission` against the Blueprint role permissions. Failure to load roles = **deny** (fail closed). (CE-SEC-002.)
4. Apply scope (branch, warehouse, own records) as a filter on every read and a check on every write.
5. Check field-level `hiddenFields` and `readOnlyFields`.
6. Evaluate approval rules. If one matches, create a pending approval instead of executing.
7. Check rate and budget limits.
8. Execute against the engine with the **user's own permissions**, not a service account that can do more.
9. Write the audit record and emit events.

The chat can never do anything the user could not do in the engine's own UI with the same role.

## 5. Approval-required flag
`approval.required` is computed at generation time from the Blueprint's approval rules and from platform policy: any tool with `effects.ledger`, `effects.tax` or `effects.external_send` is approval-required for agent callers by default. For human callers via chat, ledger/tax tools execute the same confirm step the UI would. The call returns `status: "pending_approval"` with the approval id; execution happens when an eligible approver decides. The approver cannot be the requester unless the rule allows self-approval.

## 6. Idempotency
- Write and admin tools require an `idempotency_key` (UUID or ULID, client-generated by the chat runtime per intended action).
- The gateway stores `(tenant, tool, key) -> result` for at least 24 hours. A repeat returns the stored result with `replayed: true` and performs no second effect.
- Same key with different arguments returns `idempotency_conflict`.

## 7. Error model
```json
{"status": "error", "error": {"code": "permission_denied", "message_key": "errors.permission_denied", "retryable": false, "details": {}}, "audit_id": "aud_..."}
```
| code | Meaning | Retryable |
|---|---|---|
| `invalid_arguments` | Failed input schema; `details` lists fields | yes, after fixing |
| `unknown_tool` | Not in this tenant's tool set | no |
| `permission_denied` | Role/scope/field check failed | no |
| `approval_required` | Call parked; see `approval` | no (wait) |
| `guard_failed` | Workflow guard not satisfied | no |
| `not_found` | Record missing or outside scope (indistinguishable on purpose) | no |
| `conflict` | Record changed since read (version mismatch) | yes, re-read |
| `idempotency_conflict` | Key reused with other arguments | no |
| `rate_limited` | Per user/tenant/tool limit | yes, after `retry_after_s` |
| `budget_exceeded` | AI or tool budget exhausted | no |
| `engine_error` | Engine rejected or failed | maybe |
| `internal_error` | Our bug | maybe |

`message_key` is an i18n key; the chat renders it in the user's language. Never put raw engine stack traces, SQL or other tenants' data in an error.

### 7.1 Domain errors (optional `domain` block)
A business failure may add a `domain` block. The top-level `code`, `message_key` and `retryable` stay as above (a client that ignores `domain` behaves exactly as before).
```json
{"status": "error", "error": {"code": "guard_failed", "message_key": "errors.guard_failed", "retryable": false, "details": {},
  "domain": {"code": "insufficient_stock", "params": {"item": "ITEM-0001", "warehouse": "Main-Store", "shortfall_qty": "12.5"}}}, "audit_id": "aud_..."}
```
- `domain.code` is an id from the versioned catalog [tool-api-error-catalog.json](tool-api-error-catalog.json) ([schema](tool-api-error-catalog.schema.json)). Each entry fixes its top-level class, `retryable`, typed `params` slots (type, max length; free text only if marked `escaped`), `message_key` `errors.domain.<id>`, English and Arabic `messages` with `{slot}` placeholders, a `review` state and an `owner_action`.
- **Messages come only from the catalog.** Engine text is never passed through. Params are validated against the slots, escaped and stripped of bidi controls when rendered; a locale without text falls back to English.
- An unmapped engine failure stays `engine_error` with **no** `domain`. A catalog code or params that fail validation produce `internal_error` with only a correlation id in `details`.
- The gateway maps engine failures to catalog ids (PLT-024); the catalog never names engine concepts.

| `domain.code` | Top-level class |
|---|---|
| `insufficient_stock`, `fiscal_period_closed`, `credit_limit_exceeded`, `document_not_submittable`, `negative_valuation_blocked` | `guard_failed` |
| `record_already_submitted`, `record_already_cancelled`, `linked_document_exists`, `stale_approval_state` | `conflict` |
| `duplicate_tax_id`, `required_field_missing`, `tax_registration_invalid` | `invalid_arguments` |
| `unbalanced_entry`, `currency_rate_missing` | `engine_error` |

`stale_approval_state` ties to the action-policy record revision: the record changed after approval was requested, so the approval must be re-reviewed. Decision: [ADR-0036](../docs/decisions/ADR-0036-tool-api-domain-errors.md).

## 8. Audit fields (every call, success or failure)
`audit_id`, `ts`, `tenant_id`, `user_id`, `role_ids`, `session_id`, `chat_turn_id`, `agent_id` (if any), `tool`, `tool_version`, `blueprint_revision`, `idempotency_key`, `arguments_hash` and redacted arguments, `status`, `error_code`, `approval_id`, `model_id` and `prompt_version` that proposed the call, `latency_ms`, `engine_refs` (ids of records touched). Written to the event stream as `tool.called` ([events.md](events.md)); immutable.

## 9. Rate and budget limits
- Per user, per tool, per tenant (token buckets). Defaults in `limits`, overridable by plan entitlements.
- `max_rows` caps list/search results; larger needs `report.run` with export.
- Agents have a run budget (calls, rows, AI cost) set in the agent definition ([ai-layer](../docs/architecture/ai-layer.md)). Exhaustion stops the run and raises `agent.budget_exceeded`.
- Write tools have a stricter default rate than read tools.

## 10. Safety rules for tool inputs
- Content read from customer tools or documents is untrusted. It reaches the model only as quoted data, and a tool call proposed while untrusted content is in context is flagged `tainted: true`; tainted write calls on ledger/tax/external-send tools always require human approval.
- Arguments are validated by schema before the role check, and re-validated by the engine adapter.
- No tool accepts SQL, code, formulas, URLs to fetch, API keys or role names from the caller.

## 11. Generator risk rules (fail closed)
These rules decide risk classes at generation time. Policy data lives in `services/operate/toolapi/policy.py`; the shared rules in `classify.py`. `check_tool_api` recomputes every entity tool from the same rules and refuses any difference.

**Entity class.** Each non-child entity is `plain`, `stock` or `ledger`. Interim source, until the reviewed component manifest supplies the class (a separate contract change with an ADR): a reviewed table of known entity ids; an unlisted id containing a ledger token (invoice, bill, receipt, voucher, entry, payment, payroll, ledger, journal and others in the table) is `ledger`; any other entity is refused with `TAPI-CLASS-001`. Unknown never means plain. A child table may not carry an entity of a higher class than its parent (`TAPI-CLASS-003`). Entity ids in the identity and permission domain (starting with user, role, permission, grant or agent, or containing a role, permission or grant token) are refused (`TAPI-DOMAIN-001`).

**Registry.** An optional registry is L0 configuration only. It must name its `source`; it may raise an entity class and add effects, never lower either (`TAPI-REGISTRY-002`). The definition set records `registry: {source, sha256}`, and the checker needs the same registry to recheck the set (`TAPI-REGISTRY-003`).

**Transitions.** A transition may carry an explicit `kind` (`advance`, `approve`, `reject`, `cancel`, `reversal`); an unknown kind is refused (`TAPI-TRANS-001`). A workflow has exactly one initial state (`TAPI-TRANS-002`). Name tokens in the transition id only add restriction: approval words (approve, approved, approval, authorise, sign off, accept, confirm, release and variants) make it an approval that no agent may create; reject words a rejection; cancel and reversal words (cancel, void, reverse, refund, write off, return, amend and variants) a cancel or reversal. On stock and ledger entities without an explicit kind, a transition with its own approval rule is an approval, and one that leaves a non-initial state or enters a final or cancel-named state is a reversal (R4, never agent-creatable). The one exception is discarding a record in the initial state into a cancel-named state (`cancel_draft`, R1): nothing in the initial state has posted. When several kinds apply the riskiest wins. A rule on `submit` also gates every move out of the initial state; a rule on `cancel` gates every cancel or reversal.

**Sensitive fields.** A field or relation is sensitive by its id tokens, its type or its link target: bank or payment target (iban, swift, bank account, account number, payment account, beneficiary), contact or recipient (email and phone types, email, phone, mobile, webhook) and access (admin, privilege, access level, password, credential). Sensitive fields never enter the generic `create` or `update`; each class gets its own protected tool `<entity>.update_bank_details`, `<entity>.update_contact_details` or `<entity>.update_access`, risk R4 and never agent-creatable. A create that must carry a required sensitive field is R4 as a whole. Inside a child table a sensitive field has no write path.

**Status fields.** On an entity with a workflow, a field with a status, state or workflow token is output only; `docstatus` and `workflow_state` are output only on every entity. The workflow is the only way to move a record.

**Arguments.** An argument name is split into `_`, `-` and camelCase tokens. It is refused (`TAPI-ARG-001`) when any token names a caller, role, tenant, user, owner, approver, scope, permission, grant, actor, agent or behalf, or when it is an actor phrase such as `approved_by` or `assigned_to`. Exceptions only through the reviewed `ARG_NAME_ALLOW` list, each with its reason.

**Reads and egress.** A `read` tool is always R0 (`TAPI-RISK-004`). `export` is egress: kind `write`, idempotency required, agent callers always need human approval. A field hidden from any role that may call `list` or `export` is not in the filter or order enum (`TAPI-HIDDEN-001`). `metric.query` `group_by` is an enum of the `groupBy` fields of visible reports.

**Checker.** `check_tool_api(set, registry)` recomputes entity class, kind, risk class, effects and agent flags for every entity tool and transition, and platform tool risk from `PLATFORM_RISK` (`TAPI-CLASS-002`, `TAPI-RISK-003`). `contentHash` is mandatory (`TAPI-HASH-002`). A hash is not a signature: a stored set is protected by where it is kept. A report filter without a field id is refused (`TAPI-INPUT-003`).
