# ADR-0069: Gateway live binding: durable audit spool, identity-bound audit records, size caps

Status: Proposed
Owner: partner
Approved by: pending (security review by a different model, then both founders; Tier 3 under ADR-0035 because it touches auth, tenancy and audit, RULES 42)

Plan ID: PLT-027 (G2). Design only. **No live binding, server, route or store is delivered by this ADR**; the code is in the follow-up rows at the end. Builds on [ADR-0016](ADR-0016-engine-invisibility.md) (engine invisibility), [ADR-0007](ADR-0007-identity.md) (identity, tokens, shadow users), [ADR-0060](ADR-0060-role-assignments-in-regional-store.md) (regional role store and its security conditions), [ADR-0040](ADR-0040-tenant-provisioning-service.md) (control-plane regional database, route registration gate) and [ADR-0041](ADR-0041-durable-adapter-state-on-tenant-database.md) (adapter state, idempotency and audit in the tenant database). Contradicts none of them; where a point needs another lane's change it is listed as a question, not decided.

**How to read this ADR.** Items marked **(Inherited)** restate an existing Accepted or Proposed decision and add nothing. Items marked **(P)** are new proposed choices of this ADR, including every number; a reviewer may change any (P) value without changing the structure. UNVERIFIED marks claims not tested on real infrastructure.

Revisions 1 and 2 answer two security reviews (GPT-6.2 Sol, both "changes required"); each finding was checked against the code and contracts cited inline. Protocol details left to an implementation row are named as "PLT-0xx must specify X before code".

## Context
- PLT-024 built the customer-facing API edge core in `services/gateway/edge/` (`gateway.py`, `paths.py`, `projection.py`, `headers.py`, `errors.py`, `markers.py`; summary in [services/gateway/README.md](../../services/gateway/README.md)). It is pure in-process logic tested with fake upstreams: deny-by-default `/v1/` routes, allow-list projection of engine JSON, header and cookie filtering, engine-error mapping, and an audit sink that is required.
- Its audit is process memory: an `intent` record before a mutating handler, an `outcome` after every request, a 1000-record deque for outcome records that failed after a possible effect, reservation at 900 to return `503 audit_unavailable`, and `audit_drop_count`. Process memory is not crash durable.
- Facts in today's core that this design changes: a route is matched by path for any allowed method (`gateway.py:167`), and "mutating" is decided by the HTTP verb alone (`gateway.py:29`, `gateway.py:175`); a handler returns a complete body in `UpstreamResponse` (`gateway.py:60`) that `projection.py:119` parses whole; an expired engine `sid` makes the gateway clear the platform cookie (`gateway.py:237`, `headers.py:70`, cookie `SameSite=Lax` at `headers.py:27`); the raw path is recorded up to 256 characters (`gateway.py:269`).
- The README and the PLT-024 logs (2026-11-18 and 2026-11-20) set three hard preconditions before any HTTP binding or live route: (1) a durable spool with recovery, retry and observable drop and backlog health; (2) tenant, user and session from verified identity bound to every audit record (Tool API section 8); (3) request-body, Idempotency-Key and upstream-body caps with regression tests (PR #123 review item 5). Q-302 asks Eldon to add `unauthenticated` and to ratify `audit_unavailable`.
- Identity exists as a core (PLT-005, Eldon's lane): `verify_customer_token(token, tenant_id)` returns `AccessClaims` (issuer, audience, subject, tenant, realm, session_version, mfa_satisfied, auth_time, token_id, times; no roles) after checking the membership and its session version. Roles come from a `RoleResolver` port; ADR-0060 item 15 forbids reading real roles from the regional store before SEC-024 (store design ADR with its own security review) and GOV-065 (Tool API wording) are accepted.
- The engine adapter contract covers the configuration path only (`capabilities`, `provision_site`, `plan`, `apply`, `rollback`, `sync_members`...); `execute` and `query` (Tool API runtime) are out of scope ([contracts/engine-adapter.md](../../contracts/engine-adapter.md) section 1, line 11). So ADR-0041's 30-day idempotency covers configuration operations, not business writes. The adapter context already requires a `correlationId` (engine-adapter.md line 38; `contracts_support.py:180`) and writes it to `adapter_audit_log` (engine-adapter.md line 200; `storage.py:232`, `mariadb_store.py:43`), with no index on it.
- The store of record for audit is SEC-008 (append-only, hash-chained, exported off-box; Eldon's lane, G2, todo; threat T56). Its location is not decided, and this ADR does not decide it.

## Decision

### 1. Shape of the binding
1.1 **(P)** The binding is a thin HTTP adapter around `Gateway.handle`: it builds a `GatewayRequest` carrying the verified principal and serialises the `GatewayResponse`. Route policy, audit and caps that need route knowledge stay in the edge core, testable without a socket.
1.2 **(P) Two layers of HTTP control.** WSGI (PEP 3333) runs after the server has parsed the request, so the application cannot see or refuse framing ambiguities, enforce header-read deadlines or replace parser-generated errors. Therefore:
- **At the production listener and at every HTTP hop in front of it** (proxy, if INF-001 chooses one): refuse a request with duplicate or non-numeric `Content-Length`, with both `Content-Length` and `Transfer-Encoding`, with any request `Transfer-Encoding`, with obsolete line folding, with more than one `Host` or a `Host` that disagrees with an absolute-form target (RFC 9112 sections 6.3 and 3.2), and close the connection after any framing error; enforce the header-read and body-read deadlines and header caps of section 4; send no `Server` header and our own error body for every parser-generated refusal. The production listener is a separate choice with a licence record in PLT-029; `wsgiref` and `http.server` are for tests only.
- **In the WSGI application:** repeat every check it can see (defence in depth) and every route-dependent cap. A configuration in which the listener does not provide the first layer is not deployable.
1.3 **(Inherited, ADR-0016)** The engine runs on an internal network; the public listener reaches it only through route handlers over the engine adapter.
1.4 **(P)** Health, readiness and metrics are served on a second listener bound to the internal network only, never on the public listener and never under `/v1/`.
1.5 **(P) Listener events.** Refusals and timeouts that happen at the listener, before WSGI, have no request in the core. The listener passes each one (reason, hop, keyed source digest) through a bounded local channel (10,000 events; aggregated per minute per reason; overflow counted in the next aggregate) into the `preauth` spool (2.1). PLT-029 must specify the channel for the chosen listener before code; a listener that cannot emit these events is not deployable.

### 2. Durable audit spool
2.1 **(P) What it is.** Each gateway instance owns two local, append-only SQLite spools (standard library `sqlite3`, WAL, `synchronous=FULL`), each its own file, WAL, budget, `seq` stream, chain and forwarder stream: `tenant` (verified requests) and `preauth` (no verified identity, a token for another tenant, listener events). They sit on a persistent, encrypted volume in the instance's country and placement (ADR-0006); crash durability on the production volume type is UNVERIFIED until tested. A spool is a **delivery buffer, not a store of record**: only its forwarder and recovery read it, a record stays only until the store of record has committed it, it is never backed up or restored as a source of truth, never shared between instances or over a network file system. It is not a second regional store and touches neither the control-plane regional database (ADR-0040) nor the regional role store (ADR-0060).
2.2 **Why SQLite here does not contradict ADR-0041.** ADR-0041 keeps adapter state out of SQLite because idempotency keys and their effects must restore together with the tenant database. A spool holds no state that must agree with tenant data after a restore.
2.3 **(P) Single writer and record ceiling.** An instance takes an exclusive lock on its spools at start (advisory file lock plus a fencing row); a second process refuses to serve. Every serialised record is at most 4 KiB: each field in 5.1 has a fixed maximum length, and a record that would exceed the ceiling is a write failure (503 `audit_unavailable`), never silently truncated. Every reservation counts this ceiling.
2.4 **(P) Tables of the `tenant` spool.** `records` (the chained log the forwarder delivers and prunes), `open_intents`, `quarantine`, `checkpoint`. An `open_intents` row holds the full serialised intent record, its `seq` and `chain`, the reserved bytes, and `row_mac = HMAC(key, stream || seq || intent_bytes)`. It is inserted in the intent's transaction, deleted in the outcome's transaction, and **never touched by the forwarder**, so recovery can rebuild an identity-bound outcome after the intent itself was pruned.
- Write request: intent and open row commit **before** the handler runs; if the commit fails or admission (2.10) refuses: `503 audit_unavailable`, handler not called.
- Read, denial or validation failure: the outcome commits before the response, else `503 audit_unavailable` (P: today 500 `internal_error`).
- After a possible effect: if the outcome commit fails, the real result is returned (an error would invite a duplicate), the outcome is retried in process, and the open row keeps the reservation; if the process dies first, recovery (2.11) closes it.
2.5 **(P) Chain and keys.** Each record carries `instance_id`, `stream`, monotonic `seq` (the ordering authority; wall time can go backwards), `key_id` and `chain = HMAC(key[key_id], prev_chain || canonical_record)`. Keys are versioned secrets registered under ADR-0038 by PLT-028 (no id allocated here). Rotation writes a `key_rotation` record under the old key naming the new `key_id`; the old verification key stays available until every record under it is committed in the store of record. The tenant-wide chain and off-box export stay SEC-008's (T56).
2.6 **(P) Store-side state (the `AuditStore` port, Q-614).** Per `(instance, stream)` the store keeps a checkpoint `{version, wm_seq, wm_chain, head_seq, head_chain, confirmed_at}` (committed watermark and last reported head), changed only by compare-and-set on `version`, with `wm_seq` and `head_seq` never decreasing, and accepted only from that instance's own credential (ADR-0038, registered by the forwarding row). Per `(instance, stream, seq)` it keeps the original receipt and the record's verbatim bytes (accepted record, or evidence for a rejected or conflicting one), so its own chain check recomputes the HMAC over the original bytes. Ingest is per instance and must not depend on any tenant's state, so a delivery stall is store-wide by construction. The store also lists, per instance, committed intents that have no committed outcome (for 2.11).

2.7 **(P) Checkpoint protocol.**
| Step | Action | Rule |
|---|---|---|
| Report | Forwarder sends `(head_seq, head_chain, expected version)` with every batch and every 5 s, idle or not | Store CAS; same `(seq, chain)` refreshes `confirmed_at` only. A lost reply is retried after re-reading the checkpoint; a stale `version` returns the current checkpoint |
| Snapshot | One store read (all fields at one `version`) plus local reads in one SQLite read transaction | Verification uses only this pair |
| Verify (start, every 5 s, before each batch) | Local `pruned_through` > `wm_seq` | Impossible by the prune rule: fail closed |
| | Local `pruned_through` < `wm_seq` | Rows up to `wm_seq` must exist and chain to `wm_chain` (crash before prune); else rollback or truncation: fail closed |
| | `head_seq` > `wm_seq` | Rows up to `head_seq` must exist with `chain` = `head_chain` at that `seq`; else truncation: fail closed |
| | `head_seq` <= `wm_seq` | Nothing local to check: the store holds those records |
| Prune | Only up to a `wm_seq` taken from a receipt whose `version` >= the snapshot's, in one transaction with the quarantine moves (2.9) and the local checkpoint | Never above the store's watermark; a record in `(wm_seq, head_seq]` is never pruned, so a watermark that moves after the snapshot cannot remove a record a check needs |
| Unconfirmed | No confirmed report for 30 s | The `tenant` stream refuses new writes (503) until a report is confirmed; reads continue to the capacity limit (2.10) |
Fail closed means: stop forwarding, refuse writes, page. Residual: records written after the last confirmed report (at most 30 s of writes, and reads until capacity) can be removed undetected by someone with write access to the volume.

2.8 **(P) Receipt protocol.** Batches (at most 500 records or 1 MiB) are processed in `seq` order; a batch whose first `seq` is not `wm_seq + 1` is refused with the current checkpoint and resent from there.
| Store state at `(instance, stream, seq)` | Incoming | Receipt | Store effect |
|---|---|---|---|
| empty | valid, new `(audit_id, phase)` | `committed` | append; watermark advances |
| empty | `(audit_id, phase)` already committed with other bytes | `conflict` | verbatim bytes kept as evidence beside the first, neither overwritten; watermark advances |
| empty | fails the record schema | `rejected` | verbatim bytes kept as evidence; watermark advances |
| filled | same bytes | the original receipt, unchanged | none (a retry never turns `rejected` into `duplicate`) |
| filled | other bytes | `seq_conflict` | none; forwarder fails closed (local rewrite or bug) |

2.9 **(P) Quarantine protocol.**
| Local state | Event | Next state |
|---|---|---|
| in `records` | `committed` | pruned in the prune transaction |
| in `records` | `rejected` or `conflict` | moved to `quarantine` with `seq`, `chain` and receipt, in the same transaction that prunes and advances the local checkpoint |
| in `records` | crash before that transaction | the retry returns the original receipt; same move |
| in `quarantine` | operator resolves (audited) | a corrected record, if needed, is appended as a new record citing the old `seq`; the quarantine row is deleted only after the store commits it |
| in `quarantine` | tenant deprovisioned | destroyed under the deprovisioning approvals (5.5) |
Quarantined records count against capacity and their tenant's share, never block delivery, and page while any exists.

2.10 **(P) Capacity and admission.** `tenant` spool: 100,000 records or 512 MiB, counting measured database and WAL size plus reservations (open rows times the 4 KiB ceiling times an overhead factor of 2; factor and sizes UNVERIFIED until measured). Admission and the open-row insert run in one `BEGIN IMMEDIATE` transaction, so reservations are atomic across threads and processes and survive restart. Writes are refused at 90%, reads and denials at 100%, and writes also after 30 s without a confirmed checkpoint (2.7). One tenant may hold at most 20% (unforwarded, quarantined and reserved); above that only that tenant's writes are refused. Because ingest does not depend on tenant state (2.6) and quarantine never blocks delivery (2.9), one tenant's records cannot stop another tenant's writes. Late outcomes always fit their reservation; reads after a threshold accumulate only up to capacity, so the spool is bounded by size, not time. `preauth` spool: 10,000 records or 64 MiB in its own file; when full, unverified requests get `429 rate_limited` and are counted in an in-memory aggregate written as one record per minute per reason into a reserved slot; verified traffic never touches it (3.2). `audit_drop_count` must stay zero; any increase pages. `oldest_unforwarded_age_s` alerts at 60 s and pages at 300 s; it is not an admission rule.
2.11 **(P) Restart and recovery.** Not ready until: lock taken; snapshot verified (2.7; with the store unreachable the instance starts without admitting writes until a report is confirmed); every open row with a valid `row_mac` closed by an outcome rebuilt from its own intent bytes (`status: null`, `reason: "unknown_after_restart"`, all identity fields), one transaction per row, so a crash during recovery leaves only unclosed rows and none closes twice; missing-row check: every intent the store lists as open, plus every local unpruned intent without an outcome, must have a valid open row, else writes stay refused and an operator is paged. Then the forwarder starts and the instance reports ready.
2.12 **(P) Reconciliation of unknown outcomes.** The gateway sends its request `audit_id` as `correlationId` on every adapter call (Context); each adapter call keeps its own `requestId` and `auditId`. An unknown outcome is reconciled only against a terminal adapter outcome; an audit row for a refused or running operation proves nothing. Automatic reconciliation waits on Q-611; until then each unknown outcome is a human-visible alert.
2.13 **(P) Instance loss.** Losing the volume loses every unforwarded record: bounded by capacity, not by time. The 30 s rule limits how long writes run without a confirmed checkpoint; it is an admission threshold, not a loss bound. Mitigations: replicated in-country block storage if INF-001 provides it (UNVERIFIED); a decommissioned volume is drained to zero by a forwarder-only process before deletion; for configuration writes the adapter's tenant-database audit is a second trail. GLB-T29 covers only that the alerts and thresholds fire.
2.14 **(P) Replay and deduplication.** The gateway never re-sends a request to the engine. A write route is registered only with a **durable deduplication provider for that exact operation**: the adapter's tenant-database store (ADR-0041) for configuration operations, or the Tool API store that Tool API section 6 requires for business writes (Q-613). The deduplication key binds tenant, operation, `Idempotency-Key`, input hash **and the authenticated subject**: for adapter operations, whose contract key is `(tenant, operation, key)` (engine-adapter.md section 7), the gateway forwards a keyed digest of `(subject, Idempotency-Key)` in the adapter's key grammar (PLT-030 must confirm that grammar before code). A different subject presenting the same key gets `idempotency_conflict` and no stored content. Every replay first passes authentication and route permission, and a stored business result is disclosed only after the Tool API scope check on the records it contains is re-run. The edge adds no idempotency store.
2.15 **(P) Observability.** Internal-listener metrics per stream: records, bytes, reserved, oldest unforwarded age, forward failures, quarantine, unknown outcomes, admission refusals, preauth aggregates, seconds since last confirmed checkpoint, drop count. Alerts: drop count or quarantine above zero, any fail-closed check, oldest age above 60 s, no confirmed checkpoint for 15 s.

### 3. Identity, tenant binding and caller permissions
3.1 **(Inherited, ADR-0007 items 3 and 10)** The tenant comes from the request host only, after canonical hostname validation (PLT-003, SEC-021). The customer token from the `__Host-session` cookie is verified with `verify_customer_token(token, host_tenant)`: issuer, audience naming that tenant, tenant claim equal to the host tenant, realm `customer`, active membership and current session version. Any failure is `403 permission_denied` (401 maps to `permission_denied` until Q-302 is answered). The tenant is never read from a path, query, body or header.
3.2 **(P) Order of checks.** Listener framing and caps (1.2, 4), host validation and route and method match (3.3) run first. Then a local, CPU-bounded signature and claims check of the token for the host tenant (identity's `decode`, no store lookup). A request that passes goes on to the membership and session-version check, role resolution and the `tenant` spool, and never touches `preauth` admission, so a full `preauth` spool cannot block verification. A request with no token or a failing one meets the per-source and global pre-authentication limits (SEC-009 port; a local token bucket until it exists) and the `preauth` spool. PLT-030 must specify, with identity's owner, how the signature-only pre-check is exposed before code.
3.3 **(P) Declared methods and effects.** A `Route` declares its allowed methods and one effect, `read` or `write`. A `write` route may use only POST, PUT, PATCH or DELETE; registration refuses a `write` route on GET or HEAD, and a `read` route's handler receives only a read-only upstream client. Any undeclared method on a registered path returns the same our-404 as an unknown path. Intent records, the Origin check (3.7) and the `Idempotency-Key` requirement follow the declared effect, not the verb, replacing `MUTATING_METHODS` (`gateway.py:29`) as the trigger.
3.4 **(Inherited)** Staff tokens are a separate realm and are refused on customer routes (ADR-0007 item 7). **(P)** The edge accepts no agent token: agent and department-assistant calls go through the Tool API path (ADR-0043, agent-least-privilege).
3.5 **(P) Route permission, read authoritatively.** A `Route` declares one required permission id. On every request the gateway resolves the caller's permissions through the `RoleResolver` port and denies on any failure, timeout, malformed or empty result. **(Inherited, ADR-0060 items 8 to 11)** The read is authoritative (never an asynchronous replica, maximum age 0); the result must name the claims' tenant and pass the store's integrity check; a tenant fenced after a restore denies; a widening change is not usable until its sync is verified. This is a coarse gate: scope, field rules, approvals (including the re-check when an approved action executes, ADR-0060 item 10) stay with the Tool API (contract section 4, OPR-004), and the engine evaluates the call as the caller's shadow user (ADR-0007 item 11). The real store is read only after SEC-024 is accepted with its own security review (ADR-0060 item 15); until then a fake only.
3.6 **(P) Step-up is not optional for admin operations.** Registration looks up each route's permission in the permission catalogue (admin-kind per ADR-0007 item 6 and the Tool API tool kinds). For an admin-kind permission the route must declare `max_auth_age_s`, and every request needs `mfa_satisfied` true **and** a fresh `auth_time`; a route with an admin-kind permission and no step-up, or a permission of unknown kind, is refused at startup. PLT-030 must specify the catalogue port it reads before code.
3.7 **(P) Session cookie and cross-site writes.** Session-cookie issuance and clearing belong to identity, not to the upstream: PLT-030 removes the mapping of an expired engine `sid` to clearing our cookie (`gateway.py:237`); an engine session cookie in any response is dropped and raises an internal alert, and nothing an upstream returns can change the browser session. Identity sets the cookie `HttpOnly; Secure; Path=/; SameSite=Strict` (today's clear directive uses `Lax`, `headers.py:27`). A request must carry at most one `__Host-session` cookie (duplicates are refused). No CORS headers are ever sent. A `write` request must carry exactly one `Origin` equal to the tenant's canonical origin, checked before the intent record.
3.8 **(P) Handler input.** `UpstreamRequest` gains `audit_id`, `tenant_id` and `subject` from the verified claims, and an upstream client with the caps of section 4; the handler selects the tenant site and shadow user from these fields only.

### 4. Size caps and time limits (all values (P); listener = at the listener and every hop, app = in the application)
| Item | Cap | Where | When exceeded |
|---|---|---|---|
| Raw request target | 2,048 bytes | listener, app | 400 `invalid_arguments`, `details.limit = "path"` |
| Request headers | 64 fields, 8 KiB per field, 16 KiB total | listener, app | 400 `invalid_arguments`, `limit = "headers"` |
| Framing | 1.2 rules; a body needs one valid `Content-Length`; any `Expect` refused | listener, app | 400, connection closed, listener event (1.5) |
| Query string | refused unless the route declares parameters; then 2,048 bytes, declared names only | app | 400 `invalid_arguments`, `limit = "query"` |
| Request body | route default 256 KiB, declared up to 4 MiB; file uploads out of scope | listener (ceiling), app (route cap, counting reader stops at cap + 1) | 400 `invalid_arguments`, `limit = "request_body"` |
| `Idempotency-Key` | required on `write` routes; exactly a ULID or a UUID | app | 400 `invalid_arguments`, before the intent |
| Client header read / body read / response write | 10 s / 30 s / 30 s | listener | connection closed, listener event (1.5) |
| Upstream response headers | 100 fields, 32 KiB | upstream client | 500 `internal_error`, reason `upstream_too_large` |
| Upstream body | JSON route 2 MiB default, declared up to 16 MiB; `own_content_type` route declared, at most 25 MiB | upstream client (counting read, connection closed at cap + 1), core re-checks | same |
| Upstream JSON | depth 32, 200,000 values | linear pre-scan of the bytes before `json.loads` | 500 `internal_error`, reason `upstream_unparseable` |
| Memory per request | route upstream cap times 4 (raw bytes, parsed objects, built response; factor UNVERIFIED), 256 MiB per instance | reserved before the upstream read, **released only when the client response has closed** (last byte written, client gone, or write deadline) | 503 `engine_error` retryable, before the upstream call |
| Upstream connect / total | 2 s / 30 s | upstream client | read: 503 `engine_error` retryable; write: 4.2 |
| In-flight requests | 256 per instance | app | 429 `rate_limited` with our `Retry-After`, before the intent |

4.1 **(P)** Caps are checked before the intent record wherever possible. Error bodies never echo the oversize value. A dedicated `payload_too_large` code is Q-612; until then `invalid_arguments`. Because `UpstreamResponse` holds a complete body (`gateway.py:60`), the gateway hands handlers a capped upstream client (3.8) and the core check is a second line.
4.2 **(P) Write timeout.** If the upstream deadline passes after a write was sent, the outcome is unknown: the gateway records `reason: "upstream_timeout_unknown"` and answers `503 engine_error` retryable. A retry by the same subject with the same `Idempotency-Key` reaches the route's deduplication provider (2.14), which returns the stored or in-progress outcome: one effect even when the upstream committed before the client timed out. Long-running operations (apply, up to the adapter's one-hour deadline) are never held on a synchronous request; their routes return the operation reference.

### 5. Audit record (identity-bound)
5.1 **(P) Fields of every record**, intent and outcome: `audit_id`, `phase` (`intent`, `outcome`, `reconcile`, `key_rotation`, `aggregate`), `instance_id`, `stream`, `seq`, `key_id`, `chain`, `ts` (UTC, milliseconds), `route` (our registered template, never the engine path), `method`, `param_count`, `path_normalisation`, `identity` (`verified` or `none`), and when verified: `tenant_id`, `user_id` (token subject), `realm`, `session_version`, `token_id`, `mfa_satisfied`, `auth_time`; `role_ids` and the role store's version as read for the decision (once the store exists); `idempotency_key` (random by grammar, so stored as is); `request_bytes`; on outcome also `status`, `reason`, `error_code`, `latency_ms`, `upstream_correlation` (the `correlationId` sent). Every field has a fixed maximum length so the serialised record stays within the 4 KiB ceiling (2.3).
5.2 **(P) Redaction.** A raw path can carry pasted credentials or personal data, so the raw path is no longer recorded (it is today, `gateway.py:269`). A matched request records the route template and a keyed digest of its parameters; a refused path records its length, a keyed digest and `path_normalisation`. The body is recorded only as `request_digest = HMAC(digest_key, body)` with a versioned key separate from the chain key: a plain hash of a low-entropy body (an amount, a yes or no) could be guessed offline, while a keyed digest still lets an investigator who holds the key confirm a disputed body. Source address appears only as a keyed digest for throttling. Never recorded: tokens, cookies, `Authorization` values, bodies, query values, engine headers, engine field names or engine text. Redacted arguments belong to the Tool API's `tool.called` record (Q-610).
5.3 **(Inherited, contract section 8)** Tool API section 8 lists `session_id`. `token_id` changes on every refresh rotation and `session_version` only tracks revocation, so neither links one session's records. **(P)** Record both now; **no live route until Q-609 is answered and a stable verified session id (or the accepted alternative) is in the claims**, with a test that a refresh keeps the linkage (GLB-T40).
5.4 **(P) Unauthenticated and cross-tenant attempts** (`identity: none`, or a token for another tenant) go to the separate `preauth` spool (2.1, 2.10) and to a platform security stream, with the host tenant marked unverified; they never enter a tenant's own audit view.
5.5 **(P) Deprovisioning.** A closed tenant's records may sit in `records`, `open_intents`, `quarantine`, the `preauth` spool (host-tenant field) or a detached recovery volume. ADR-0040's deprovisioning verification (step 8) must probe all five on every instance and every retained volume and find none for the tenant before certifying; quarantined records of that tenant are resolved or destroyed under the deprovisioning approvals. The workflow change belongs to the ADR-0040 owner (partner); it is not made here.

### 6. Engine invisibility at the binding
6.1 **(Inherited, ADR-0016)** Everything a caller can observe is ours: paths, headers, cookies, error shapes, `audit_id` format.
6.2 **(P)** No `Server` or `X-Powered-By` header; every parser-generated refusal at the listener and at each hop uses our JSON error body (1.2). Internal listeners, metric names and logs may name the engine; the public listener may not.
6.3 **(P) Internal pre-public probe (ADR-0040 step 10, `PROV-T32`).** The first route is bound on an internal-only hostname that no public DNS name points to, with synthetic tenant data. Two suites must pass there, through every configured hop, before the public hostname is bound to the same configuration: (a) the QA-016 crawler (paths, headers, cookies, error bodies over ordinary HTTP); (b) a wire-level malformed-request suite over raw sockets (duplicate and invalid `Content-Length`, `Content-Length` with `Transfer-Encoding`, obsolete folding, conflicting `Host`, oversize headers, slow headers and bodies), checking each refusal is ours, closes the connection and emits a listener event. Any later listener, proxy or route change repeats both.
6.4 Timing and size side channels against the engine are not addressed (UNVERIFIED whether they reveal the engine).

### 7. Failure summary
| Situation | Write | Read |
|---|---|---|
| Spool commit fails before handler | 503 `audit_unavailable`, handler not called | 503 `audit_unavailable` |
| `tenant` spool at 90%, or no confirmed checkpoint for 30 s | 503 `audit_unavailable` | served until 100% |
| One tenant above its 20% share | 503 for that tenant only | served until 100% |
| `preauth` spool full | n/a | unverified requests 429, aggregate record; verified traffic unaffected |
| Outcome commit fails after effect | real result, outcome retried, open row kept; else `unknown_after_restart` | 503 `audit_unavailable` |
| Crash mid-request | open row survives any prune; recovery rebuilds the outcome from it | outcome may be missing (no effect) |
| Checkpoint, chain, receipt or open-row check fails | writes and forwarding stop, page; at start, no writes | served until capacity |
| Identity or role store unreachable | 403 `permission_denied`, outcome recorded | same |
| Upstream timeout | 503 retryable, unknown outcome, retry by the same subject and key | 503 retryable |

### 8. Order of work and the live-route gate
PLT-028 (local durability) and PLT-032 (forwarding and integrity) both come before PLT-029 (binding), per the README's spool-before-binding rule and Q-302. PLT-028 builds against a fake `AuditStore`. No live route is registered until all of these hold: PLT-028, PLT-032, PLT-029 and PLT-030 are merged with their tests; Q-614 is agreed and SEC-008 accepts records through that port with the checkpoint, receipt and quarantine semantics of 2.6 to 2.9; SEC-024 is accepted after its own security review and GOV-065 is accepted (ADR-0060 item 15); SEC-009 limits sit in front of the binding; Q-609 (stable session id) and Q-302 are answered and implemented; every `write` route has its deduplication provider (2.14, Q-613); both pre-public suites (6.3) have passed; and a security review by a different model has run on the bound gateway. The go-live row is G3, so no partner row in G2 waits on an Eldon row in G2 (ADR-0025).

## Threats and the test that proves each (proposed test names; row in brackets)
| ID | Threat | Proposed test |
|---|---|---|
| GLB-T01 | Killed after intent, before handler | `test_spool_intent_survives_sigkill_before_handler` [028] |
| GLB-T02 | Killed after effect, before outcome | `test_restart_closes_open_intent_as_unknown` [028] |
| GLB-T03 | Spool near full | `test_high_water_refuses_write_without_handler_call` [028] |
| GLB-T04 | Store down for hours | `test_forwarder_outage_backpressure_zero_drops` (PLT-032) |
| GLB-T05 | Crash between store commit and local prune | `test_redelivery_returns_original_receipts` (PLT-032) |
| GLB-T06 | Records edited while running | `test_live_tampering_fails_closed` (PLT-032) |
| GLB-T07 | Rejected or conflicting record | `test_rejected_and_conflict_keep_verbatim_evidence_and_quarantine` (PLT-032) |
| GLB-T08 | Two writers on one spool | `test_second_spool_writer_refused` [028] |
| GLB-T09 | Wall clock moves backwards | `test_clock_backwards_keeps_seq_order` [028] |
| GLB-T10 | Token for tenant X on host Y | `test_cross_tenant_token_denied_and_kept_out_of_tenant_audit` (joins SEC-004) [030] |
| GLB-T11 | Tenant smuggled in request data | `test_tenant_never_taken_from_request` [030] |
| GLB-T12 | Staff or agent token | `test_staff_and_agent_tokens_refused` [030] |
| GLB-T13 | Revoked member keeps access | `test_session_version_bump_denies_next_request` [030] |
| GLB-T14 | Role outage, replica lag or bad snapshot | `test_role_lookup_failure_lag_or_bad_snapshot_denies` [030] |
| GLB-T15 | Forged identity fields | `test_audit_identity_fields_only_from_claims` [030] |
| GLB-T16 | Secrets or bodies in audit | `test_audit_record_contains_no_token_cookie_body_or_raw_path` [030] |
| GLB-T17 | Oversize body | `test_request_body_cap_declared_and_undeclared` [029] |
| GLB-T18 | Header flood or slow client | `test_listener_header_caps_and_slow_client_deadline` [029] |
| GLB-T19 | Malformed Idempotency-Key | `test_idempotency_key_grammar_before_intent` [029] |
| GLB-T20 | Oversize upstream | `test_upstream_caps_abort_in_transport` [029] |
| GLB-T21 | Deep or huge upstream JSON | `test_upstream_json_depth_and_count_caps` [029] |
| GLB-T22 | Upstream commits, client retries | `test_write_route_without_dedupe_refused_and_retry_single_effect` [029] |
| GLB-T23 | Server library reveals itself | `test_listener_parser_errors_are_ours_without_server_header` [029] |
| GLB-T24 | Health or metrics public | `test_health_and_metrics_absent_on_public_listener` [029] |
| GLB-T25 | Outsider floods audit | `test_unauthenticated_denials_not_in_tenant_audit` [030] |
| GLB-T26 | Cross-site write | `test_cross_origin_write_refused_before_intent` [030] |
| GLB-T27 | Undeclared query parameters | `test_undeclared_query_refused` [029] |
| GLB-T28 | Handler takes tenant or user from request | `test_handler_receives_only_claims_tenant_and_subject` [030] |
| GLB-T29 | Volume loss with backlog (detection only) | `test_age_alerts_and_unconfirmed_write_threshold_fire` (PLT-032) |
| GLB-T30 | Intent pruned, then crash | `test_pruned_intent_recovered_with_identity_fields_from_open_row` [028] |
| GLB-T31 | Crash during recovery | `test_crash_during_recovery_resumes_without_double_close` [028] |
| GLB-T32 | Suffix truncation or older file restored | `test_truncation_and_rollback_detected_against_store_checkpoint` (PLT-032) |
| GLB-T33 | Key rotation | `test_key_rotation_chain_verifies_across_keys` (PLT-032) |
| GLB-T34 | Partially committed batch, gap | `test_mixed_batch_prunes_only_to_watermark_and_gap_refused` (PLT-032) |
| GLB-T35 | Pre-auth flood | `test_verified_requests_complete_during_sustained_preauth_saturation` [028] |
| GLB-T36 | Request smuggling | `test_listener_refuses_duplicate_cl_cl_te_and_ambiguous_host` (real listener and proxy) [029] |
| GLB-T37 | Write through a safe or undeclared method | `test_write_effect_refused_on_safe_methods_and_undeclared_method_404` [029] |
| GLB-T38 | Admin operation without step-up | `test_admin_permission_route_without_step_up_refused_at_registration` [030] |
| GLB-T39 | Unsynced widening, fenced tenant | `test_unsynced_widening_and_fenced_tenant_denied` [030] |
| GLB-T40 | Refresh breaks audit linkage | `test_refresh_rotation_keeps_session_linkage` [031] |
| GLB-T41 | Upstream cookie changes the session | `test_upstream_cookies_cannot_set_or_clear_session` [030] |
| GLB-T42 | Concurrent near-limit responses, slow clients | `test_memory_reservation_held_until_slow_client_response_closes` [029] |
| GLB-T43 | Secret pasted into a path | `test_secret_bearing_path_not_in_audit` [030] |
| GLB-T44 | Closed tenant's records survive | `test_deprovision_probe_covers_open_rows_quarantine_and_detached_volumes` [028] |
| GLB-T45 | Stalled tenant beside a healthy one | `test_tenant_over_share_or_quarantined_does_not_block_other_tenant` [028] |
| GLB-T46 | Open row deleted on disk | `test_missing_or_bad_mac_open_row_detected_at_recovery` [028] |
| GLB-T47 | Cross-principal replay of a stored result | `test_same_key_other_subject_gets_conflict_without_content` [030] |
| GLB-T48 | Lost checkpoint reply; idle tail truncated | `test_lost_reply_retry_and_idle_truncation_detected` (PLT-032) |
| GLB-T49 | Listener refusal leaves no audit | `test_listener_timeouts_and_refusals_reach_preauth_spool_bounded` [029] |

## Alternatives rejected
- **Keep the in-memory deque and bind HTTP.** Fails README precondition 1.
- **Audit synchronously in the tenant database.** Needs database credentials for every tenant (beyond ADR-0007 item 11), has no home for unauthenticated attempts, and makes denials unauditable during a tenant database outage.
- **Control-plane regional database or regional role store as the audit store.** Own custody rules (`S22`, ADR-0060 item 6); the audit store of record is SEC-008's decision.
- **Write-through on every request.** Every request fails when the store blips; kept as a possible per-route option.
- **Startup-only verification, highest-`seq` acks, hash-only placeholders.** Miss suffix deletion, rollback, partial batches, and cannot re-verify the original HMAC (2.7 to 2.9).
- **One shared spool for verified and unverified traffic.** An outsider could exhaust storage needed by tenants (2.1, 2.10).
- **An edge idempotency store.** Duplicates the store that owns each operation's deduplication (2.14).
- **WSGI or a proxy alone for HTTP safety.** WSGI cannot see framing; a proxy alone can be misconfigured (1.2).

## Consequences
- Easier: PLT-024's preconditions become testable rows; gateway, Tool API and adapter records join through the existing `correlationId`; crash, outage, restart and tampering behaviour is specified per protocol step.
- Harder: per instance a persistent, encrypted, in-country volume, two spools, a lock discipline and a store credential; drains before scale-down; operators own quarantine and unknown-outcome alerts; the production listener needs a licence record; the live route waits on SEC-008, SEC-009, SEC-024 and GOV-065 (earlier gates) and on Q-302, Q-609, Q-613 and Q-614.
- Residual risks: a lost volume loses every unforwarded record (2.13); records written after the last confirmed checkpoint can be removed undetected by someone with volume write access (2.7); unknown outcomes need a human until Q-611; timing side channels (6.4); all (P) values, the overhead and memory factors and crash durability on the production volume are UNVERIFIED.
- Must be done: PLT-028, PLT-032, PLT-029, PLT-030, PLT-031; Q-609 to Q-614 by Eldon's lane; the ADR-0040 deprovisioning probe (5.5) by its owner.

## Follow-up plan rows (in PLAN as PLT-028 to PLT-032)
1. PLT-028: local audit spool durability and recovery (sections 2.1 to 2.5, 2.10, 2.11, 5.5, 7): `tenant` and `preauth` spools, 4 KiB record ceiling, records and `open_intents` with authenticated recovery metadata, chained writes with versioned keys, persisted atomic reservations, tenant share, recovery and missing-row check, against a fake `AuditStore`; tests GLB-T01 to T03, T08, T09, T30, T31, T35, T44 to T46. G2, depends PLT-027, partner.
2. PLT-032: audit forwarding and integrity conformance (sections 2.6 to 2.9, 2.12, 2.13, 2.15): forwarder, checkpoint, receipt and quarantine protocols, per-instance store credential, a conformance suite that any `AuditStore` (the fake now, SEC-008 later) must pass, metrics and alerts; tests GLB-T04 to T07, T29, T32 to T34, T48. G2, depends PLT-028, partner.
3. PLT-029: HTTP binding skeleton with caps and time limits (sections 1, 3.3, 4, 6): production listener choice with licence record, listener and app rules and listener events tested against the real listener and proxy configuration, declared methods and effects, capped upstream client and memory reservation, no live route; tests GLB-T17 to T24, T27, T36, T37, T42, T49. G2, depends PLT-027, PLT-028, PLT-032, partner.
4. PLT-030: identity-bound audit and tenant binding (sections 3, 5): signature pre-check then membership verification, check order, fake `RoleResolver` with the authoritative-read rules, step-up mandatory for admin permissions, identity-owned session cookie, Origin check, subject-bound deduplication keys, redacted fields and keyed digests; tests GLB-T10 to T16, T25, T26, T28, T38, T39, T41, T43, T47 (GLB-T10 joins SEC-004). G2, depends PLT-027, PLT-028, partner.
5. PLT-031: first live route (section 8): `AuditStore` connected to SEC-008 after Q-614 is agreed and its conformance suite passes, real role reads, SEC-009 limits, a deduplication provider per write route, both pre-public suites (6.3), stable session id and GLB-T40, security review by a different model; gated on Q-302, Q-609, Q-613 and Q-614. G3, depends PLT-028, PLT-032, PLT-029, PLT-030, SEC-008, SEC-009, SEC-024, GOV-065, QA-016, partner.

## Supersedes
none
