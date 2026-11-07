# Threat model: contracts

Status: draft
Owner: eldon

Plan ID: SEC-001. Companion to [threat-model.md](threat-model.md) (threat ids T1 to T60 are defined there). This file says, per contract, what each consumer may trust, what it must not trust, and who validates what. It also lists contract changes we propose. Nothing here changes a contract: each change needs an ADR ([../../contracts/README.md](../../contracts/README.md), rule 2).

## Rules that apply to every contract
1. **Nothing in a payload sets identity.** Tenant id, user id, roles, actor kind and reviewer id come from the authenticated session or the platform, never from a body, a Blueprint, an event payload or model output.
2. **Validate at every boundary, again.** A check done upstream is a convenience. The consumer that acts (writes to the engine, executes a tool, stores an event) runs its own check.
3. **Fail closed.** A lookup error, unknown field, unknown version or schema failure is a deny, logged with an audit id.
4. **Model output is untrusted input.** Anything a model wrote (a draft Blueprint, tool arguments, a mapping) is treated like a request from an anonymous user until the validator and the permission check pass.
5. **Pin versions.** Consumers declare the contract versions they accept and refuse others (README rule 7).

## 1. Blueprint schema ([blueprint.schema.json](../../contracts/blueprint.schema.json))

Producers: Discovery (AI drafts, templates, imports), Operate (`blueprint.propose_change`), owner and admin edits (settings screens), the factory (indirectly, via components). Consumers: validator, compiler, change engine, Tool API generator, theming, visual viewer, simulator.

| Consumers may trust | Consumers must not trust |
|---|---|
| A revision that the validator passed **and** that is stored with that pass recorded, in the state the control plane reports | Any Blueprint not checked by the validator in this exact revision, including drafts shown to the owner |
| That `meta.buildState` mirrors the control plane, only when read from the control plane | `meta.buildState`, `provenance` or `humanEdited` read from the file itself (producer-written, can be forged) |
| Ids are unique and references resolve (x-validator-rules) | That an id is safe as an engine object name (T24), or that a guard `value` matches its field type (T26) |
| `computed.function` names a function from a bound component | That the name maps to safe code unless resolution uses a static registry from certified manifests (T25) |
| `assetRef.sanitised = true` was set by the pipeline, once checked against the asset record | That the asset belongs to this tenant unless the lookup is tenant-scoped (T28) |
| Labels and display names are strings of bounded length | That labels are safe in templates, HTML, CSV or PDFs (T27): always escape on output |
| Branding colours match `hexColour` | That contrast passes; the validator computes it (designed) |

Validation responsibilities:
- **Validator (Part 2, BPL-003)**: JSON Schema plus every x-validator-rule. Owns the proposed new rules below.
- **Compiler (BPL-004)**: refuses any revision without a validator pass recorded for its hash; namespaces generated engine objects; passes values as parameters.
- **Change engine**: the plan gate flags destructive operations and any change to core engine objects; applies only change sets from the compiler, never ad hoc input.
- **Tool API generator (OPR-003)**: derives permissions only from the stored revision; `approval.required` from rules plus platform policy.
- **Owner and team reviewer**: see a deterministic permission diff (T32), not only the model's summary.

## 2. Component manifest ([component.manifest.schema.json](../../contracts/component.manifest.schema.json))

Producers: our engineers, the component factory (AI-drafted, `origin.source = component_factory`), upstream open source. Consumers: registry, compiler, Tool API generator (components may contribute tools), validator (function and parameter resolution), entitlements and rollout.

| Consumers may trust | Consumers must not trust |
|---|---|
| `certification.level` and evidence, when read from the registry (which refuses invalid manifests) | A manifest read from a package that the registry did not hash-pin |
| `licence` was recorded and dated | That `dataHandling` flags are true: they are self-declared |
| `parameters` types and bounds | That a parameter default contains no tenant data (T28) |
| Declared `provides` artifacts exist in the package | That contributed tools declare their `effects` honestly (T33); effects must be confirmed in review |

Validation responsibilities: registry (BPL-010) refuses invalid or unpinned packages; certification (BPL-014) includes a security review for any component with `function`, `tool` or `scheduled_job` artifacts; factory sandbox and static analysis (SEC-010).

## 3. Tool API ([tool-api.md](../../contracts/tool-api.md))

Producers of calls: the chat runtime (model chooses tool and arguments), scheduled agents, UI actions that reuse tools. Consumer: the Tool API gateway in Part 4, then the engine adapter.

| The gateway may trust | The gateway must not trust |
|---|---|
| Tenant and user from the verified session token, checked against the routed tenant (T50) | Anything in the request `caller` object: `role_ids`, `tenant_id`, `user_id` (T41) |
| Roles loaded from identity for this tenant at call time | Role names, SQL, code, formulas, URLs or keys in arguments (section 10 already forbids them) |
| The tool set stored with the current revision | That a tool the model names exists for this caller: check `unknown_tool` then permission |
| An approval record whose hash matches the call (once the change below lands) | An approval decided in the same model turn, or by the requester, or with tainted context (T42, T43) |
| A stored idempotency result for the same user, tool and key | A stored result for the same key from another user (T44) |
| The `tainted` flag set by the runtime when untrusted content is in context | The model's claim that content was trusted |

Validation responsibilities: schema check of arguments, then role, scope, field and approval checks in the gateway (OPR-004); re-validation in the adapter; the engine evaluates permissions as the real user, not as the service identity (T36, gap). Audit record on every call, success or failure.

## 4. Event stream ([events.md](../../contracts/events.md))

Producers: engine adapter (record events), our services (audit, agent, metering), identity, control plane. Consumers: audit store, agents (triggers), metering and billing, reuse metrics, observability, support console.

| Consumers may trust | Consumers must not trust |
|---|---|
| `tenant_id`, `sequence` and `recorded_at` when stamped by the platform at ingestion | `tenant_id`, `actor` or `actor.kind` set by a producer (T55) |
| `event_id` uniqueness for de-duplication | That a new `event_id` means a new fact: replays with fresh ids are possible until producers are authenticated |
| `data_class` as a minimum handling level | That `data` contains no personal data: redact again before any model sees it |
| Event schemas by `type` and `schema_version` | Free text in `data` (names, comments): it is untrusted content for agents (T47) |

Validation responsibilities: ingestion authenticates each producer and restricts the types it may emit; the platform stamps tenant, sequence and actor; the audit store is append-only and hash-chained (SEC-008); agent triggers check freshness and treat payload text as untrusted.

## 5. Connector interface ([connector-interface.md](../../contracts/connector-interface.md))

Producers: connectors (our code) reading customer tools, files, inboxes. Consumers: Discovery mapping, the model (via quoted data), staging, importers (ERP-013).

| Consumers may trust | Consumers must not trust |
|---|---|
| `source.trust = "untrusted"` labelling and source ids | Any string inside `extract` or `normalise` output, including headers, file names and OCR text (T1) |
| `describe()` from the registry, after security review | A base URL, redirect or link supplied by the owner or found in data (T18) |
| Content hashes for de-duplication | OCR values above a confidence threshold without human confirmation |
| That tokens are in the vault | That a token's scope is read-only unless checked at `authorize` time |

Validation responsibilities: connector framework (DSC-010) enforces tenant context, staging-first, file safety, scope checks and egress controls; mapping approval by the owner or team before any import; importer re-validates against the Blueprint.

## 6. Build states ([build-states.md](../../contracts/build-states.md))

Consumers may trust a state only as reported by the control plane. They must not trust a state or reviewer id carried in a Blueprint, event payload or agent request (T31). The control plane validates: actor identity from the session, actor type allowed for the transition (AI never approves), preconditions recorded, MFA for the human gate.

## 7. Proposed contract changes (for an ADR; not made here)

| Contract | Change | Threats |
|---|---|---|
| Tool API | Mark the `caller` object in the sample request as "set by the gateway; any client value is discarded", or remove it from the request example | T41 |
| Tool API | Idempotency store keyed `(tenant, user, tool, key)`; replay returned only to the same user; state the retention as at least the longest client retry window | T44 |
| Tool API | Approval binds to `arguments_hash`, `tool_version`, `blueprint_revision`; any mismatch voids it | T43 |
| Tool API | `approval.decide` requires a user gesture outside the model (UI action or signed confirmation), is never in an agent's allow-list, and is refused while the turn is tainted | T42 |
| Tool API | Add `tainted` and `on_behalf_of` to the audit fields (section 8) | T1, T47 |
| Tool API | Section 4 step 8: state how "user's own permissions" is achieved in the engine (no admin service account) | T36 |
| Events | Producers authenticate; each producer has an allow-list of types; `tenant_id`, `sequence`, `actor` stamped at ingestion; `support` actor must carry a grant id | T55, T52 |
| Events | Agent triggers ignore events older than a set window and dedupe on subject plus causation, not only `event_id` | T55, T47 |
| Blueprint | New x-validator-rules: reserved-name deny-list for ids; guard `value` typed by field and `op`; `maxItems` and size caps; `assetRef` must belong to the same tenant; least-privilege lint (flag new `isAdmin`, `company` scope, removed approval rules) | T21, T24, T26, T28, T35 |
| Blueprint | State that labels and display names are data and must be escaped by every renderer, never placed in template source | T27 |
| Manifest | Require a package hash; declare outbound network use; security review evidence required for `function`, `tool` and `scheduled_job` artifacts; parameter defaults may not hold tenant data | T33, T39, T28 |
| Connector | Owner-supplied URLs: HTTPS only, DNS resolved and checked against private ranges, redirects re-checked, egress via proxy; OAuth with state and PKCE where supported | T18, T4 |
| Connector | Tier 4: per-tenant unguessable inbox addresses and an owner-set sender allow-list | T19 |
| Build states | Approving transitions need a staff session with MFA; AI service identities are refused by the control plane | T31 |

## 8. Not verified
- Engine behaviour assumed above (how impersonation, whitelisted methods and site context work) is UNVERIFIED until ERP-001 and CE-SEC-005.
- Whether OAuth with PKCE is offered by target source systems (Odoo and others) is UNVERIFIED.
