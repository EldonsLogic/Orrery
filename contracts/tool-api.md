# Tool API

Version: 0.1.0
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
