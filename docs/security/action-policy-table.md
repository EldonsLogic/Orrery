# Action-policy table

Status: accepted for Q-41, Q-42 and Q-43 (Eldon, 2026-11-22); row class assignments in section 11 still for founder, accountant and compliance review
Owner: eldon
Approved by: pending (partner review with a different model; accountant and compliance review of the finance rows before Phase 2)

Plan ID: SEC-019. Specifies the one authoritative action-policy table that [ADR-0027](../decisions/ADR-0027-human-floor-action-policy-and-agent-authority.md) calls for. ADR-0027 is Accepted; this spec follows its wording and changes nothing in it. Enforcement is built in ERP-023 (engine side) and OPR-004, OPR-007 (Tool API and approval inbox); agent roles are specified in SEC-020; scoped-chat leak tests are QA-019. Threats addressed: T2, T13, T42, T43, T44, T47, T52, T55, T56 in [threat-model.md](threat-model.md).

Nothing here is built. Every behaviour below is a design requirement, not a description of running code.

## 1. What the table is and is not
- **Is:** the single source of truth for which actor may initiate, approve and execute each action that changes data, sends something outside the tenant, or changes who may do what. Deterministic code reads it; nothing else decides.
- **Is not:** a user-facing risk slider. A simpler scale (for example "low, medium, high") may present the table to owners, but it is derived from the table and never overrides a mandatory control (ADR-0027).
- **Platform rows vs tenant settings.** The platform ships the table with mandatory controls (the floor). A tenant may tighten a row (add an approver, lower a limit, shorten an expiry). A tenant may never loosen a mandatory control or set a limit above the platform cap. Setting or changing a tenant limit is itself a floor action (row AP-PERM-01 class).
- **Versioned.** The table has a version. Every request, approval and execution records the table version it was evaluated under. A table change is a Blueprint change for tenant settings and a reviewed pull request plus ADR for platform rows.

## 2. Principles
1. **Deterministic code decides, never the model.** The policy evaluator is plain code with the table as data. Model output is only ever a proposed payload (a draft). It is never an input to "may this happen".
2. **Fail closed.** If the evaluator cannot load the table, resolve the caller's roles, compute the payload hash, verify the approval or write the audit record, the action is refused.
3. **Identity from the session only.** Actor, roles, tenant and scope come from the authenticated session at the gateway, never from a request body or a model (T41, RULES 41).
4. **Approval is bound.** An approval covers one exact payload, identified by its hash, and nothing else (section 5).
5. **Approval is out of band.** An approval is a human gesture in the UI or a signed confirmation, never a tool the model can call (T42).
6. **Everything is an event.** Request, approval, rejection, expiry, voiding, execution, failure and break-glass are recorded events in the audit log (section 10).
7. **Agents draft, humans approve.** Every row's agent column is draft-only (section 9).

## 3. Table schema
Each row of the table has these fields. Field names are illustrative; the contract change that carries them needs an ADR (threat model section 8, Tool API row).

| Field | Meaning |
|---|---|
| Action id | Stable id, for example AP-SALES-01. Never reused for a different meaning |
| Action version | Increments when the action's payload shape or effect changes; an approval for one version never executes another |
| Description | What the action does, in plain words (i18n key for user-facing text) |
| Effect | Which of: ledger posting, stock movement, external send, permission or role change, configuration change, money movement, record change only |
| Risk class | R0 to R4 (section 4) |
| Reversibility | Reversible by a counter-action (named action id), reversible only by correcting entries, or irreversible |
| Floor action | Yes or no. Yes means a human must execute or approve; no tenant setting removes it (ADR-0027) |
| May initiate | Roles (and scope) allowed to create the request or submit the draft |
| May approve | Roles allowed to approve, or "none" when the initiator's own submission is the human act |
| Approvals required | Number of distinct approvers (0, 1 or 2) |
| Separation of duties | Rule that the approver must satisfy relative to the initiator and others (section 6) |
| Agent | Always "draft only" (section 9) |
| Binding fields | Which payload fields enter the hash in addition to the fixed ones (section 5) |
| Material fields | Fields whose change voids an approval; by default all binding fields |
| Approval expiry | How long an approval stays valid before execution (section 7) |
| Request expiry | How long an unapproved request stays open |
| Limit | Optional amount limit under the platform cap; above it, extra approval applies |
| Break-glass | Allowed or not, and which break-glass path (section 8) |
| Step-up | Whether the approver must re-authenticate with a second factor at the moment of approval |
| Notifications | Who is told on request, approval, execution and failure |

## 4. Risk classes
| Class | Meaning | Default control |
|---|---|---|
| R0 | Read or draft only, no change to shared records | Role and scope check only. Never needs approval |
| R1 | Record change with no ledger, stock, money or external effect | Initiator's own submission; logged |
| R2 | Stock movement or ledger posting arising from an operational document | Human submits (floor); approval above a tenant limit |
| R3 | Direct ledger posting, external send of a financial document, money movement | Human submits; second approver above a limit or by tenant setting; step-up |
| R4 | Reversal of posted history, permission or role change, bank-detail change, contact-detail change (email, phone, notify-to, webhook; its own tool, never agent-creatable, Q-139), agent limit or autonomy change, Blueprint publish | Always a second, different, eligible human approver (section 6); with none available the action is refused, never self-approved (Q-41: R4 has no self-approval); step-up; short expiry; break-glass only through section 8 |

The class sets the minimum. A row may be stricter, never looser. The class assignments in section 11 are still for founder, accountant and compliance review.

## 5. Approval binding
An approval is valid only for the exact payload it was granted for. The evaluator computes a payload hash at request time, shows the approver a rendering produced from the same canonical payload, records the hash with the approval, and recomputes it at execution. Any mismatch voids the approval (T43).

**Always in the hash:** tenant id, action id, action version, table version, target record ids, the data revision of each target record (the revision the approver saw), amount and currency where the action has one, the initiator's user id, and the idempotency key.

**Recorded beside the hash, not in it:** approver user id, approval time, expiry, step-up result. These are part of the approval event, which is itself hash-chained (SEC-008).

**Canonical form.** The hash is taken over one canonical serialisation of the payload, so the same payload always gives the same hash in every service. Proposal: JSON canonicalisation per RFC 8785 with a SHA-256 digest; amounts as decimal strings at the currency's precision, never floating point (UNVERIFIED: the RFC and its fit for decimal strings were not checked this session; confirm in ERP-023).

**Voided automatically when:**
- any material field changes, including a line, a quantity, a price, a discount, the customer, a target record's revision, or the currency;
- the action version or the table version used at request time is no longer current, unless the new table version marks the row unchanged;
- the initiator or approver loses the role that allowed them to act, or their membership is suspended;
- the approval expires;
- the request is cancelled.

A voided approval is never revived. A new request with a new hash starts again.

**The approver sees what executes.** The approval screen renders from the canonical payload, not from model text. A model summary may appear next to it, labelled as a summary, and is not what the approver approves (T32 pattern).

## 6. Separation of duties
Rules a row can name, evaluated by the policy code against session identities:

| Rule | Meaning |
|---|---|
| SOD-NONE | No separation; the initiator's own submission is the human act |
| SOD-DIFF | Approver is a different human from the initiator |
| SOD-DIFF-AUTHOR | Approver is different from the initiator and from every human who edited the payload since the draft was created |
| SOD-NOT-SELF | The action may not target the actor themselves (no granting yourself a role, no approving a change to your own limits) |
| SOD-NOT-AGENT-OWNER | When the draft came from an agent, the approver is not the human who owns or configured that agent (accepted, Q-42: approving a draft from an agent you own or set up is not a second person) |

**Small tenants (Q-41, resolved 2026-11-22).** An eligible approver is a human who holds the row's approving role, is not the initiator, and is not an agent (and, for agent drafts, is not the agent's owner, SOD-NOT-AGENT-OWNER, Q-42). Fallback: when the initiator is the tenant owner and no other human in the tenant holds the row's approving role (role holding, not availability), the owner may self-approve R1 to R3 rows that need a different approver (SOD-DIFF or SOD-DIFF-AUTHOR); the approval is flagged "self-approved", step-up is required, and the event is listed in a periodic review report. If another human holds the role but is away or unavailable, the request waits or goes through section 8; it is never self-approved. R4 rows (permission or role changes, bank-detail changes, agent limits or autonomy, reversals of posted history, Blueprint publish) never have this fallback: they wait for a second eligible human or, where allowed, go through section 8. Consequence for onboarding: a tenant needs a second eligible person to cancel posted invoices (AP-FIN-02) or change roles (AP-PERM-01). When the sole owner approves a draft from their own agent, the same fallback applies (flagged self-approved, step-up, periodic review report), for R1-R3 rows only and never R4 (Q-563, Eldon's answer 2026-11-22).

**Platform staff.** Our own staff never approve a tenant's business action. Support access follows [access-policy.md](access-policy.md) and PLT-019 and is read-only by default. While only two founders exist, separation of duties for support grants is weak (T52); this table does not fix that.

## 7. Lifecycle, cancellation, failure and timeout
States of one request: drafted, pending approval, approved, executing, executed, rejected, cancelled, expired, voided, failed, outcome unknown.

| From | Event | To | Rule |
|---|---|---|---|
| drafted | initiator submits | pending approval, or executing when approvals required is 0 | Policy evaluated at submit; refusal leaves it drafted |
| pending approval | approver approves | approved | Out-of-band gesture, SoD and step-up checked, hash recorded |
| pending approval | approver rejects | rejected | Reason required; terminal |
| pending approval | request expiry passes | expired | Terminal; no approval can be added afterwards |
| pending or approved | initiator or tenant admin cancels | cancelled | Allowed until execution starts; terminal |
| pending or approved | material change, role loss, table change | voided | Terminal; a new request is needed |
| approved | execution starts | executing | Hash recomputed and compared first; mismatch goes to voided |
| approved | approval expiry passes | expired | Terminal |
| executing | engine confirms effect | executed | Terminal; the approval is consumed and cannot run twice |
| executing | engine refuses with no effect | failed | See failure rules |
| executing | no confirmation (timeout, crash) | outcome unknown | See failure rules |

**Cancellation.**
- Before execution, cancelling withdraws the request and any approval. It is an event, not a deletion.
- After execution there is no "cancel". Undoing an executed action is a separate action with its own row and policy (for example AP-FIN-02, cancel a posted invoice, which writes correcting entries and never edits history). Its reversibility field names the counter-action.

**Failure.**
- An approval is single-use and bound to the idempotency key. Execution goes through the engine adapter with that key, so a retry with the same key cannot apply twice (golden path section 7 case 1; T44: the key store includes the user).
- **Failed with no effect** (validation error, stock shortage, closed period): the request moves to failed. A retry is allowed only with the same hash and key and within the approval expiry; anything else needs a new request.
- **Outcome unknown:** never retried automatically with a new key. Deterministic reconciliation reads the engine by idempotency key and target revision and moves the request to executed or failed. Until then it is visible to the initiator and approver as "outcome unknown". Golden path section 7 case 2 is the test.
- A partial effect is a defect, not a state: engine operations for one action must be atomic. If one is ever observed, it is an incident ([incident-response.md](incident-response.md)).

**Timeout and expiry.** Defaults accepted in Q-43: request expiry, R1 to R2 several days, R3 to R4 one working day; approval expiry, R2 to R3 a few hours, R4 one hour. Tenants may shorten these defaults, never lengthen them (Q-43). Expiry is checked by the evaluator at execution from a trusted clock, never from the client. Expired items are not executed late.

## 8. Emergency access (break-glass)
Two different things share the name; neither lets an agent act.

**Tenant break-glass** (the approver is unavailable and something must happen, for example a delivery is stuck behind an absent approver):
- Only rows marked break-glass allowed. Proposed: never for permission changes, bank-detail changes, agent limits or Blueprint publish.
- Only a tenant owner, with step-up, a typed reason and a time box.
- Executes as the owner under a break-glass flag; the event says so.
- Notifies every other approver for that row at once.
- Opens an after-the-fact review item that a different human must close (approve or dispute). An undisputed review that runs past its window escalates to the owner's review report; it is never auto-closed.
- Counted and shown in the periodic review report; repeated use is a signal that the row or staffing is wrong.

**Platform break-glass** (our staff, for an incident affecting a tenant): governed by [access-policy.md](access-policy.md) (sealed account, alerts on use) and PLT-019 (just-in-time, ticket-linked, second-person approval, tenant notified, auto-expiring). It never posts, sends or changes permissions inside a tenant's books on the tenant's behalf. If it ever has to change tenant data to stop harm, that is a recorded incident action with tenant notification and founder review afterwards.

Neither path can change the action-policy table, raise a platform cap, or disable audit.

## 9. Agent actors and the human floor
- **Agents are their own actors** with their own least-privilege role (SEC-020), never their owner's permissions (ADR-0027). Every agent event carries the agent's id and the owning human's id.
- **Draft-only, everywhere.** In every row, the agent column is "draft only": an agent may prepare a payload and place it in the initiator's or approver's queue. It may not submit, approve, reject, post, send, change permissions or change an approval rule. The policy evaluator refuses any submit or approve whose actor is an agent, whatever the agent's role says. This is a hard check in code, not a table value a tenant can change.
- **Adopting a draft.** When a human submits an agent's draft, that human becomes the initiator and is accountable. The draft's origin (agent id, model call ids) stays on the request for audit.
- **The approval gesture is not reachable from a model.** The approve action is not exposed as a tool, and the approval screen refuses to approve while the session has untrusted (tainted) content in the same turn (T42).
- **Floor actions** in ADR-0027 (ledger posting, periodic tax returns, payments, permission or role changes, sensitive external sends, bank-detail changes, agent limits and autonomy) are marked floor = yes and can never be set to approvals required 0 with an agent initiator.
- **Authority invoice clearance** is deterministic code outside the floor (ADR-0027). It is not in the starter table because the golden path has no tax. Its rows wait for the accountant and compliance review per country.

## 10. Enforcement when the model or gateway fails
| Failure | Behaviour |
|---|---|
| Model gateway down or model returns nonsense | No drafts from the chat. Humans can still create, submit and approve through role views; policy is unaffected because the model never decided it |
| Model output tries to set actor, role, approver, hash or table version | Ignored; these come from the session and the evaluator only |
| Policy table cannot be loaded or fails validation | All non-R0 actions refused |
| Role or scope cannot be resolved | Refused (RULES 41, golden path section 6) |
| Hash cannot be computed or does not match | Refused; approval voided |
| Audit write fails | Refused. The request, approval and execution events are written before the effect (write-ahead); no effect without a durable record |
| API gateway down | Nothing executes. There is no direct path to the engine that skips the gateway (ADR-0016, threat model assumption 3) |
| Clock untrusted or skewed beyond tolerance | Expiry cannot be checked; R2 to R4 refused |

**Two enforcement points.** The Tool API gateway evaluates the policy (OPR-004). The engine adapter re-checks the approval binding before applying the effect (ERP-023), so a defect in one point is caught by the other. Both read the same table version.

## 11. Approval as a recorded event
Every step is an event in the event stream contract and the audit log, append-only and hash-chained (SEC-008). Proposed event types: action.requested, action.cancelled, approval.granted, approval.rejected, approval.voided, approval.expired, action.executed, action.failed, action.outcome_unknown, action.reconciled, breakglass.used, breakglass.reviewed.

Each event carries: tenant id, event id, sequence, action id and version, table version, request id, payload hash, actor kind (human, agent, platform, support) and actor id stamped by the platform, never by the producer (T55), the owning human for agent actors, the session or device reference, step-up result where relevant, reason text where required, and the previous state.

From any posted document, the audit trail can answer: who drafted it (human or agent), who submitted it, who approved it, which exact payload hash they approved, under which table version, when it executed, and whether break-glass was involved. QA-019 and the ERP-023 tests check this trail.

## 12. Starter table: golden-path actions
Roles from [../specs/golden-path-trading-sale.md](../specs/golden-path-trading-sale.md) section 3: Owner, Sales, Warehouse, Finance. The class assignments and rows are proposals for founder, accountant and compliance review; only Q-41, Q-42 and Q-43 are settled. "Owner" also covers a tenant admin role if one exists (ADR-0007, Proposed).

| Action id | Action | Effect | Risk | Floor | May initiate | May approve | Approvals | Separation | Agent | Extra binding fields | Approval expiry | Break-glass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AP-SALES-01 | Create and submit a sales order | Record change | R1 | No | Sales, Owner | None | 0 | SOD-NONE | Draft only | Customer, lines (item, quantity, price, discount), total | Not applicable | Not needed |
| AP-STOCK-01 | Create and submit a delivery against an order | Stock movement and its ledger posting (perpetual inventory) | R2 | Yes (human submits) | Warehouse, Owner | None up to tenant limit; Owner above it | 0, or 1 above limit | SOD-NONE; SOD-DIFF above limit | Draft only | Order id and revision, warehouse, lines (item, quantity) | Few hours | Allowed (tenant) |
| AP-FIN-01 | Review and post a sales invoice to the ledger | Ledger posting | R3 | Yes | Finance | Finance poster by default; Owner above tenant limit | 0, or 1 above limit | SOD-DIFF-AUTHOR above limit; single-approver fallback allowed | Draft only | Source delivery ids and revisions, customer, lines, discount, total, currency | Few hours | Allowed (tenant) |
| AP-FIN-02 | Cancel a posted invoice (correcting entries, never edited history) | Reversal of posted history | R4 | Yes | Finance | Owner | 1 | SOD-DIFF; no self-approval fallback (R4, Q-41) | Draft only | Invoice id and revision, reason, the correcting entries preview total | One hour | Not allowed |
| AP-PERM-01 | Change a user's roles or permissions, or a tenant limit | Permission change | R4 | Yes | Owner | A second Owner or admin | 1 | SOD-DIFF, SOD-NOT-SELF; no fallback | Draft only (never even for its own role) | Target user, roles before and after, scopes, limits before and after | One hour | Not allowed |
| AP-BPL-01 | Publish a Blueprint change to the live tenant | Configuration change | R4 | Yes | Owner | Owner (confirming the deterministic diff) and our review gate for first clients | 1 owner, plus platform review | SOD-NOT-AGENT-OWNER when agent-drafted; reviewer is not the author | Draft only | Blueprint id, from and to revision, diff hash | One hour | Not allowed |
| AP-PAY-01 (proposed) | Create a hosted checkout for an invoice or order (`payment.create_checkout`) | Money movement | R3 | Yes (human submits) | Finance, Sales, Owner | None up to tenant limit; Finance or Owner above it, with step-up | 0, or 1 above limit | SOD-NONE; SOD-DIFF and SOD-NOT-AGENT-OWNER above limit | Draft only (a human reviews and submits) | Connection id, link ids and revisions, amount and currency (decimal string), expiry | Few hours | Not allowed |
| AP-PAY-02 (proposed) | Refund a payment (`payment.refund`), basis credit note or unallocated funds | Money movement | R4 | Yes | Finance | Owner, or a second Finance holder, with step-up | 1 | SOD-DIFF, SOD-NOT-AGENT-OWNER; no fallback | Not allowed, not even a draft | Payment id and revision, basis, amount and currency (decimal string), credit note ids and revisions (credit note basis), reason code | One hour | Not allowed |
| AP-PAY-03 (proposed) | Void an authorised payment (`payment.void`) | Money movement | R4 | Yes | Finance | Owner, or a second Finance holder, with step-up | 1 | SOD-DIFF, SOD-NOT-AGENT-OWNER; no fallback | Not allowed, not even a draft | Payment id and revision, authorised amount and currency (decimal string), reason code | One hour | Not allowed |
| AP-PAY-04 (proposed) | Connect a gateway account or rotate its keys (`payment.connect_gateway`); the environment is fixed, a new environment is a new connection | Configuration change (bank-detail class) | R4 | Yes | Owner | A second Owner or admin, with step-up | 1 | SOD-DIFF, SOD-NOT-AGENT-OWNER; no fallback | Not allowed, not even a draft | Connection id and revision, provider, environment, merchant account ref from the probe, probe id, each staged secret's slot, id and fingerprint (never the secret) | One hour | Not allowed |
| AP-PAY-05 (proposed) | Post a captured or unallocated payment to the ledger as a receipt allocated to open invoices or orders (rigid-zone code drafts it; never posted by a webhook) | Ledger posting | R3 exact match (one open sales invoice, same tenant and currency, allocated in full, equal to the net captured amount); R4 otherwise (Q-723, Eldon 2026-11-27) | Yes (human submits; never posted by a capture) | Finance | R3: none, as AP-FIN-01 (Owner above tenant limit). R4: Owner, or a second Finance holder, with step-up | R3: 0, or 1 above limit. R4: 1 | R3: as AP-FIN-01. R4: SOD-DIFF, SOD-NOT-AGENT-OWNER; no fallback | Not allowed, not even a draft | Payment id and revision, each link with revision and allocated amount (decimal string), currency, receipt account | One hour | Not allowed |

Notes on the rows:
- **AP-SALES-01** has no ledger effect on this path, so no approval. A tenant may add a credit-limit approval later; that is a tenant tightening, not a new mandatory control.
- **AP-STOCK-01** moves stock and posts cost of goods sold (golden path section 5). Posting to the ledger is a floor action, so a human must submit; the Warehouse user's own submission is that human act. Whether an operational posting like this counts as "posting to the ledger" in the ADR-0027 sense is open question Q-44.
- **AP-FIN-01** follows the golden path: Finance reviews and posts. ADR-0027 says posting is always a human; it does not require a second human for every invoice. The tenant limit above which the Owner must also approve is a tenant setting under a platform cap.
- **AP-FIN-02** is a counter-action, not a cancellation of a request (section 7). It needs the Owner even when Finance initiates.
- **AP-PERM-01** also covers changing an agent's limits or autonomy (ADR-0027); SEC-020 may split that into its own row.
- **AP-BPL-01** keeps the human review gate for first clients (ADR-0005, RULES 23). The owner approves the deterministic diff, not a model summary (BPL-006).
- **AP-PAY-01 to AP-PAY-05** are proposed by DSC-021 (2026-11-27, [connector-payments.md](../../contracts/connector-payments.md) sections 4 and 11, [ADR-0077](../decisions/ADR-0077-payments-connector-bring-your-own-gateway.md)) for partner review on its PR. Every row binds the full section 5 fixed set (table version and initiator id included), and amounts enter the hash as decimal strings at the currency's ISO 4217 exponent (contract 1.3). AP-PAY-02 to AP-PAY-05 are stricter than section 9: an agent may not even draft them. Execution re-checks SoD, the approver's role and the step-up result.
- The golden path roles table says Finance may not change permissions and Sales and Warehouse may not see cost or ledger; section 6 of that spec is checked by role views and QA-019, not by this table, which governs actions.

## 13. Open questions for the founders
Added to [../open-questions.md](../open-questions.md) as Q-41 to Q-44 (numbers chosen after the highest number used on any open branch).
1. **Q-41** (resolved 2026-11-22) Single-approver fallback for small tenants: may a sole owner self-approve SOD-DIFF rows with a flag and step-up, and which rows have no fallback?
2. **Q-42** (resolved 2026-11-22) When a human approves a draft made by their own agent, does that count as separation of duties (SOD-NOT-AGENT-OWNER)?
3. **Q-43** (resolved 2026-11-22) Default request and approval expiry per risk class, and whether tenants may lengthen them up to a platform cap.
4. **Q-44** Does an operational posting (delivery posting cost of goods sold under perpetual inventory) count as "posting to the ledger" under ADR-0027, and therefore need floor treatment? Accountant input needed.

Also for review, not separate questions: the risk class of each starter row; the canonical-form and hash proposal (UNVERIFIED); whether break-glass for AP-STOCK-01 and AP-FIN-01 is acceptable.

## 14. What this spec does not cover
Payments other than the proposed AP-PAY rows, tax returns, e-invoice clearance and submission, bank-detail changes and external sends get rows when their paths are specified. Agent role grants, cost caps and kill switch are SEC-020. The approval inbox screen is WEB-005. Retention of approval records follows OPR-012 and [data-classification.md](data-classification.md).
