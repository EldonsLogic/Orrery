# Gateway local audit spool: specification before code (PLT-028)

Status: draft, revision 2.1 (Tier 3, security review by a different model before code)
Owner: partner
Plan ID: PLT-028 (G2)
Related: [ADR-0069](../decisions/ADR-0069-gateway-live-binding-audit-spool.md) sections 2.1 to 2.5, 2.10, 2.11, 5.5, 7; founder decisions on PR #316 (2026-11-25); [ADR-0038](../decisions/ADR-0038-secrets-management.md); [ADR-0041](../decisions/ADR-0041-durable-adapter-state-on-tenant-database.md); [ADR-0006](../decisions/ADR-0006-tenancy-site-per-tenant.md); [data-retention.md](../security/data-retention.md) section 8; Q-614

This is the local side of the ADR-0069 spool, built against a fake `AuditStore`: files, tables, transactions, admission, recovery and key rotation in one gateway instance. Forwarding is PLT-032's; this spec fixes only the local interface PLT-032 calls (section 6) and the local comparison rules it applies (4.7). Every choice marked **(P)** is proposed and may change in review without changing the structure.

**Precedence.** The founder decisions on PR #316 (2026-11-25, Eldon for both founders) override ADR-0069 where they differ, because ADR-0069 was merged as Proposed before that re-scope. This spec applies five of them: (D1) SEC-008 owns the record format and the `AuditStore` port; (D2) identity is the per-tenant `memberRef` plus `token_id`, with no global user id; (D3) platform security events go to SEC-008's platform security stream; (D4) ordinary routes are buffered and crash loss is accepted; admin and money routes are write-through; (D5) idempotency lives in the adapter only; the gateway does no dedupe. Eldon's answers on PR #335 (2026-11-26, for both founders) settle the rest: (A1) write-through means a synced commit on this instance's local volume before the action completes, then forwarding to the store of record; (A2) with the store unreachable at start, sign-in and reads keep working, ordinary actions buffer locally, admin and money actions still run, and the instance refuses everything only when its own local volume fails.

Departures from ADR-0069, for its next revision to follow:
| ADR-0069 | It says | Here |
|---|---|---|
| 2.4, 7 | every write intent and every read outcome commits before the handler or response | two route classes (3); only `write_through` routes commit per request; `ordinary` records are buffered (D4) |
| 2.7, 2.10 | the 30 s unconfirmed rule refuses all writes | (P, inferred from A2) it is an alert only and refuses nothing (5.2 step 2) |
| 2.8, 2.9 | per-record receipts, local quarantine and its protocol | receipts are required for `write_through` rows only; an acknowledgement deletes the acknowledged rows whatever their receipt; the store keeps rejected or conflicting bytes (6.3); no quarantine |
| 2.10 | tenant share on writes only; reads up to 100% | share on every class, including the in-memory buffer (5) |
| 2.11, 7 | store unreachable at start: serve reads, refuse writes | serve every class once the local chain verifies; the store comparison and reconcile run when the store is reachable, and nothing is forwarded before they pass (4.4, A2) |
| 2.13 | loss bounded by capacity | adds the buffer: at most 1,024 ordinary records per crash (4.1) |
| 2.14 | subject-bound dedupe key forwarded by the gateway | removed (D5); nothing here deduplicates requests |
| 3.3 | a `Route` declares methods and effect | it also declares `audit_class` (3) |
| 5.1 | the token subject as the user field | `memberRef` and `token_id`; no subject and no global user id (1, D2) |
| 5.4 | platform security stream with no owner | SEC-008's stream (D3); rows listed in 6.8 |
| threats | GLB-T07 (quarantine), T44 and T45 name quarantine | T07 (PLT-032) keeps verbatim store evidence and deletes locally with a page; T44 and T45 renamed (8) |
| 5.5 | five places to probe, including quarantine | `records`, `open_intents`, `preauth`, the late file, preserved failed or corrupt files (7.4) |

## 1. Files, settings, units and MACs
- **(P) Files.** Three per instance on the encrypted in-country volume (ADR-0069 2.1): `spool-tenant.db`, `spool-preauth.db` and `spool-late.db`. The late file is empty unless the tenant file fails closed (4.2, 7.4). Each file has its own WAL, an advisory lock file `<name>.lock` and, once it fails closed, a marker file `<name>.failed` (created exclusively, file and directory fsynced, holding reason and time). None is ever on a network file system.
- **(P) Library and connections.** Standard library `sqlite3` only. Start refuses if `sqlite3.sqlite_version_info < (3, 37, 0)`, which STRICT tables need. One writer connection per file opened with `isolation_level=None`, and one read connection for PLT-032's batch reads.
- **(P) Pragmas on every open,** each read back: `journal_mode=WAL`, `synchronous=FULL`; `fullfsync=ON`, `checkpoint_fullfsync=ON` (no-ops on Linux, they make a macOS developer run durable; production is Linux only); `foreign_keys=ON`, `secure_delete=ON` (M6), `cell_size_check=ON`, `trusted_schema=OFF`; `busy_timeout=5000`, `journal_size_limit=67108864`, `wal_autocheckpoint=1000`.
- **(P) Units.** Capacity is counted in integer units, never in measured bytes: a `records` row costs 1 unit; an `open_intents` row costs 2 units: the intent copy plus the reserved outcome; 1 unit = 4 KiB ceiling × overhead factor 2 = 8 KiB. So `U = 512 MiB / 8 KiB = 65,536` for `tenant` and `U_p = 8,192` (64 MiB) for `preauth`. A physical guard (5.3) backs the logical count.
- **(P) Record bytes.** `body` is the canonical record without `chain`: JSON with sorted keys, separators `,` and `:`, UTF-8, no NaN, at most 4,096 bytes. A larger body is a write failure (503 `audit_unavailable`), never truncated. **Inside `body`:** `instance_id`, `stream`, `seq` (assigned at commit in the transaction that appends the row; `null` in `late` rows, which sit outside the chain and are authenticated by the late-row MAC), `key_id`, `phase`, `audit_id`, `tenant_id` and `audit_class`. **Identity, when verified (F3, D2):** `tenant_id`, `memberRef` (the per-tenant member reference from the membership check), `token_id`, `realm`, `session_version`, `mfa_satisfied`, `auth_time`. The token subject and any global user id are never written. **Provisional:** the field set is ADR-0069 5.1 with that change, and SEC-008 may change the record shapes (D1, D3). Only the indexed columns of section 2 are fixed here, so a shape change touches the record builder, not the schema.
- **(P) Keys.** Each key version `K` from the secret store (ADR-0038) gives two derived keys: `K_chain = HMAC(K, "seshna.spool.chain.v1")` and `K_mac = HMAC(K, "seshna.spool.rowmac.v1")`. Notation: `lp(x) = be32(len(x)) || x`.
- **(P) Chain.** `chain(seq) = HMAC-SHA256(K_chain[key_id], chain(seq-1) || body)`, with `chain(0)` = 32 zero bytes.
- **(P) First key of a fresh file (F9).** Creation is one transaction. It writes `owner` (epoch 1, new `boot_id`) and `checkpoint` (head 0, zero chain, `active_key_id` = the secret store's current version, which must load). Creation is refused if the store already has a checkpoint for this `(instance_id, stream)`: a fresh file under a used `instance_id` is a rollback (4.7, first row). With the store unreachable, creation proceeds and this check is the deferred 4.7 comparison (4.4 step 5), which a fresh file under a used `instance_id` fails; nothing is forwarded before it passes (A2).
- **(P) Open-row MAC.** `HMAC-SHA256(K_mac[key_id], lp("open") || lp(instance_id) || lp(stream) || lp(audit_id) || lp(tenant_id) || be64(seq) || lp(key_id) || be64(reserved_units) || chain || lp(intent_body))`.
- **(P) Late-row MAC.** `HMAC-SHA256(K_mac[key_id], lp("late") || lp(instance_id) || lp(audit_id) || lp(phase) || lp(tenant_id) || lp(key_id) || lp(body))`.
- **Column binding.** Every indexed column (`seq`, `phase`, `audit_id`, `tenant_id`, `key_id`) must equal the same field in its `body` or `intent_body`. TX2 checks the row it closes; recovery step 4 checks every row.

## 2. Schema (`tenant` and `preauth`; `preauth` never has `open_intents` rows)
```sql
CREATE TABLE owner (one INTEGER PRIMARY KEY CHECK (one = 1), instance_id TEXT NOT NULL,
  stream TEXT NOT NULL CHECK (stream IN ('tenant','preauth')), epoch INTEGER NOT NULL CHECK (epoch >= 1),
  boot_id TEXT NOT NULL, schema_version INTEGER NOT NULL) STRICT;
CREATE TABLE checkpoint (one INTEGER PRIMARY KEY CHECK (one = 1),
  head_seq INTEGER NOT NULL CHECK (head_seq >= 0), head_chain BLOB NOT NULL CHECK (length(head_chain) = 32),
  pruned_through INTEGER NOT NULL CHECK (pruned_through BETWEEN 0 AND head_seq),
  pruned_chain BLOB NOT NULL CHECK (length(pruned_chain) = 32),
  prune_receipt_version INTEGER NOT NULL CHECK (prune_receipt_version >= 0),
  active_key_id TEXT NOT NULL) STRICT;
CREATE TABLE records (seq INTEGER PRIMARY KEY CHECK (seq >= 1),
  phase TEXT NOT NULL CHECK (phase IN ('intent','outcome','reconcile','key_rotation','aggregate')),
  audit_id TEXT CHECK (phase NOT IN ('intent','outcome','reconcile') OR audit_id IS NOT NULL),
  tenant_id TEXT NOT NULL, key_id TEXT NOT NULL,
  chain BLOB NOT NULL CHECK (length(chain) = 32),
  body BLOB NOT NULL CHECK (length(body) BETWEEN 2 AND 4096)) STRICT;
CREATE UNIQUE INDEX records_audit_phase ON records(audit_id, phase) WHERE phase IN ('intent','outcome');
CREATE INDEX records_tenant ON records(tenant_id);
CREATE INDEX records_key ON records(key_id);
CREATE INDEX records_agg ON records(tenant_id) WHERE phase = 'aggregate';
CREATE TABLE open_intents (audit_id TEXT PRIMARY KEY, seq INTEGER NOT NULL UNIQUE,
  tenant_id TEXT NOT NULL CHECK (tenant_id <> ''), key_id TEXT NOT NULL,
  chain BLOB NOT NULL CHECK (length(chain) = 32),
  intent_body BLOB NOT NULL CHECK (length(intent_body) BETWEEN 2 AND 4096),
  reserved_units INTEGER NOT NULL CHECK (reserved_units = 1),
  row_mac BLOB NOT NULL CHECK (length(row_mac) = 32)) STRICT;
CREATE INDEX open_intents_key ON open_intents(key_id);
CREATE TABLE usage (tenant_id TEXT PRIMARY KEY, units INTEGER NOT NULL CHECK (units > 0)) STRICT;
-- spool-late.db only:
CREATE TABLE late (audit_id TEXT NOT NULL, phase TEXT NOT NULL CHECK (phase IN ('intent','outcome')),
  tenant_id TEXT NOT NULL, key_id TEXT NOT NULL, body BLOB NOT NULL CHECK (length(body) BETWEEN 2 AND 4096),
  row_mac BLOB NOT NULL CHECK (length(row_mac) = 32), PRIMARY KEY (audit_id, phase)) STRICT;
```
- **`tenant_id` values.** `tenant` file: the verified tenant. `preauth` file: the unverified host tenant, **only if the validated host names a provisioned tenant**; otherwise `''` (F9). Platform rows (`key_rotation`, platform aggregates): `''`.
- **`usage`** caches `count(records) + 2 * count(open_intents)` per tenant, plus a `'*'` row for the file total. A row that reaches 0 is deleted in the same transaction, so `preauth` holds at most (provisioned tenants + 2) rows. Start recomputes and compares it (4.4 step 4).
- No foreign key from `open_intents` to `records`: the intent row is pruned after delivery while the open row stays (ADR-0069 2.4).

## 3. Route classes and transactions
**Route class (F1).** Each `Route` declares `audit_class` in the route table: `ordinary` or `write_through`. An unclassified route is `write_through` (fail closed). Registration refuses `ordinary` for three kinds of route: a route whose permission is admin-kind (ADR-0069 3.6); a route whose permission the catalogue marks as money (Q-647); until Q-647 is answered, every `write` route (P). So for now only `read` routes can be `ordinary`.

**`ordinary` routes (D4).** Records go to an in-memory buffer: the intent before an ordinary write's handler, and the outcome after every request. A flusher commits the buffer in batches (TX9). The response does not wait for the flush, and a crash loses whatever was not flushed.

**`write_through` routes (A1).** The intent record is committed in this file under `synchronous=FULL` before the action's effect (TX1, before the handler), and the outcome record before the response (TX2 for writes, TX3 for reads). PLT-032 then forwards both to the store of record. No store round trip is in the request path, so a store outage never blocks a `write_through` route (A2). Open rows (4.2), required receipts (6.3) and reconcile (4.4 step 7) apply to these routes only.

**Denials and validation failures** before any handler have no effect, so they are buffered on every route (P).

**Transaction rules.** Every write runs under the writer lock (5.4) as `BEGIN IMMEDIATE` ... `COMMIT`. Its first statement reads `owner.epoch`, and a mismatch stops the writer. Any exception before `COMMIT` is followed by an explicit `ROLLBACK`.

**An I/O error raised by `COMMIT` itself (F7)** fails the file closed at once: the connection is closed and no further transaction runs on it. Then TX1 never calls the handler and the client gets 503; TX3 answers 503 with no data (a read has no effect; the same holds when TX3 meets a `failed_closed` file or a full disk); TX2 takes the 4.2 late path; TX9 sends its batch to the late file; any other transaction is named in the page. The earlier rule (reopen, then read the durability point) is deferred and UNVERIFIED (10). A later revision may enable it only after its own test passes on the production volume type (GLB-T76).

| Id | Name | Statements inside one `BEGIN IMMEDIATE` | DP |
|---|---|---|---|
| TX0 | start | `UPDATE owner SET epoch = epoch + 1, boot_id = ?` | DP0 |
| TX1 | write-through intent | admission W (5.1); `INSERT records` (intent); `INSERT open_intents`; `UPDATE checkpoint` head; `usage` tenant and `'*'` +3 | DP1 |
| TX2 | write-through write outcome | `SELECT open_intents` by `audit_id` (absent: 4.2); verify `row_mac` and binding; refuse an outcome with `status` null or `reason` `unknown_after_restart`; `INSERT records`; `DELETE open_intents`; head; usage -1 | DP2 |
| TX3 | write-through read outcome | admission R; `INSERT records`; head; usage +1 | DP3 |
| TX4 | aggregate | admission G; `INSERT records` (`aggregate`); head; usage +1 | DP4 |
| TX5 | apply acknowledgement (PLT-032) | checks of 6.3; `DELETE records` through `through_seq`; `UPDATE checkpoint` pruned fields; usage per tenant | DP5 |
| TX6 | recovery close | open row as in TX2; `INSERT records`: `phase = 'outcome'`, `key_id = active_key_id`, `ts` = now, identity (1) and route fields copied from `intent_body`, `status`, `error_code`, `latency_ms`, `upstream_correlation` null, `reason = "unknown_after_restart"`; `DELETE open_intents`; head; usage -1 | DP6 |
| TX7 | key rotation (each file) | admission K; `INSERT records` (`key_rotation`, `tenant_id = ''`, under the old key, naming the new `key_id`); `UPDATE checkpoint SET active_key_id = new`; head; usage `''` and `'*'` +1 | DP7 |
| TX8 | removed in revision 2 (quarantine destroy; no quarantine exists) | | |
| TX9 | buffer flush | at most 256 buffered records in arrival order; `INSERT records` each; head; usage per tenant (units move from buffered to usage) | DP9 |
| TX10 | late append (`spool-late.db`) | `INSERT late` with `row_mac` under the tenant file's `active_key_id` | DP10 |

**WAL truncation after a drain (M6).** Hold `stream_guard` (6.1), which pauses PLT-032, close the read connection, and run `PRAGMA wal_checkpoint(TRUNCATE)`. The result must be `(busy = 0, log = 0)`; otherwise retry up to 10 times at 1 s, then page. Deprovisioning certification refuses without this result (UNVERIFIED: 10).

## 4. State machines
### 4.1 A record
| State | Event | Guard | Action | Next |
|---|---|---|---|---|
| none | ordinary record | file `serving`, not `failed_closed`; admission R at enqueue (5.2); buffer < 1,024 records | append to the in-memory buffer | buffered |
| none | same | any guard fails | 503 `audit_unavailable` (429 on `preauth`); counter (5.2 step 5) | none |
| buffered | flusher: every 200 ms, or 256 records waiting | none | TX9 | unforwarded |
| buffered | TX9 fails without an I/O error on `COMMIT` (full, busy) | none | keep in arrival order; retry with backoff 0.1 s to 5 s; a full buffer refuses new records; never dropped | buffered |
| buffered | I/O error on `COMMIT`, or the file goes `failed_closed` | none | `tenant`: TX10 for every buffered record; `preauth`: fold the buffered rows into the per-reason counters of 4.6 (`preauth_unrecorded`), no action ran; page | late or counted |
| buffered | graceful shutdown | none | flush for at most 30 s (P), then TX10 for the rest | unforwarded or late |
| buffered | crash | none | lost (D4); bound: the buffer, at most 1,024 records, normally under 200 ms of traffic | lost |
| none | TX1, TX2, TX3, TX4, TX6, TX7 | file `serving` (TX6: recovery step 6); body ≤ 4,096; admission | append, `seq = head_seq + 1`, chained under `active_key_id` | unforwarded |
| unforwarded | TX5 | 6.3 | delete whatever the receipt; `rejected` or `conflict` is counted and pages; the store keeps the verbatim bytes (ADR-0069 2.8; semantics are SEC-008's) | pruned |
| unforwarded | tenant deprovisioned | none | never deleted out of order; deprovisioning waits for drain (ADR-0069 5.5) | unforwarded |
| late | drain (7.4) | `row_mac` verifies | forwarded, then deleted after acknowledgement | gone |

### 4.2 An `open_intents` row (`write_through` writes only)
| State | Event | Guard | Action | Next |
|---|---|---|---|---|
| none | write request | class `write_through`; 5.2 checks inside the transaction | TX1, then call the handler | open |
| none | same | any guard fails, or TX1 fails | 503 `audit_unavailable`; handler never called | none |
| open | handler returns or raises | row present; `row_mac` and binding valid | TX2 | closed |
| open | TX2 fails without an I/O error on `COMMIT` (full, busy) | effect possible | return the real result; retry in memory, 0.1 s to 5 s; row and reservation stay | open (retrying) |
| open | **F4:** the file is or becomes `failed_closed` before or during TX2; TX2 gets an I/O error on `COMMIT`; the row is absent; or its `row_mac` or binding fails | none | the file goes `failed_closed` if it is not already; return the real result to the client; TX10 writes the real outcome (`status`, `reason`, `latency_ms`) to the late file; page | open, with a late outcome |
| open, with a late outcome | TX10 also fails | none | the outcome stays in memory, TX10 is retried every 5 s, and the outcome is sent directly if Q-646 allows. If the process exits first, only the result fields are lost: the open row survives in the preserved file and the drain reports it as unknown (residual, 9) | open |
| open | process dies | none | none | open, found by recovery |
| open | recovery step 6 | `row_mac` and binding valid, key present, no local outcome | TX6 | closed |
| open | recovery step 4 | `row_mac` or binding invalid, key missing, or an outcome already exists | leave the row; `failed_closed`; page (GLB-T46) | open (unverifiable) |
| open | forwarder, TX5, key retirement | any | never touched; retirement waits (4.5) | open |

### 4.3 Reservations
| Holder | Taken | Released | Rule |
|---|---|---|---|
| open row | TX1: +2 units in `usage` | TX2 or TX6: net -1 | survives restart; every limit counts it in `'*'`; every floor keeps `8 KiB × held` free (5.3) |
| ordinary write's outcome | enqueue of its intent: +1 in `buffered[tenant]` | when its outcome is enqueued | in memory only; a crash loses both (D4); the outcome is never refused (5.1 O) |

### 4.4 Restart recovery (R3-1), per file
When the store answers at start, steps run 1 to 7 and the file serves after step 7, so nothing is appended before the comparison. When it does not (one attempt, 2 s timeout (P)), they run 1, 2, 3, 4, 6, the file serves, and steps 5 and 7 run when the store is first reachable (A2).
| Step | State | Check | On success | On failure |
|---|---|---|---|---|
| 1 | starting | `flock` (exclusive, non-blocking) on `<name>.lock` | 2 | refuse to serve; exit non-zero (GLB-T08) |
| 2 | locked | no `<name>.failed` marker; open; read pragmas back; `PRAGMA quick_check`; schema version; for `spool-tenant.db` only (the late file holds `tenant` rows only), `spool-late.db` empty | 3 | `corrupt` (7.3); a marker or a non-empty late file means the last run failed closed: `failed_closed` (7.4) |
| 3 | open | TX0 | 4 | `corrupt` |
| 4 | fenced | every `key_id` and `checkpoint.active_key_id` loads; chain verifies from `(pruned_through, pruned_chain)` to `(head_seq, head_chain)`; column binding of every row; every `row_mac`; `usage` equals its recomputation | 5; 6 if the store does not answer | `failed_closed`, not ready, page; a `usage` mismatch alone: rewrite it and page |
| 5 | verified locally, or `waiting_store` | when the store answers (retry every 5 s; alert after 60 s, page after 300 s (P)): under `stream_guard`, compare the store checkpoint with `local_snapshot` under 4.7. Rows appended since start lie above every point the store knows and the 4.7 rules cover them | 6, or 7 when deferred | mismatch: `failed_closed` (7.4), not ready, page; the forwarder never starts, and the 7.4 drain hands the rows above the store's watermark to SEC-008 as flagged evidence |
| 6 | close | for each open row in `seq` order: TX6, one transaction per row | keep `h0 = head_seq`; 7 if step 5 passed, else `serving`, `writes_ready`, `waiting_store`, ready | TX6 fails: stop at that row, `failed_closed`, page (GLB-T83) |
| 7 | reconcile | `O = list_open_intents(instance)` filtered to `audit_class = write_through`, read under `stream_guard` on the read connection while the forwarder is stopped; the writer lock is never held across a store call, and with `h0` fixed and nothing pruned the rows it checks cannot change. Required set `Q = O ∪ {audit_id of every write_through intent in records with seq ≤ h0}`. Each member is satisfied by an `outcome` in `records` (chain verified in step 4), else it is missing. Intents above `h0` were admitted after start and may be in flight; they are not required. An `ordinary` intent without an outcome is expected after a crash (D4) and is not required | `serving`, `writes_ready`, ready (deferred: leave `waiting_store`); start the forwarder | any missing: `serving` with `writes_ready` cleared (`write_through` refused), page with the list, start the forwarder; store unreachable: `serving`, `writes_ready`, `waiting_store`, retry step 7 |

**While `waiting_store` (A2).** The file serves every class: sign-in and reads, `ordinary` records buffered and flushed by TX9, `write_through` records committed by TX1 to TX3. Nothing is forwarded, acknowledged or pruned, so step 5 still has every row it compares. Appends only extend a chain that passed step 4, and nothing reaches the store before step 5 passes. The only refusals are local: a `tenant` file that is `failed_closed` or `corrupt` makes the instance not ready, refusing everything; the 5.1 limits still apply, so a long outage that fills the file refuses W at 90% and R at `U - B` (tenant capacity is the one refusal an outage can cause); sign-in is never refused for `preauth` capacity during an outage (4.6).

Why this closes R3-1: step 6 first turns every surviving open row into a local outcome. Step 7 then needs one rule: a required intent is satisfied by a verified local outcome, either the original (committed locally, not yet forwarded) or the rebuilt one. Invariant (tested): after step 6, `open_intents` is empty or the file is `failed_closed`; rows added later have `seq > h0`.

### 4.5 MAC and chain key rotation (R3-4)
`deps(k)` = the rows with `key_id = k` in `records`, `open_intents` and `late`, plus 1 if `checkpoint.active_key_id = k`, summed over every file of a spool directory.
| Key state | Event | Guard | Action | Next |
|---|---|---|---|---|
| active | rotation with a new `key_id` | new key loads; both files `serving` | TX7 on `tenant`, then TX7 on `preauth` | verify_only |
| active | TX7 fails on one file (partial rotation) | none | `ROLLBACK`; that file keeps the old key; alert; retry. Each file chains under its own `active_key_id` | active on that file |
| verify_only | rows depend on it | `deps(k) > 0` | keep it loaded; export `spool_rows_by_key{key_id}` | verify_only |
| verify_only | `deps(k) = 0` on this instance | none | report `retirable` | retirable |
| retirable | key administrator requests retirement (ADR-0038 item 5) | **active inventory probe** returns `deps(k) = 0` for every spool directory on every attached and detached volume (INF-001 inventory) and every preserved failed or corrupt file. Attached: live `key_dependents(k)`. Detached or preserved: the probe takes the `flock`, opens and counts | retire the version; instances unload it | retired |
| retirable | same | a volume unreachable, a file failing `quick_check`, an instance not answering, or any `deps > 0` | refuse; alert | retirable |
| any | start finds a row or checkpoint whose `key_id` cannot load | none | `failed_closed`; the row is never deleted or re-MACed | failed_closed |

(P) Keep the key rather than re-authenticate the rows: unforwarded `records` under the old key need it until they are pruned anyway. Rotation never waits on `deps`; only retirement does.

### 4.6 The `preauth` spool
Every `preauth` record is `ordinary`, buffered and flushed by TX9. That covers unverified denials, tokens for another tenant, and listener events (ADR-0069 1.5, 3.2). They follow 4.1 under the `preauth` limits of 5.1. Over a limit, or with the file not `serving`, the request gets 429 `rate_limited` and an in-memory counter per reason goes up. **(P) Sign-in during a store outage (A2):** while the `tenant` file is `waiting_store` or no report has been confirmed for 30 s, a sign-in request that the `preauth` limit would refuse is served, and its record is folded into the per-reason counters (`preauth_unrecorded`) instead; other unverified requests still get 429. So sign-in never gets 429 because the store is down; only a failed `preauth` file refuses it. Every 60 s, TX4 writes one aggregate of every reason's counts and the window. If that aggregate is refused, or the `preauth` file fails closed (its buffer is folded into the counters, 4.1), counting continues (`preauth_unrecorded` metric) and the counts go to the platform stream as a state event; the late file holds `tenant` rows only. Verified requests never call `preauth` admission. There are no `open_intents` and no tenant share.

### 4.7 Snapshot comparison (local half of ADR-0069 2.7; used in step 5 here and by PLT-032 before each acknowledgement)
`L` = `local_snapshot` (6.2), `S` = the store checkpoint for `(instance, stream)`. Step 4 has already verified the local chain between L's anchor and head, so equality at single points is enough. Every row is a test (GLB-T70); any failure is a mismatch.
| Case | Check |
|---|---|
| `S` absent (never confirmed) | `L.pruned_through = 0` and `L.pruned_chain` = zero bytes |
| `L.pruned_through > S.wm_seq` | always a mismatch (impossible by the prune rule) |
| `L.pruned_through = S.wm_seq` | `L.pruned_chain = S.wm_chain`, **even when no row lies between anchor and head** |
| `L.pruned_through < S.wm_seq` | a row at `S.wm_seq` exists and its chain = `S.wm_chain` |
| `S.head_seq > L.head_seq` | always a mismatch (truncated suffix or older file) |
| `L.pruned_through < S.head_seq ≤ L.head_seq` | the chain at `S.head_seq` = `S.head_chain` |
| `S.head_seq = L.pruned_through` | `L.pruned_chain = S.head_chain` |

## 5. Admission (R3-5)
### 5.1 Limits (P)
- **`tenant`:** `U = 65,536`; share `S = 0.20 U = 13,107`; band `B = 0.01 U = 655`; platform slot `P = 16`; per-tenant aggregate cap `A = 8`. **`preauth`:** `U_p = 8,192`; band 256; `P = 16`; aggregate cap 64. **`buffered[t]`** = tenant t's unflushed records plus its reserved ordinary outcomes, in memory.

| Path | Cost | File-total limit | Per-tenant limit | Other guards |
|---|---|---|---|---|
| W: write-through intent (TX1) | 3 | total + buffered + 3 ≤ `0.90 U` = 58,982 | tenant + `buffered[t]` + 3 ≤ S | `writes_ready` (cleared only by 4.4 step 7); at most 8 write-through requests in flight for the tenant (5.4); floor `M_hi` |
| R: ordinary record at enqueue (an ordinary write's intent costs 2, its outcome included; a read or denial outcome costs 1); write-through read outcome (TX3) | 1 or 2 | total + buffered + cost ≤ `U - B` = 64,881 (`preauth`: 7,936) | tenant + `buffered[t]` + cost ≤ S (`preauth`: none) | buffer < 1,024 records; for TX3, the in-flight cap (5.4); floor `M_hi` at TX9 or TX3 |
| G: tenant or platform aggregate (TX4) | 1 | total + 1 ≤ `U - P` = 65,520 (`preauth`: 8,176) | that tenant's (or the platform's) unforwarded aggregates < `A` (`preauth`: < 64) | floor `M_lo` |
| K: key rotation (TX7) | 1 | total + 1 ≤ U | none | floor `M_lo` |
| O: write-through outcome (TX2), recovery close (TX6), ordinary write outcome | -1 net, or already reserved | none | none | never refused by admission |

The band holds `B - P = 639` units for tenant aggregates: at `A = 8` each, that is 79 tenants with full backlogs, and beyond that counters accumulate in memory. The last `P` units serve key rotation only, so no aggregate can block TX7. **Worked example:** tenant A holds 13,100 units of read outcomes, buffered or unforwarded. A's eighth further read is refused at enqueue (13,108 > S), and so are A's writes. Tenant B's write-through intent passes while total + buffered + 3 ≤ 58,982. Refusing every other tenant's writes takes at least 4.5 tenants at full share.

### 5.2 Algorithm
1. **Lock.** A write-through path takes the writer lock, runs `BEGIN IMMEDIATE` and checks the epoch. An ordinary enqueue takes the buffer mutex instead. Either path then reads the in-memory flags (`serving`, `failed_closed`, `writes_ready`, `waiting_store`, `last_confirmed`), `buffered` and the cached physical reading (5.3). The flags change only while both the writer lock and the buffer mutex are held; `buffered` changes only under the buffer mutex; W takes the buffer mutex inside the writer lock for steps 2 to 4, so every path reads a consistent state.
2. **State checks.** Refuse if the file is not `serving` or is `failed_closed`. For W, also refuse if not `writes_ready`. **(P, inferred from A2) The 30 s rule is an alert, not an admission check:** no confirmed report for 30 s raises `spool_unconfirmed` and pages after 300 s (P); it refuses nothing, at start or later. Then apply the path's floor (5.3).
3. **Limits.** Read `usage` (and `count(records_agg)` for G) and apply the path's 5.1 row. On any refusal: `ROLLBACK` (W); answer 503 `audit_unavailable` (429 on `preauth`), and call no handler; add 1 to the in-memory counter `(tenant, path, reason)`.
4. **Admit.** Otherwise insert and `COMMIT` (W), or enqueue and add to `buffered` (R).
5. **Aggregates.** Every 60 s, for each tenant with a non-zero counter, TX4 writes one `aggregate` record: counts per path and reason, window start and end, at most 4,096 bytes. If it is refused, counting continues and the window grows.

A refused request ran no handler and is not an admitted record. So `audit_drop_count`, which must stay 0, counts only admitted records lost outside a crash. A crash loses unwritten counts (residual, 9).

### 5.3 Physical guard (P)
Refreshed at most once per second under the writer lock. `H` = held open-row reservations. **Per file:** `size(db) + size(wal) + 8 KiB × H_file ≤ cap`, with a cap of 512 MiB for `tenant` and 64 MiB for `preauth`, and `H_preauth = 0`. The late file is bounded by 7.4. **Per volume:** `statvfs` free bytes ≥ `8 KiB × H + M`: `M_hi = 64 MiB` for W and R; `M_lo = 16 MiB` for G and K; no floor for O or TX10. The unit count stays the admission authority; this guard only catches a wrong overhead factor.

### 5.4 Writer lock and fsync queue (F8)
One tenant's reads never take the fsync queue per request: they join the shared TX9 batches (one fsync per batch), and the share S bounds them in units. (P) The writer lock is one FIFO queue for TX9 batches, TX1 to TX4, TX6, TX7 and PLT-032's TX5: **Batch hold.** TX9 holds the lock for one batch of at most 256 records, so a write-through commit waits at most one batch. **Per-tenant cap.** A tenant may have at most 8 write-through requests in flight, counted from admission (TX1 for a write, request start for a read) until the outcome commits (TX2, TX3 or TX10). A ninth is refused at admission with 503 `audit_unavailable` for that tenant only, recorded by 5.2 step 5; an outcome is never refused, so the cap bounds that tenant's per-request fsyncs to 8 at a time. **Reads off the lock.** PLT-032's batch reads and the read-only accessors use the read connection, never the writer lock.

## 6. Interface for PLT-032 (local side only; PLT-032 owns the protocol)
6.1 `stream_guard(stream)`: a mutex per stream. PLT-032 holds it across one store checkpoint read, `local_snapshot` and the 4.7 comparison. `apply_ack` and WAL truncation take it too (local half of R3-2).
6.2 `local_snapshot(stream)`, in one read transaction: `pruned_through`, `pruned_chain`, `prune_receipt_version`, `head_seq`, `head_chain`, and `chain_at(seq)` for `seq` in `(pruned_through, head_seq]`.
6.3 `apply_ack(stream, through_seq, wm_seq, receipt_version, receipts)` runs TX5. It is refused, with nothing written, unless: `through_seq ≤ wm_seq`; `receipt_version ≥ prune_receipt_version`; every `seq` in `(pruned_through, through_seq]` exists; every `write_through` row in that range has exactly one receipt (A1: receipts only where needed). Every other row needs a receipt only if it is `rejected` or in `conflict`; without one it counts as `committed`. Receipts at or below `pruned_through` are ignored, so a replay after a lost reply is a local no-op (R3-3 local half). `rejected` and `conflict` delete the row as `committed` does, increment `receipt_rejected_total` and page. What the store keeps is SEC-008's choice.
6.4 `read_batch(stream, after_seq, max_records = 500, max_bytes = 1 MiB)`: one short read transaction; rows in `seq` order.
6.5 `report_confirmed(stream, monotonic_time)` and `fail_closed(stream, reason)` are set under the writer lock and the buffer mutex. Confirmation is in memory only: after a restart nothing counts as confirmed until PLT-032 reports. It drives the 30 s alert (5.2) and the sign-in exception (4.6), never admission. `fail_closed` also writes the `<name>.failed` marker (1) before it returns; if the marker cannot be written, the instance stays not ready, retries every 5 s and pages, and a restart before it succeeds re-verifies the file under 4.4 step 4 (residual, 9).
6.6 Read-only accessors: units and `buffered` per tenant, held reservations, `key_dependents(key_id)`, the oldest unforwarded `ts`, refusal counters, late rows.
6.7 The fake `AuditStore` implements `checkpoint(instance, stream)` and `list_open_intents(instance)`, filterable by `audit_class`. A direct late outcome exists only if Q-646 allows it.
6.8 **Stream routing (D3).** These go to SEC-008's platform security stream and never to a tenant's audit: every `preauth` row; `tenant` rows with `tenant_id = ''`: `key_rotation` and platform aggregates; the state events `failed_closed`, `corrupt` and `waiting_store`, rejected receipts, the missing intents of 4.4 step 7, and the fact (not the content) that a file has late rows. Only rows with a verified `tenant_id` go to the tenant audit, late rows included, flagged as late. SEC-008 may change these shapes and this routing (D1, D3).

## 7. Failure semantics
### 7.1 Crash (SIGKILL) at each durability point
| Point | Crash before `COMMIT` returns | Crash after `COMMIT`, before the next step |
|---|---|---|
| DP0 | the kernel releases the lock; next start repeats | same |
| DP1 | no intent, no open row; handler not called; dropped connection | open row survives; recovery closes it `unknown_after_restart` (GLB-T01) |
| DP2 | open row survives; recovery closes it (GLB-T02) | outcome unforwarded; step 7 finds it (R3-1) |
| DP3 | no record; dropped connection; no effect | record kept; the response may be lost |
| DP4 | counts lost (residual) | record kept |
| DP5 | nothing pruned; the store returns the original receipts | pruned; open rows untouched (GLB-T30) |
| DP6 | that row stays open; the next start closes it, never twice (GLB-T31) | closed; recovery moves to the next row |
| DP7 | the old key stays active on that file | new key active; old key `verify_only` |
| DP9 | the batch and the rest of the buffer are lost (D4; at most 1,024 records) | batch kept; the rest of the buffer is lost |
| DP10 | the late outcome is lost; the open row survives and the drain reports it as unknown | late row kept; the drain forwards it |

### 7.2 Disk full (`SQLITE_FULL`, or the 5.3 guard)
TX1 and TX3: `ROLLBACK`, 503, handler not called. TX2: real result returned, outcome retried, row and reservation kept. TX9: the batch stays buffered and enqueue is refused once the buffer is full; nothing is dropped. TX5 frees space. TX6 at start: stop at the failing row, `failed_closed`. Graceful shutdown flushes the buffer and retries queued TX2s for at most 30 s (P), then leaves the rest to TX10 or recovery. INF-001 sizes the volume so that `(U + U_p) × 8 KiB + 64 MiB` fits.

### 7.3 Corrupt file
A file is `corrupt` when SQLite reports `SQLITE_CORRUPT` or `SQLITE_NOTADB`, or when `quick_check` is not `ok`. It is then not ready, and a page goes out. It is never repaired, rebuilt or deleted in place; it is preserved for forensic reading, the deprovisioning probe and the key probe (4.5). (P) The instance is replaced with a **new `instance_id`** and a fresh spool, so no `seq` stream ever restarts (Q-633).

### 7.4 Leaving `failed_closed` (F5)
A file becomes `failed_closed` on any of these: a `<name>.failed` marker at start; a failed chain, binding, `row_mac` or key check; a 4.7 mismatch; a missing open row; an I/O error on `COMMIT`; a non-empty late file at start. The state is terminal for the file's instance. The instance reports not ready, still returns real results for requests already past their handler (4.2), and is replaced with a new `instance_id` (as in 7.3). (P) The exit has four steps:
1. **Preserve.** The file and `spool-late.db` stay read-only on the volume, which stays in the INF-001 inventory.
2. **Drain.** An audited, forwarder-only process takes the `flock` and appends nothing. It verifies the chain from the anchor; delivers `records` up to the last verifiable `seq`; delivers the late rows whose `row_mac` verifies; reports each open row with no late outcome as unknown (`unknown_after_failed_closed`; Q-633 decides how the store marks it); hands unverifiable rows to SEC-008 as flagged evidence, or keeps them for forensics. After a 4.7 mismatch (4.4 step 5), "verifiable" ends at the store's watermark: every row above it, including rows appended during an outage, goes to SEC-008 only as flagged evidence.
3. **Destroy.** After the drain and any forensic hold, destroy the files under the deprovisioning or forensic approvals; the deprovisioning probe (ADR-0069 5.5) must then find none of them.
4. **Release keys.** The files count in `deps(k)` until they are destroyed; their key versions then retire through the 4.5 probe. The late file holds at most 1,024 + 256 rows per failure: the whole buffer plus one outcome per in-flight request (256 per instance, ADR-0069 4).

## 8. Tests
Stdlib `unittest`. Crash tests kill a subprocess with SIGKILL at a named hook; the hooks are refused in production, as in ADR-0041. A full disk is simulated with `PRAGMA max_page_count`.
| Test id | Test | Covers |
|---|---|---|
| GLB-T01, T02 | `test_spool_intent_survives_sigkill_before_handler`; `test_restart_closes_open_intent_as_unknown` | 4.2; DP1, DP2 |
| GLB-T03, T08 | `test_high_water_refuses_write_without_handler_call`; `test_second_spool_writer_refused` (an epoch mismatch stops the old writer) | 5.1 W; 4.4 step 1; TX0 |
| GLB-T09, T50 | `test_clock_backwards_keeps_seq_order`; `test_record_over_ceiling_is_write_failure_not_truncated` | 4.1; 1 |
| GLB-T30, T31 | `test_pruned_intent_recovered_with_identity_fields_from_open_row`; `test_crash_during_recovery_resumes_without_double_close` | 4.2; DP5; 4.4 step 6; DP6 |
| GLB-T35 | `test_verified_requests_complete_during_sustained_preauth_saturation` | 4.6 |
| GLB-T44 | `test_deprovision_probe_covers_open_rows_late_file_and_preserved_volumes` | ADR-0069 5.5; 7.4 |
| GLB-T45 | `test_tenant_over_share_does_not_block_other_tenant` (buffer included) | 5.1 |
| GLB-T46 | `test_missing_or_bad_mac_open_row_detected_at_recovery` | 4.2; 4.4 step 7 |
| GLB-T51, T52 | `test_apply_ack_contiguity_rejected_receipt_deletes_pages_and_replay_no_op`; `test_prune_never_exceeds_watermark_or_touches_open_intents` | 6.3; 4.2 |
| GLB-T53 | `test_outcome_commit_failure_returns_real_result_and_keeps_row` | 4.2; 7.2 |
| GLB-T54 to T56 | the tenant share applies to buffered reads and denials (R3-5); late and recovery outcomes are never refused at full capacity; refusals become bounded aggregates per tenant | 5.1; 4.3; 5.2 step 5 |
| GLB-T57, T58 | `test_store_open_intent_satisfied_by_unforwarded_local_outcome` (R3-1); `test_usage_counters_recomputed_and_checked_at_start` | 4.4 step 7; 4.4 step 4 |
| GLB-T59 to T61 | the rotation record is under the old key; a key is not retirable while deps > 0; a missing key fails closed without deleting rows (R3-4) | 4.5 |
| GLB-T62, T63 | `test_preauth_full_returns_429_and_writes_aggregate_in_band`; `test_disk_full_refuses_intent_retries_outcome_and_keeps_buffer` | 4.6; 7.2 |
| GLB-T64, T65 | a corrupt file is not ready and is preserved; local chain or column binding tampering is detected at start | 7.3; 4.4 step 4 |
| GLB-T66 | `test_sigkill_at_each_durability_point` (DP0 to DP10 except DP8, both sides of `COMMIT`) | 7.1 |
| GLB-T67, T68 | `test_snapshot_and_ack_serialised_per_stream` (R3-2 local half); `test_secure_delete_and_wal_truncate_leave_no_closed_tenant_bytes_in_files` (M6) | 6.1; 3; 9 |
| GLB-T69 | removed in revision 2 (it tested quarantine) | |
| GLB-T70 | `test_snapshot_comparison_each_case` (all seven 4.7 rows, each passing and failing) | 4.7 |
| GLB-T71 | `test_store_unreachable_at_start_serves_signin_reads_ordinary_and_write_through` (A2): with the fake store down at start and the local chain valid, the instance is ready; sign-in and reads are served; ordinary records are buffered and flushed locally; admin and money writes commit TX1 and TX2 locally before the handler and response; nothing is forwarded; when the store returns, steps 5 and 7 pass and forwarding starts | 4.4; 3 |
| GLB-T72 to T75 | open-row `audit_id` or tenant swap detected; aggregate band, per-tenant cap, rotation slot and floors; a fail-closed flag set concurrently blocks the next admission; the retirement probe fails closed on an unreachable or corrupt volume | 1; 5.1 to 5.3; 4.5 |
| GLB-T76, T77 | `test_commit_io_error_fails_closed_writes_marker_handler_not_called` (F7; the deferred reopen rule gets its own test before it is enabled); `test_close_write_refuses_recovery_outcome_and_recovery_outcome_fields` | 3; 6.5; TX2; TX6 |
| GLB-T78 | **Power-loss gate (F6):** `test_power_cut_keeps_every_acknowledged_write_through_commit`. A VM on the production volume type is hard-reset by the hypervisor during sustained TX1 and TX2; after reboot, every acknowledged commit must be present. A negative control run with `synchronous=OFF` must lose commits, or the harness is invalid. No `write_through` route goes live until this passes on the production volume type. The SIGKILL tests cannot stand in for it: they also pass with `synchronous=OFF` | 1; 3 |
| GLB-T79, T80 | pragmas read back (including `synchronous=FULL` and `fullfsync`); a fresh file's first key, and creation refused when the store has a checkpoint (F9); with the store down, creation proceeds and the deferred comparison fails a fresh file under a used `instance_id` | 1; 4.4 step 5 |
| GLB-T81, T82 | `test_thirty_second_unconfirmed_rule_alerts_and_refuses_nothing` (F10, A2: no report for 30 s raises the alert; sign-in, reads, ordinary and write-through requests are all still admitted); `test_route_class_declared_default_write_through_and_ordinary_refused_for_admin_money_write` (F1) | 5.1 W; 5.2; 3 |
| GLB-T83, T84 | a recovery close failure stops at its row and fails closed; a partial rotation leaves each file chaining under its own key while retirement waits (F10) | 4.4 step 6; 4.5 |
| GLB-T85, T88 | `test_buffer_flush_failure_retries_never_drops_and_shutdown_flushes`; `test_one_tenant_write_through_cap_and_flush_batch_bound_lock_wait` (F8) | 4.1; 5.4 |
| GLB-T86, T87 | failed closed mid-request returns the real result and writes a late outcome (F4); the failed-closed drain delivers verified rows, reports unknowns and releases keys (F5) | 4.2; TX10; 7.4 |
| GLB-T89, T90 | `preauth` usage rows bounded by provisioned tenants (F9); record identity carries `memberRef` and `token_id` and no subject (F3) | 2; 1 |
| GLB-T91 | `test_signin_never_429_while_store_down` (A2): with the store down and `preauth` at its limit, sign-in is served and counted; another unverified request gets 429; with the store up and `preauth` failed closed, sign-in gets 429 | 4.6 |
| GLB-T92 | `test_local_volume_failure_refuses_everything` (A2): a `tenant` file that is `failed_closed` or `corrupt`, with the store up or down, makes the instance not ready; every new request (sign-in, read, ordinary, write-through) is refused and no handler runs | 4.4; 7.3; 7.4 |
| GLB-T93 | `test_deferred_comparison_mismatch_fails_closed_and_forwards_nothing`: a rolled-back copy of the file passes step 4 and serves during the outage; when the store returns, step 5 fails, the file fails closed, the forwarder never starts and the drain flags every row above the watermark. A file that fails step 4 never serves, store up or down | 4.4 steps 4 and 5; 7.4 |
| GLB-T94 | `test_deferred_reconcile_ignores_in_flight_intents_above_h0`: write-through requests in flight when the store returns are not reported missing; a store-open intent at or below `h0` with no local outcome clears `writes_ready` and pages | 4.4 step 7 |
| GLB-T95 | `test_apply_ack_requires_receipts_for_write_through_rows_only` (A1) | 6.3 |

Also a measurement, not a pass or fail test: `bench_commit_rate_synchronous_full`, which measures TX1 and TX9 rates on the test machine and later on the production volume.

## 9. Open items, residuals and review findings
- **R3-1 (closed, subject to Q-630).** Closed by 4.4 steps 6 and 7 (GLB-T57, T31, T46). It needs `list_open_intents` to be complete at one checkpoint version and filterable by `audit_class`.
- **R3-4 (closed).** A key is kept while `deps > 0` and retired only after an active probe (4.5; GLB-T59 to T61, T75, T84).
- **R3-5 (closed).** The tenant share applies to W, R and the buffer; aggregates are capped inside a band; held reservations count in every limit (5; GLB-T54 to T56, T45, T73).
- **R3-2 and R3-3 (local half here).** 6.1 serialises snapshot and acknowledgement, and 6.3 makes a replay a no-op. The protocol itself is PLT-032's and SEC-008's.
- **M6 (P): a stated exception with conditions, pending Eldon (Q-629).** The per-tenant envelope rule ([data.md](../architecture/data.md) item 3; data-retention section 8) exists so that destroying one tenant's keys erases every copy. The spool is excepted because: (a) its volume key is per instance volume, wrapped by the regional `S10a`, never shared, and destroyed after a drain to zero; (b) the volume is never backed up, snapshotted or restored; (c) records hold only identifiers and keyed digests; (d) rows live only until they are forwarded, and `secure_delete=ON` plus the checked WAL truncation run before the deprovisioning probe certifies (GLB-T68). Residual: freed blocks may still hold old frames, readable only with the volume key. Rejected: per-tenant data keys for `body`, which would put a KMS unwrap in the request path.
- **Residuals.** A crash loses up to 1,024 buffered ordinary records (D4). Until the store acknowledges them, unforwarded rows can be removed undetected by someone with volume write access. That includes `write_through` records; this residual is accepted (A1), and with the 30 s rule now an alert the window is bounded by capacity, not by 30 s. A rollback or a deleted file during a store outage is detected late, when step 5 runs, not at start; rows appended in between reach SEC-008 only as flagged evidence (7.4). During an outage, sign-in records over the `preauth` limit are counted, not recorded one by one (4.6). Open-row replay (F9): someone with volume write access and an old copy of the file can restore a closed open row whose MAC is still valid. Recovery then appends a second `unknown_after_restart` outcome. Only the store detects it, as a `conflict` on that `audit_id`, which pages. A late outcome is lost if TX10 fails and the process then exits; its intent survives. Refusal counts are lost on a crash. If the `<name>.failed` marker cannot be written and the process restarts first, the file is re-verified instead of staying failed (6.5).
- **Review findings, revision 1 (Gemini 4 Argon):** 1 to 7 fixed. The quarantine parts of the fixes for 1 and 7 are superseded by revision 2.
- **Revision 2 (founder decisions on PR #316; Fable 5.2 security review at `befd6de`).** Removed: the quarantine table and its MAC, TX8, per-request commits for ordinary routes, and the reopen rule after an ambiguous `COMMIT` (deferred). F1: 3, 4.1, 5.1, GLB-T82. F2: 4.4 step 5a, Q-645. F3: 1 (record bytes), TX6, GLB-T90. F4: 4.2, TX10, Q-646, GLB-T86. F5: 7.4, GLB-T87. F6: GLB-T78. F7: 3, GLB-T76. F8: 5.4, GLB-T88. F9: 1 (fresh file, fullfsync), 2 (`preauth` usage), the residuals above, GLB-T79, T80, T89. F10: GLB-T70, T81, T83, T84. Route class: Q-644 and Q-647. SEC-008 record shapes and the platform stream: 1 and 6.8.
- **Gemini 4 Argon re-check of revision 2 (APPROVE, two Lows, fixed by the coordinator):** `seq` in `body` is assigned at commit and is `null` in `late` rows (section 1); the "late file empty" recovery check applies to `spool-tenant.db` only (4.4 step 2).
- **Revision 2.1 (Eldon's answers of 2026-11-26 on PR #335; Q-644 and Q-645 resolved).** A1 (write-through is a synced local commit, then forwarding): precedence note, 3, 6.3 (receipts for `write_through` rows only), residuals above, GLB-T95. A2 (store down at start): 4.4 (steps 5 and 7 deferred, `h0`, the `waiting_store` paragraph; step 5a removed), 1 (fresh-file check deferred), 4.6 (sign-in exception), 5.1 W and 5.2 step 2 (the 30 s rule is an alert only, inferred from A2), 6.5, 7.4 (drain after a mismatch), GLB-T71, T80, T81, T91 to T94. F3 to F10 still hold: the F9 (T80) and F10 (T81) tests are rewritten for A2, the rest is unchanged.

## 10. UNVERIFIED
- Crash and power-loss durability of WAL with `synchronous=FULL` on the production volume type, and `flock` semantics there (gate GLB-T78).
- The production image's SQLite version (3.37 or later required; the dev machine has 3.45.1, 2026-11-25).
- Commit throughput of TX1 and TX9; the 8 KiB unit; the cost of `secure_delete`; the 200 ms and 256-record flush values.
- That reopening after an I/O error on `COMMIT` always yields a definite committed-or-not state (deferred, see 3).
- That `wal_checkpoint(TRUNCATE)` returning `(0, 0)` with readers quiesced removes every frame, and that truncated frames are unreadable in freed blocks.
- That `PRAGMA max_page_count` reproduces a real full disk, and that `statvfs` is accurate on the volume.
- Whether audit metadata counts as tenant data under data-retention section 8.
- That the membership check can return `memberRef`: today's `AccessClaims` carry `subject` and `token_id` (ADR-0069 Context), so PLT-030 must add `memberRef` with identity's owner.

## 11. Questions for Eldon
1. **Q-629**: M6: accept the per-volume key exception of section 9, or require per-tenant data keys for the spool?
2. **Q-630**: Q-614: may the fake and SEC-008 expose `list_open_intents(instance)` as a complete list taken at one checkpoint `version`? Does an intent whose outcome the store `rejected` stay on that list? (Revision 2 also needs the list to be filterable by `audit_class`, 4.4 step 7.)
3. **Q-631**: R3-5: agree the unit model (65,536 units replacing "100,000 records or 512 MiB"), the share on reads and denials, and refusals recorded only as capped per-minute aggregates that a crash can lose? (Revision 2: the share also covers the buffer.)
4. **Q-632**: Secret inventory ids for the spool's HMAC key versions and the per-volume data key: to be allocated in the ADR-0038 inventory by its owner when code lands; does SEC-008 need the same chain key versions, and for how long?
5. **Q-633**: A corrupt spool retires its `instance_id`: should SEC-008 mark that instance's store-open intents as unknown outcomes for operators, or keep them open? (Revision 2: the same applies to a `failed_closed` spool, 7.4.)
6. **Q-634**: SEC-008 and Q-614 (record schema, provisional here per ADR-0069 lane note): ratify the `K_chain` derivation label `seshna.spool.chain.v1`, the exclusion of `chain` from `body`, and the schemas of the `aggregate` and `key_rotation` records (5.2 step 5, TX7)?
7. **Q-646**: May the `AuditStore` port accept one late outcome directly, outside the instance's `seq` chain, when the late file cannot be written (4.2)?
8. **Q-647**: Which permission catalogue kinds count as money for write-through (3)?
