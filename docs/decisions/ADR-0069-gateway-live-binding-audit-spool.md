# ADR-0069: Gateway live binding: durable audit spool, identity-bound audit records, size caps

Status: Proposed
Owner: partner
Approved by: pending (security review by a different model, then both founders; Tier 3 under ADR-0035 because it touches auth, tenancy and audit, RULES 42)

Plan ID: PLT-027 (G2). Design only. **No live binding, server, route or store is delivered by this ADR**; the code is in the follow-up rows at the end. Builds on [ADR-0016](ADR-0016-engine-invisibility.md) (engine invisibility), [ADR-0007](ADR-0007-identity.md) (identity, tokens, shadow users), [ADR-0060](ADR-0060-role-assignments-in-regional-store.md) (regional role store and its security conditions), [ADR-0040](ADR-0040-tenant-provisioning-service.md) (control-plane regional database, route registration gate) and [ADR-0041](ADR-0041-durable-adapter-state-on-tenant-database.md) (adapter state, idempotency and audit in the tenant database). Contradicts none of them; where a point needs another lane's change it is listed as a question, not decided.

**How to read this ADR.** Items marked **(Inherited)** restate an existing Accepted or Proposed decision and add nothing. Items marked **(P)** are new proposed choices of this ADR, including every number; a reviewer may change any (P) value without changing the structure. UNVERIFIED marks claims not tested on real infrastructure.

## Context
- PLT-024 built the customer-facing API edge core in `services/gateway/edge/` (`gateway.py`, `paths.py`, `projection.py`, `headers.py`, `errors.py`, `markers.py`; summary in [services/gateway/README.md](../../services/gateway/README.md)). It is pure in-process logic tested with fake upstreams: deny-by-default `/v1/` routes, allow-list projection of engine JSON, header and cookie filtering, engine-error mapping, and an audit sink that is required.
- Its audit is process memory: an `intent` record before a mutating handler, an `outcome` after every request, a 1000-record deque for outcome records that failed after a possible effect, reservation at 900 to return `503 audit_unavailable`, and `audit_drop_count`. Process memory is not crash durable.
- The README and the PLT-024 logs (2026-11-18 and 2026-11-20) set three hard preconditions before any HTTP binding or live route: (1) a durable spool with recovery, retry and observable drop and backlog health; (2) tenant, user and session from verified identity bound to every audit record (Tool API section 8); (3) request-body, Idempotency-Key and upstream-body caps with regression tests (PR #123 review item 5). Q-302 asks Eldon to add `unauthenticated` and to ratify `audit_unavailable`.
- Identity exists as a core (PLT-005, Eldon's lane): `verify_customer_token(token, tenant_id)` returns `AccessClaims` (issuer, audience, subject, tenant, realm, session_version, mfa_satisfied, auth_time, token_id, times; no roles) after checking the membership and its session version. Roles come from a `RoleResolver` port; ADR-0060 item 15 forbids reading real roles from the regional store before SEC-024 (store design ADR) and GOV-065 (Tool API wording) are accepted.
- The store of record for audit is SEC-008 (append-only, hash-chained, exported off-box; Eldon's lane, G2, todo; threat T56). Its location is not decided, and this ADR does not decide it.

## Decision

### 1. Shape of the binding
1.1 **(P)** The binding is a thin HTTP adapter around the existing `Gateway.handle`: it parses HTTP, enforces the caps of section 4, authenticates (section 3), builds a `GatewayRequest` carrying the verified principal, and serialises the `GatewayResponse`. All policy stays in the edge core so it remains testable without a socket.
1.2 **(P)** The binding is a WSGI callable written with the standard library (no new dependency). Tests run it under `wsgiref`. The production HTTP server is a separate choice with its own licence record and plan row; `wsgiref` and `http.server` are never the production server (no slow-client protection). An outer reverse proxy, if INF-001 chooses one, enforces the same outer caps as defence in depth; the application never relies on it and enforces every cap itself.
1.3 **(Inherited, ADR-0016)** The engine runs on an internal network; the public listener reaches it only through route handlers over the engine adapter.
1.4 **(P)** Health, readiness and metrics are served on a second listener bound to the internal network only, never on the public listener and never under `/v1/`.

### 2. Durable audit spool
2.1 **(P) What it is.** Each gateway instance owns one local, append-only spool: a SQLite database (standard library `sqlite3`) in WAL mode with `synchronous=FULL`, on a persistent, encrypted volume in the same country and placement as the instance (ADR-0006). It is a **delivery buffer, not a store of record**: it serves no reads except to its own forwarder and recovery, holds a record only until the store of record acknowledges it, is never backed up or restored as a source of truth, and is never shared between instances or over a network file system. It is therefore not a second regional store, and it does not touch the control-plane regional database (ADR-0040) or the regional role store (ADR-0060).
2.2 **Why SQLite here does not contradict ADR-0041.** ADR-0041 keeps adapter state out of SQLite because idempotency keys and the effects they describe must restore together with the tenant database. The spool holds no state that must agree with tenant data after a restore; its only job is to survive a process crash until a record reaches SEC-008. Adapter idempotency and adapter audit stay in the tenant database exactly as ADR-0041 says.
2.3 **(P) Single writer.** An instance takes an exclusive lock on its spool at start (an advisory file lock plus a row holding `instance_id` and a fencing counter). A second process that finds the lock held refuses to start serving.
2.4 **(P) Write rule (replaces the deque).** A record is durable when its spool transaction has committed. Rules, keeping PLT-024's semantics:
- Mutating request: the `intent` record commits **before** the handler runs. If the commit fails, or admission (2.6) refuses, the answer is `503 audit_unavailable` and the handler is not called.
- Read, denial or validation failure: the `outcome` record commits before the response is sent; if it cannot, the answer is `503 audit_unavailable` (P: today this path returns 500 `internal_error`; 503 tells the caller the condition is temporary).
- After a possible mutating effect: if the outcome commit fails, the real result is still returned (an error would invite a duplicate). The outcome stays in a small in-process retry slot (one per reserved request, so it is bounded by admission) and is retried; if the process dies first, restart recovery (2.8) closes the intent.
2.5 **(P) Integrity inside the spool.** Each record carries `instance_id`, a per-instance monotonic `seq` (the ordering authority; wall-clock time can move backwards) and `chain = HMAC(key, prev_chain || canonical_record)`. The key is a secret registered under ADR-0038 by the follow-up (no id allocated here). This detects truncation, deletion or rewrite of unforwarded records by someone who can read the disk but not the key. The tenant-wide hash chain and off-box export remain SEC-008's (T56); the spool chain is local and does not replace it.
2.6 **(P) Capacity and admission.** Every record is bounded (section 5, at most 4 KiB), so capacity is deterministic: 100,000 records or 512 MiB, whichever comes first. New mutating requests are refused with `503 audit_unavailable` once `backlog + in-flight reservations >= 90%` of capacity (today's 900 of 1000 ratio); reads and denials are refused once `backlog + reservations` reaches 100%. Each admitted mutation reserves one outcome slot before its intent, as now, so a full spool can never force the loss of an outcome. `audit_drop_count` stays as a counter that must always be zero; any increase pages.
2.7 **(P) Forwarder.** A forwarder (separate thread, same process, or a separate process holding the same lock family) reads committed records in `seq` order and delivers batches (at most 500 records or 1 MiB) to an `AuditStore` port. Delivery is at-least-once; storage is exactly-once because the store of record deduplicates on `(audit_id, phase)` and rejects the same key with a different hash as a conflict. On acknowledgement the forwarder records the highest acked `seq` and deletes acked rows in the same transaction. Failure backs off from 1 s doubling to 60 s with jitter, forever; nothing is dropped. A record the store rejects permanently (schema or conflict) moves to a quarantine table inside the spool, still counts against capacity, pages, and is released only by an audited operator action after the cause is fixed. Until SEC-008 provides the store, the port has a test double only and **no live route may be registered** (section 8).
2.8 **(P) Restart and recovery.** On start an instance is not ready until it has: taken the lock; opened the spool and verified the chain from the last acked `seq` to the tail (a break fails closed: no serving, page an operator, keep the file for investigation); scanned for intents without an outcome. Every such intent belonged to the previous process, so the instance appends an `outcome` record with `status: null`, `reason: "unknown_after_restart"` (a new record; nothing is ever edited). It then starts the forwarder and only then reports ready.
2.9 **(P) Reconciliation of unknown outcomes.** An unknown outcome means the effect may or may not have happened. The gateway passes its `audit_id` to the handler (2.11); when the adapter contract can carry it as a correlation id (question for Eldon's lane, contracts/), a reconciliation job asks the adapter whether an operation with that correlation id exists in `adapter_audit_log` (tenant database, ADR-0041) and appends a `reconcile` record with the finding. Until then each unknown outcome is a human-visible alert, not a silent gap.
2.10 **(P) Instance loss.** The spool survives a process crash and restart on the same volume. Loss of the volume itself loses unforwarded records; this is the honest residual. Mitigations: the volume is replicated block storage if INF-001 provides it in-country (UNVERIFIED), `oldest_unforwarded_age_s` pages above 60 s so the loss window stays small, a decommissioned instance's volume is attached to a forwarder-only recovery process and drained to zero before deletion, and for mutations that reached the engine the adapter's own audit in the tenant database remains as a second trail (ADR-0041). Write-through (store of record acknowledges before the response) is not the default (2.13) but a route class may require it later.
2.11 **(P) One audit id end to end.** The gateway mints `audit_id` (`aud_<ULID>`, as now) once per HTTP request, returns it to the caller, and hands it to the handler in `UpstreamRequest` together with the verified tenant and principal (never as an engine header). The Tool API layer and the adapter reuse it, so `tool.called` (Tool API section 8), the gateway record and the adapter audit join on one key. Whether the Tool API adopts it is Eldon's call (question).
2.12 **(P) Replay means records, never requests.** "Replay" in this ADR is re-delivery of spooled records to the store of record. The gateway never re-sends a request to the engine. A client retry of a mutation is safe only with the same `Idempotency-Key`, which the gateway forwards and the adapter deduplicates in the tenant database for at least 30 days (ADR-0041). The edge adds no idempotency store of its own (that would be a second store with its own restore story).
2.13 **(P) Observability.** Metrics on the internal listener: `audit_spool_records`, `audit_spool_bytes`, `audit_reserved`, `audit_oldest_unforwarded_age_s`, `audit_forward_failures_total`, `audit_quarantine_records`, `audit_unknown_outcomes_total`, `audit_admission_refusals_total`, `audit_drop_count`. Alerts: drop count above zero, quarantine above zero, chain break, oldest unforwarded age above 60 s, admission refusals above zero for 1 minute.

### 3. Identity, tenant binding and caller permissions
3.1 **(Inherited, ADR-0007 items 3 and 10)** The tenant comes from the request host only, after canonical hostname validation (PLT-003, SEC-021). The customer token from the `__Host-session` cookie (HttpOnly, Secure, host-only) is verified with `verify_customer_token(token, host_tenant)`: issuer, audience naming that tenant, tenant claim equal to the host tenant, realm `customer`, active membership and current session version. Any failure is `403 permission_denied` (401 maps to `permission_denied` until Q-302 is answered). The tenant is never read from a path, query, body or header.
3.2 **(P)** This replaces PLT-024's interim rule that refuses every `__Host-session` cookie; the replacement ships only in the follow-up that also binds identity to audit records, never alone.
3.3 **(Inherited)** Staff tokens are a separate realm and are refused on customer routes (ADR-0007 item 7). The edge accepts no agent token: agent and department-assistant calls go through the Tool API path (ADR-0043, agent-least-privilege), not through a browser session (P: this edge serves human sessions only).
3.4 **(P) Route permission.** A `Route` declares one required permission id. On every request the gateway resolves the caller's permissions for the verified tenant and subject through the `RoleResolver` port, with no cache (ADR-0060 item 10, maximum age 0), and denies on any failure, timeout, malformed or empty result (ADR-0060 item 9). This is a coarse gate. Scope filters, field rules, approvals and agent rules remain the Tool API's (contract section 4, OPR-004) and the engine still evaluates the call as the caller's shadow user (ADR-0007 item 11). The edge never widens what those layers allow.
3.5 **(P) Step-up.** A route may declare `max_auth_age_s`; the request is refused unless `auth_time` is within it, for admin-kind routes (ADR-0007 item 6).
3.6 **(P) Cross-site requests.** No CORS headers are ever sent. A mutating request must carry an `Origin` equal to the tenant's own origin; a missing or different `Origin` is refused before the intent record. The cookie stays `SameSite=Strict`.
3.7 **(P) Handler input.** `UpstreamRequest` gains `audit_id`, `tenant_id` and `subject` taken from the verified claims; the handler selects the tenant site and shadow user from these fields only. Routes registered before this change are refused at startup.

### 4. Size caps and time limits (all values (P))
| Item | Cap | When exceeded |
|---|---|---|
| Raw request target | 2,048 bytes | 400 `invalid_arguments`, `details.limit = "path"`; outcome recorded |
| Request headers | at most 64 fields, 8 KiB per field, 16 KiB total | 400 `invalid_arguments`, `limit = "headers"` |
| Query string | refused unless the route declares query parameters; then 2,048 bytes and only declared names | 400 `invalid_arguments`, `limit = "query"` |
| Request body | route default 256 KiB, a route may declare up to 4 MiB; file uploads are out of scope | 400 `invalid_arguments`, `limit = "request_body"`, decided from `Content-Length` before reading, and by a counting reader that stops at cap + 1 byte |
| Request framing | a body requires `Content-Length`; any request `Transfer-Encoding` and any `Expect` header are refused (no chunked requests, no smuggling ambiguity) | 400 `invalid_arguments` |
| `Idempotency-Key` | required on mutating routes; exactly a ULID (26) or a UUID (36) | 400 `invalid_arguments`, before the intent record |
| Upstream response headers | 100 fields, 32 KiB total | 500 `internal_error`, reason `upstream_too_large` |
| Upstream body, JSON route | 2 MiB default, route may declare up to 16 MiB | read stops at cap + 1, upstream connection closed, 500 `internal_error`, reason `upstream_too_large` |
| Upstream body, `own_content_type` route | route declares, at most 25 MiB | same |
| Upstream JSON | depth 32, 200,000 values | 500 `internal_error`, reason `upstream_unparseable` |
| Client header read / body read | 10 s / 30 s total | connection closed; outcome recorded when the request line was read |
| Upstream connect / total | 2 s / 30 s | read: 503 `engine_error` retryable; mutation: see 4.2 |
| In-flight requests per instance | 256 | 429 `rate_limited` with our own `Retry-After` (SEC-009 may refine), before the intent record |

4.1 **(P)** Caps are checked before the intent record wherever possible, so an oversize request never consumes spool capacity or reaches the engine. The error body never echoes the oversize value. Whether a dedicated `payload_too_large` (413) code is wanted is Eldon's contract decision (question); until then the code is `invalid_arguments`.
4.2 **(P) Mutation timeout.** If the upstream deadline passes after a mutation was sent, the outcome is unknown: the gateway records `reason: "upstream_timeout_unknown"` and answers `503 engine_error` retryable. A retry with the same `Idempotency-Key` is deduplicated by the adapter (ADR-0041), which returns the stored or `in_progress` outcome. Long-running operations (apply, up to the adapter's one-hour deadline) are never held on a synchronous request; their routes return the adapter's operation reference.

### 5. Audit record (identity-bound)
5.1 **(P) Fields of every record**, intent and outcome: `audit_id`, `phase` (`intent`, `outcome`, `reconcile`), `instance_id`, `seq`, `chain`, `ts` (UTC, milliseconds), `route` (our registered prefix, never the engine path), `method`, `path` (raw, 256 characters), `normalised_path`, `path_normalisation`, `identity` (`verified` or `none`), and when verified: `tenant_id`, `user_id` (token subject), `realm`, `session_version`, `token_id`, `mfa_satisfied`, `auth_time`; `role_ids` and the role store's version as read for the decision (once the store exists); `idempotency_key` (validated grammar only); `request_bytes` and `request_sha256`; on outcome also `status`, `reason`, `error_code`, `latency_ms`. Source address appears only as a keyed hash for SEC-009 throttling.
5.2 **(P) Never recorded:** tokens, cookies, `Authorization` values, request or response bodies, engine headers, engine field names or engine text. Redacted arguments belong to the Tool API's `tool.called` record, not to this one.
5.3 **(Inherited, contract section 8)** Tool API section 8 lists `session_id`. The claims carry `token_id` and `session_version` but no stable session id. **(P)** Record those two now and add `session_id` when identity exposes one (question for Eldon).
5.4 **(P) Unauthenticated and cross-tenant attempts** (`identity: none`, or a token for another tenant) are written to a platform security stream with the host tenant marked as unverified; they never enter a tenant's own audit view, so an outsider cannot flood or poison a tenant's audit trail.
5.5 **(Inherited, ADR-0040 decision 8 step 5; data-retention.md)** A tenant's records in a spool exist only until forwarded; deprovisioning's verification step should find none for a closed tenant (the deprovisioning workflow adds the probe; not changed here).

### 6. Engine invisibility at the binding
6.1 **(Inherited, ADR-0016)** Everything a caller can observe is ours: paths, headers, cookies, error shapes, `audit_id` format.
6.2 **(P)** The binding sends no `Server` or `X-Powered-By` header and replaces every server-library default response (malformed request line, unsupported method, oversize header) with our JSON error body. Internal listeners, metrics names and logs may name the engine; the public listener may not. QA-016's crawl runs against the bound gateway before the first live route (ADR-0040 step 10, `PROV-T32`).
6.3 Timing and size side channels against the engine are not addressed by this ADR (UNVERIFIED whether they reveal the engine).

### 7. Failure summary
| Situation | Mutation | Read |
|---|---|---|
| Spool commit fails before handler | 503 `audit_unavailable`, handler not called | 503 `audit_unavailable` |
| Spool above admission level | 503 `audit_unavailable` | served until 100% |
| Outcome commit fails after effect | real result returned, outcome retried in process, else `unknown_after_restart` | 503 `audit_unavailable` |
| Store of record unreachable | served while capacity lasts; backlog grows; alerts | same |
| Process crash mid-request | intent durable; restart writes `unknown_after_restart` | outcome may be missing (request had no effect) |
| Spool chain break at start | instance does not serve | same |
| Identity or role store unreachable | 403 `permission_denied`, outcome recorded | same |
| Upstream timeout | 503 retryable, unknown outcome, retry with same key | 503 retryable |

### 8. Order of work and the live-route gate
No live route is registered until all of these hold: the spool, caps and identity binding are merged with their tests; SEC-008 accepts records through the `AuditStore` port; SEC-024 and GOV-065 are accepted so real roles may be read (ADR-0060 item 15); SEC-009 rate limits sit in front of the binding; QA-016 has passed against the bound gateway; and a security review by a different model has run on the bound gateway. This is the last follow-up row (G3), so no partner row in G2 waits on an Eldon row in G2 (ADR-0025).

## Threats and the test that proves each (proposed test names)
| ID | Threat | Control | Proposed test |
|---|---|---|---|
| GLB-T01 | Process killed after intent, before handler | Intent commit precedes handler | `test_spool_intent_survives_sigkill_before_handler` (subprocess killed, record present on reopen) |
| GLB-T02 | Process killed after effect, before outcome | Restart writes `unknown_after_restart` | `test_restart_closes_orphan_intent_as_unknown` |
| GLB-T03 | Spool full or near full | Admission at 90%, reservation per mutation | `test_spool_high_water_refuses_mutation_without_handler_call` |
| GLB-T04 | Store of record down for hours | Backlog, backoff, no drop | `test_forwarder_outage_backpressure_zero_drops` |
| GLB-T05 | Forwarder crashes between send and ack | Dedupe on `(audit_id, phase)` | `test_forwarder_redelivery_is_idempotent` |
| GLB-T06 | Unforwarded records deleted or edited on disk | HMAC chain verified at start | `test_spool_chain_break_fails_closed` |
| GLB-T07 | Record permanently rejected by the store | Quarantine, counted, paged | `test_poison_record_quarantined_not_dropped` |
| GLB-T08 | Two processes write one spool | Exclusive lock and fencing row | `test_second_spool_writer_refused` |
| GLB-T09 | Wall clock moves backwards | `seq` orders records | `test_clock_backwards_keeps_seq_order` |
| GLB-T10 | Token for tenant X used on host Y | Claim must equal host tenant | `test_cross_tenant_token_denied_and_kept_out_of_tenant_audit` (joins SEC-004) |
| GLB-T11 | Tenant smuggled in header, body, path or query | Tenant only from host and claims | `test_tenant_never_taken_from_request` |
| GLB-T12 | Staff or agent token on a customer route | Realm check, no agent tokens | `test_staff_and_agent_tokens_refused` |
| GLB-T13 | Revoked member keeps access | Session version checked every request | `test_session_version_bump_denies_next_request` |
| GLB-T14 | Role store outage grants stale roles | No cache, deny on failure or empty set | `test_role_lookup_failure_or_empty_denies` |
| GLB-T15 | Caller forges identity fields in the audit | Identity fields only from verified claims | `test_audit_identity_fields_only_from_claims` |
| GLB-T16 | Secrets or bodies leak into audit | Field allow-list | `test_audit_record_contains_no_token_cookie_or_body` |
| GLB-T17 | Oversize body (declared, undeclared, chunked) | Content-Length rule, counting reader, no Transfer-Encoding | `test_request_body_cap_declared_undeclared_and_chunked` |
| GLB-T18 | Header flood or slow client | Header caps, read deadlines | `test_header_caps_and_slow_client_deadline` |
| GLB-T19 | Malformed or huge Idempotency-Key | Exact ULID or UUID grammar | `test_idempotency_key_grammar_before_intent` |
| GLB-T20 | Oversize upstream body or headers | Counting read, connection closed | `test_upstream_body_and_header_caps_abort` |
| GLB-T21 | Deeply nested or huge upstream JSON | Depth and value caps | `test_upstream_json_depth_and_count_caps` |
| GLB-T22 | Mutation times out, client retries | Unknown outcome, adapter dedupe | `test_mutation_timeout_retry_same_key_single_effect` |
| GLB-T23 | Server library reveals itself | No `Server` header, our error bodies | `test_binding_malformed_http_returns_our_error_without_server_header` |
| GLB-T24 | Metrics or health reachable publicly | Internal listener only | `test_health_and_metrics_absent_on_public_listener` |
| GLB-T25 | Outsider floods a tenant's audit | Unauthenticated records go to platform stream | `test_unauthenticated_denials_not_in_tenant_audit` |
| GLB-T26 | Cross-site mutating request with the cookie | `Origin` check, SameSite=Strict, no CORS | `test_cross_origin_mutation_refused_before_intent` |
| GLB-T27 | Undeclared query parameters reach the handler | Query refused unless declared | `test_undeclared_query_refused` |
| GLB-T28 | Handler picks tenant or user from request data | Handler gets claims-derived fields only | `test_handler_receives_only_claims_tenant_and_subject` |
| GLB-T29 | Volume lost with unforwarded backlog | Age alert, replicated volume, adapter second trail | `test_oldest_unforwarded_age_alert_fires` (detection only; the loss itself is the accepted residual) |

## Alternatives rejected
- **Keep the in-memory deque and bind HTTP.** Fails README precondition 1: a crash loses intents and queued outcomes.
- **Write audit synchronously into the tenant database (beside `adapter_audit_log`).** The gateway would need database credentials for every tenant, beyond ADR-0007 item 11's per-site impersonation credential; unauthenticated and cross-tenant attempts have no tenant database; and a tenant database outage would make denials unauditable.
- **Use the control-plane regional database (ADR-0040) or the regional role store (ADR-0060) as the audit store.** Both have their own custody rules (`S22`, ADR-0060 item 6); mixing HTTP audit into them widens who can write there, and picking the audit store of record is SEC-008's decision, not this ADR's.
- **Write-through to the store of record on every request.** Simplest semantics, but every request then fails when the store is briefly unreachable; kept as a possible per-route option later.
- **An edge idempotency store.** Duplicates the adapter's tenant-database store (ADR-0041) and adds a second restore story.
- **Rely on a reverse proxy for caps.** Proxies differ and can be misconfigured; the application must enforce its own caps and treat the proxy as defence in depth.

## Consequences
- Easier: PLT-024's preconditions become concrete, testable rows; the gateway, Tool API and adapter can join on one `audit_id`; crash, outage and restart behaviour is specified per case.
- Harder: each gateway instance needs a persistent, encrypted, in-country volume and a lock discipline; scaling down needs a drain; operators own quarantine and unknown-outcome alerts; the live route waits on four rows in Eldon's lane (SEC-008, SEC-009, SEC-024, GOV-065), all in earlier gates than the go-live row.
- Residual risks: loss of a spool volume loses unforwarded records (2.10); unknown outcomes need a human until the adapter accepts a correlation id; timing side channels are not covered (6.3); all (P) values are untested on real infrastructure (UNVERIFIED).
- Must be done: the follow-up rows below (PLT-028 to PLT-031); questions to Eldon's lane on `session_id` (Q-609), `audit_id` adoption in `tool.called` (Q-610), an adapter correlation id (Q-611), `payload_too_large` (Q-612), the Tool API section 6 idempotency location (Q-613), and the `AuditStore` port shape for SEC-008 (Q-614).

## Follow-up plan rows (added to PLAN as PLT-028 to PLT-031)
1. Gateway durable audit spool replacing the in-memory deque (ADR-0069 sections 2 and 7): SQLite WAL spool, intent before handler, capacity and admission, HMAC chain, single writer, restart recovery with `unknown_after_restart`, forwarder to an `AuditStore` test double with dedupe, backoff and quarantine, internal metrics; tests GLB-T01 to T09 and T29. Platform, G2, depends PLT-027, partner.
2. Gateway HTTP binding skeleton with request and response size caps and time limits (ADR-0069 sections 1, 4 and 6): stdlib WSGI adapter under wsgiref for tests, no live route, internal health listener, no server fingerprint; tests GLB-T17 to T24 and T27. Platform, G2, depends PLT-027, partner.
3. Gateway identity-bound audit and tenant binding (ADR-0069 sections 3 and 5): verify customer tokens through the identity port, host-tenant equality, route permission through the `RoleResolver` port with a fake only, Origin check, claims-derived handler input, platform security stream; tests GLB-T10 to T16, T25, T26 and T28 (GLB-T10 joins SEC-004). Platform, G2, depends PLT-027 and the row 1 ID, partner.
4. Gateway first live route behind the binding (ADR-0069 section 8): connect the `AuditStore` port to SEC-008, real role reads, SEC-009 limits in front, QA-016 crawl on the bound gateway, security review by a different model. Platform, G3, depends rows 1 to 3, SEC-008, SEC-009, SEC-024, GOV-065, QA-016, partner.

## Supersedes
none
