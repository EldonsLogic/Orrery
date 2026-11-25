# Gateway local audit spool: specification before code (PLT-028)

Status: draft, revision 1 (Tier 3, security review by a different model before code)
Owner: partner
Plan ID: PLT-028 (G2)
Related: [ADR-0069](../decisions/ADR-0069-gateway-live-binding-audit-spool.md) sections 2.1 to 2.5, 2.10, 2.11, 5.5, 7; [ADR-0038](../decisions/ADR-0038-secrets-management.md); [ADR-0041](../decisions/ADR-0041-durable-adapter-state-on-tenant-database.md); [ADR-0006](../decisions/ADR-0006-tenancy-site-per-tenant.md); [data-retention.md](../security/data-retention.md) section 8; Q-614

This is the local side of the ADR-0069 spool: files, tables, transactions, admission, recovery and key rotation in one gateway instance, built against a fake `AuditStore`. Forwarding, checkpoint and receipt protocols are PLT-032's; this spec fixes only the local interface they call (section 6) and the local comparison rules they must apply (4.7). Every choice marked **(P)** is proposed and may change in review without changing the structure. It closes or hands off ADR-0069's open items R3-1, R3-4, R3-5, M6 and the local parts of R3-2 and R3-3 (section 9). Revision 1 answers a Gemini 4 Argon security review (findings 1 to 7, section 9).

## 1. Files, settings, units and MACs
- **(P)** Two files per instance on the encrypted in-country volume (ADR-0069 2.1): `spool-tenant.db` and `spool-preauth.db`, each with its own `-wal` file and an advisory lock file `<name>.lock`. Never on a network file system.
- **(P)** Standard library `sqlite3` only. Start refuses if `sqlite3.sqlite_version_info < (3, 37, 0)` (STRICT tables). One writer connection per file, opened with `isolation_level=None` (explicit transactions only) and guarded by a process writer lock; one read connection for PLT-032's batch reads.
- **(P)** Pragmas on every open: `journal_mode=WAL` (read back as `wal`), `synchronous=FULL`, `foreign_keys=ON`, `secure_delete=ON` (M6), `cell_size_check=ON`, `trusted_schema=OFF`, `busy_timeout=5000`, `journal_size_limit=67108864`, `wal_autocheckpoint=1000`.
- **(P) Units.** Capacity is counted in integer units, never in measured bytes: 1 unit = one row of `records` or `quarantine`; an `open_intents` row costs 2 units (its copy of the intent plus the reserved outcome). 1 unit stands for the 4 KiB ceiling times the overhead factor 2 = 8 KiB, so the ADR's "100,000 records or 512 MiB" becomes `U = 512 MiB / 8 KiB = 65,536` units for `tenant` and `U_p = 8,192` units (64 MiB) for `preauth`. A physical guard (5.3) backs the logical count.
- **(P) Record bytes.** `body` is the canonical record of ADR-0069 5.1 without `chain`: JSON with sorted keys, separators `,` and `:`, UTF-8, no NaN. At most 4,096 bytes; a larger body is a write failure (503 `audit_unavailable`), never truncated. PLT-032's wire envelope adds `chain` and framing outside this ceiling. `instance_id`, `stream`, `seq`, `key_id`, `phase`, `audit_id` and `tenant_id` are inside `body`.
- **(P) Keys.** Per key version `K` from the secret store (ADR-0038), two derived keys: `K_chain = HMAC(K, "seshna.spool.chain.v1")` and `K_mac = HMAC(K, "seshna.spool.rowmac.v1")`. `lp(x) = be32(len(x)) || x`.
- **(P) Chain.** `chain(seq) = HMAC-SHA256(K_chain[key_id], chain(seq-1) || body)`; `chain(0)` is 32 zero bytes.
- **(P) Open-row MAC** (finding 3): `HMAC-SHA256(K_mac[key_id], lp("open") || lp(instance_id) || lp(stream) || lp(audit_id) || lp(tenant_id) || be64(seq) || lp(key_id) || be64(reserved_units) || chain || lp(intent_body))`.
- **(P) Quarantine-row MAC** (finding 1), computed in TX5 under the record's own `key_id`: `HMAC-SHA256(K_mac[key_id], lp("quarantine") || lp(instance_id) || lp(stream) || be64(seq) || lp(phase) || lp(audit_id or "") || lp(tenant_id) || lp(key_id) || lp(receipt) || be64(receipt_version) || chain || lp(body))`. A quarantined row's predecessors are deleted, so its chain cannot be re-verified locally; the MAC replaces that check.
- **Column binding.** Every indexed column (`seq`, `phase`, `audit_id`, `tenant_id`, `key_id`) must equal the same field in its `body` or `intent_body`. TX2 checks this for the row it closes; recovery step 4 checks it for every row.

## 2. Schema (both files; `preauth` never has `open_intents` rows)
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
CREATE TABLE quarantine (seq INTEGER PRIMARY KEY, phase TEXT NOT NULL,
  audit_id TEXT CHECK (phase NOT IN ('intent','outcome','reconcile') OR audit_id IS NOT NULL),
  tenant_id TEXT NOT NULL, key_id TEXT NOT NULL, chain BLOB NOT NULL, body BLOB NOT NULL,
  receipt TEXT NOT NULL CHECK (receipt IN ('rejected','conflict')),
  receipt_version INTEGER NOT NULL, row_mac BLOB NOT NULL CHECK (length(row_mac) = 32)) STRICT;
CREATE INDEX quarantine_key ON quarantine(key_id);
CREATE INDEX quarantine_audit ON quarantine(audit_id, phase);
CREATE TABLE usage (tenant_id TEXT PRIMARY KEY, units INTEGER NOT NULL CHECK (units >= 0)) STRICT;
```
- `tenant_id` is the verified tenant (`tenant` file), the unverified host tenant or `''` (`preauth`), or `''` for platform rows (`key_rotation`, platform aggregates).
- `usage` holds one row per tenant plus `'*'` for the file total: a persisted cache of `count(records) + count(quarantine) + 2 * count(open_intents)` per tenant, recomputed and compared at start (4.4 step 4).
- No foreign key from `open_intents` to `records`: the intent row is pruned after delivery while the open row stays (ADR-0069 2.4).

## 3. Transactions
Every write runs under the process writer lock as `BEGIN IMMEDIATE` ... `COMMIT`. Its first statement reads `owner.epoch`; a mismatch stops the writer. **Any exception before `COMMIT` is followed by an explicit `ROLLBACK`** (with `isolation_level=None` a failed statement leaves the transaction open; finding 6). An I/O error raised by `COMMIT` itself leaves the outcome unknown: the writer closes the connection, reopens (SQLite recovers the WAL) and reads the column in the last column below before answering (UNVERIFIED that the reopen always gives a definite answer; 10).
| Id | Name | Statements inside one `BEGIN IMMEDIATE` | DP | Ambiguous `COMMIT`: read |
|---|---|---|---|---|
| TX0 | start | `UPDATE owner SET epoch = epoch + 1, boot_id = ?` | DP0 | `owner.epoch`, `boot_id` |
| TX1 | admit write | admission (5.2) cost 3; `INSERT records` (intent); `INSERT open_intents`; `UPDATE checkpoint` head; `usage` tenant and `'*'` +3 | DP1 | `head_seq`; open row by `audit_id` |
| TX2 | close write | `SELECT open_intents` by `audit_id`: **absent: `ROLLBACK`, `failed_closed`, page** (finding 3); verify `row_mac` and column binding; refuse an outcome with `status` null or `reason` `unknown_after_restart` (finding 7); `INSERT records` (outcome); `DELETE open_intents`; head; usage -1 | DP2 | `head_seq`; open row absent |
| TX3 | read or denial outcome | admission cost 1; `INSERT records`; head; usage +1 | DP3 | `head_seq` |
| TX4 | aggregate | admission G (5.1); `INSERT records` (`aggregate`); head; usage +1 | DP4 | `head_seq` |
| TX5 | apply receipts (PLT-032) | checks of 6.3; `DELETE records` committed; for rejected or conflict `INSERT quarantine` with `row_mac`, `DELETE records`; `UPDATE checkpoint` pruned fields; usage per tenant | DP5 | `pruned_through`, `prune_receipt_version` |
| TX6 | recovery close | open row as in TX2; `INSERT records` with `phase = 'outcome'`, `seq = head_seq + 1`, `key_id = active_key_id`, `ts` = wall clock now, identity and route fields copied from `intent_body`, `status`, `error_code`, `latency_ms` and `upstream_correlation` null, `reason = "unknown_after_restart"`; `DELETE open_intents`; head; usage -1 | DP6 | `head_seq`; open row absent |
| TX7 | key rotation (each file) | admission K (5.1); `INSERT records` (`key_rotation`, `tenant_id = ''`, under the old key, naming the new `key_id`); `UPDATE checkpoint SET active_key_id = new`; head; usage `''` and `'*'` +1 | DP7 | `head_seq`, `active_key_id` |
| TX8 | destroy quarantine (deprovisioning, operator, audited) | `DELETE quarantine WHERE tenant_id = ?`; usage | DP8 | `count(quarantine WHERE tenant_id = ?)` |
**WAL truncation after a drain or TX8 (M6, finding 6):** hold `stream_guard` (6.1) so PLT-032 is paused, close the read connection, run `PRAGMA wal_checkpoint(TRUNCATE)` and require the result `(busy = 0, log = 0)`; otherwise retry up to 10 times at 1 s, then page. Deprovisioning certification refuses without this result (UNVERIFIED: 10).

## 4. State machines
### 4.1 A record in a spool file
| State | Event | Guard | Action | Next | DP |
|---|---|---|---|---|---|
| none | TX1, TX2, TX3, TX4, TX6 or TX7 | file `serving` (4.4) for TX1 to TX4 and TX7, file in `close` (4.4 step 6) for TX6; body ≤ 4,096; admission for TX1, TX3, TX4, TX7 | append with `seq = head_seq + 1`, chain under `active_key_id` | unforwarded | DP1 to DP4, DP6, DP7 |
| none | same | not in the required state, body > 4,096 or admission refused | `ROLLBACK`; 503 `audit_unavailable` (TX2 and TX6 never refused by admission: 5.1) | none | none |
| unforwarded | PLT-032 reads a batch | none | nothing local changes | unforwarded | none |
| unforwarded | TX5 with receipt `committed` | 6.3 | delete row | pruned | DP5 |
| unforwarded | TX5 with `rejected` or `conflict` | 6.3 | move to `quarantine` with receipt and `row_mac` | quarantined | DP5 |
| unforwarded | tenant deprovisioned | none | never deleted out of order (it would break the chain); deprovisioning waits for drain (ADR-0069 5.5) | unforwarded | none |
| quarantined | start (4.4 step 4) | `row_mac` and column binding verify | none | quarantined | none |
| quarantined | same | either fails | `failed_closed`, page | quarantined | none |
| quarantined | correction committed by the store (PLT-032 resolution) | audited operator action | delete quarantine row | gone | PLT-032 |
| quarantined | TX8 | deprovisioning approvals | delete; then WAL truncation (3) | gone | DP8 |

### 4.2 An `open_intents` row
| State | Event | Guard | Action | Next | DP |
|---|---|---|---|---|---|
| none | write request | route effect `write`; checks of 5.2 inside the transaction | TX1; then the handler is called | open | DP1 |
| none | same | any guard fails or TX1 fails | 503 `audit_unavailable`; handler never called | none | none |
| open | handler returns or raises | row present; `row_mac` and binding valid; outcome is not a recovery outcome | TX2 | closed (row deleted) | DP2 |
| open | TX2 fails (disk full, I/O) | effect possible | real result returned; in-memory retry, backoff 0.1 s to 5 s; row and reservation stay | open (retrying) | none |
| open (retrying) | retry succeeds | as TX2 | TX2 | closed | DP2 |
| open | TX2 finds `row_mac` or binding invalid, or key missing | none | `ROLLBACK`; real result returned; `failed_closed`; page | open | none |
| absent | TX2 finds no row for its `audit_id` | none | `ROLLBACK`; real result returned; `failed_closed`; page (deleted or swapped row) | absent | none |
| open | process dies | none | none | open, found by recovery | none |
| open | recovery (4.4 step 6) | `row_mac` and binding valid, key present, no local outcome for `audit_id` | TX6 | closed | DP6 |
| open | recovery (4.4 step 4) | `row_mac` or binding invalid, key missing, or an outcome already exists | leave the row; `failed_closed`; page (GLB-T46) | open (unverifiable) | none |
| open | forwarder, TX5, key retirement | any | never touched: TX5 has no statement on this table; retirement waits (4.5) | open | none |

### 4.3 A reservation (outcome units)
| State | Event | Guard | Action | Next | DP |
|---|---|---|---|---|---|
| none | TX1 | 5.1 W | `reserved_units = 1` in the open row; usage +2 for the row | held | DP1 |
| held | TX2 or TX6 | none (net -1 unit) | outcome +1, open row -2 | released | DP2, DP6 |
| held | restart | none | survives in the row; usage recomputed at start | held | (DP1) |
| held | any admission of W, R, G or K | none | cannot consume it: every limit counts held units in `'*'`, and every physical floor (5.3) keeps `8 KiB × held` free | held | none |

### 4.4 Restart recovery (R3-1), per file
| Step | State | Check | On success | On failure |
|---|---|---|---|---|
| 1 | starting | `flock` (exclusive, non-blocking) on `<name>.lock` | 2 | refuse to serve, exit non-zero (GLB-T08) |
| 2 | locked | open; pragmas read back; `PRAGMA quick_check`; schema version | 3 | `corrupt` (7.3) |
| 3 | open | TX0 | 4 | `corrupt` |
| 4 | fenced | every `key_id` in any table and `checkpoint.active_key_id` loads; chain verifies from `(pruned_through, pruned_chain)` to `(head_seq, head_chain)`; column binding of every row; every open-row and quarantine-row `row_mac` verifies; `usage` equals the recomputation | 5 | `failed_closed`, not ready for any traffic on this file (no append onto unverified state), page; a `usage` mismatch alone: rewrite it and page |
| 5 | verified locally | store snapshot compared under 4.7, **before any append** | 6 | mismatch: `failed_closed`, not ready, page; store unreachable: `waiting_store` |
| 5a | `waiting_store` | not ready: no transaction on this file. `tenant`: health reports not ready, so no audited traffic reaches the instance. `preauth`: unverified requests get 429 and are counted in memory only. Retry the step that found the store unreachable (5 or 7) every 5 s | 6 (from 5) or 7 (from 7) | stays, alert after 60 s |
| 6 | close | for each open row in `seq` order: TX6, one transaction per row | 7 | TX6 fails: stop at that row, `failed_closed` |
| 7 | reconcile | `O = list_open_intents(instance)` from the store, read under the lock while the forwarder is stopped, so it cannot shrink. Required set `Q = O ∪ {audit_id of every intent in records}`. Each `audit_id` in `Q` is **satisfied** by an `outcome` in `records` (chain verified in step 4) or in `quarantine` (`row_mac` verified in step 4); else **missing**. A quarantined intent that is not in `O` is not required (finding 1: no wedge when its outcome was committed and pruned) | `serving`: reads ready; `writes_ready` after the first confirmed report; start the forwarder | any missing: `serving` with writes refused, page with the list; operator resolution is PLT-032's. Store unreachable: `waiting_store` (5a), then retry step 7 (open rows are already closed) |
Why this closes R3-1: step 6 turns every surviving open row into a local outcome first, so step 7 has one rule: a required intent is satisfied by a verified local outcome, either the original (committed locally, not yet forwarded) or the rebuilt one. A required intent with neither has truly lost its row, and a forged quarantine outcome cannot satisfy it without `K_mac`. Invariant (tested): after step 6, `open_intents` is empty or the file is `failed_closed`. Step 5a is stricter than ADR-0069 2.11 and 7 (which serve reads with the store unreachable at start); the ADR text must follow.

### 4.5 MAC and chain key rotation (R3-4)
`deps(k)` = rows with `key_id = k` in `records`, `open_intents` and `quarantine`, plus 1 if `checkpoint.active_key_id = k`, summed over both files of a spool directory (finding 5).
| Key state | Event | Guard | Action | Next | DP |
|---|---|---|---|---|---|
| active | rotation with a new `key_id` | new key loads; both files `serving` | TX7 on `tenant`, then TX7 on `preauth` | verify_only | DP7 |
| active | TX7 fails on a file | none | `ROLLBACK`; that file keeps the old key; alert; retry | active on that file | none |
| verify_only | rows depend on it | `deps(k) > 0` | keep it loaded; export `spool_rows_by_key{key_id}` | verify_only | none |
| verify_only | `deps(k) = 0` on this instance | none | report `retirable` | retirable | none |
| retirable | retirement requested (key administrator, ADR-0038 item 5) | **active inventory probe**: every spool directory on every attached and detached volume in the volume inventory (INF-001), and every preserved corrupt file, returns `deps(k) = 0`. Attached: asked live through the instance's internal `key_dependents(k)`. Detached or preserved: a probe process takes the `flock`, opens and counts | retire the version in the secret store; instances unload it | retired | secret store |
| retirable | same | any listed volume unreachable, any file fails `quick_check`, any instance does not answer, or any `deps > 0` | refuse retirement; alert | retirable | none |
| any | start finds a row or checkpoint whose `key_id` cannot load | none | `failed_closed`; the row is never deleted or re-MACed | failed_closed | none |
(P) Keep-the-key, not re-authentication: unforwarded `records` under the old key need it anyway until pruned, so open and quarantine rows add no new retention rule; re-MACing would add a second code path that writes MAC material and would not help `records`. Rotation never waits on deps; only retirement does. A preserved corrupt file keeps its keys until the file is destroyed under the deprovisioning or forensic approvals.

### 4.6 The `preauth` spool
| State | Event | Guard (5.1 `preauth`) | Action | Next | DP |
|---|---|---|---|---|---|
| none | unverified denial or listener event (ADR-0069 1.5, 3.2) | R limit and floor | TX3 | unforwarded | DP3 |
| none | same | over a limit, or the file is not `serving` | 429 `rate_limited`; in-memory counter per reason | counted | none |
| counted | each 60 s | G limit and floor | TX4: one record with all reasons' counts and the window | unforwarded | DP4 |
| counted | G refused | none | keep counting; the window grows; `preauth_unrecorded` metric | counted | none |
| unforwarded | TX5 | 6.3 | as 4.1 | pruned or quarantined | DP5 |
Verified requests never call `preauth` admission (ADR-0069 3.2). No `open_intents`, no tenant share; `tenant_id` holds the unverified host tenant only for the deprovisioning probe.

### 4.7 Snapshot comparison (local half of ADR-0069 2.7; step 5 here, every 5 s in PLT-032; finding 2)
`L` = `local_snapshot` (6.2), `S` = the store checkpoint for `(instance, stream)`. Step 4 has already verified the local chain between L's anchor and head, so equality at single points suffices. Every row is checked; any failure is a mismatch.
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
`tenant`: `U = 65,536`, share `S = 0.20 U = 13,107`, band `B = 0.01 U = 655`, platform slot `P = 16`, per-tenant aggregate cap `A = 8` unforwarded aggregate rows (`records_agg`). `preauth`: `U_p = 8,192`, band 256, `P = 16`, aggregate cap 64.
| Path | Cost | File-total limit | Per-tenant limit | Other guards |
|---|---|---|---|---|
| W: write intent (TX1) | 3 | total + 3 ≤ `0.90 U` = 58,982 | tenant + 3 ≤ S | `writes_ready`; confirmed report within 30 s; floor `M_hi` |
| R: read, denial or validation outcome (TX3) | 1 | total + 1 ≤ `U - B` = 64,881 (`preauth`: 7,936) | tenant + 1 ≤ S (`preauth`: none) | floor `M_hi` |
| G: tenant or platform aggregate (TX4) | 1 | total + 1 ≤ `U - P` = 65,520 (`preauth`: 8,176) | that tenant's (or the platform's, `tenant_id = ''`) unforwarded aggregates < `A` (`preauth`: < 64) | floor `M_lo` |
| K: key rotation (TX7) | 1 | total + 1 ≤ U (`preauth`: 8,192) | none (no `records_agg` limit) | floor `M_lo` |
| O: late outcome (TX2), recovery close (TX6) | -1 net | none | none | never refused by admission |
The band holds `B - P = 639` units for tenant aggregates: at `A = 8` each, 79 tenants with full backlogs; beyond that, counters keep accumulating in memory. The last `P` units serve only key rotation (row K), so no aggregate, tenant or platform, can block TX7 (finding 4b; round 2 F1).
### 5.2 Algorithm (finding 4c)
1. Take the writer lock, `BEGIN IMMEDIATE`, check the epoch. The in-memory flags (`serving`, `failed_closed`, `writes_ready`, `last_confirmed`) and the cached physical reading (5.3) are changed only under the same writer lock, so reading them here is atomic with the insert.
2. Inside the transaction: refuse if the file is not `serving` or is `failed_closed`; for W, also if not `writes_ready` or `now_monotonic - last_confirmed > 30 s`; then the floor of 5.3 for the path.
3. Read `usage` for `'*'` and the tenant (and `count(records_agg)` for G). Apply the 5.1 row. On any refusal: `ROLLBACK`, 503 `audit_unavailable` (429 on `preauth`), handler not called, in-memory counter `(tenant, path, reason)` +1.
4. Otherwise insert, update `usage` for the tenant and `'*'`, `COMMIT`.
5. Every 60 s, per tenant with a non-zero counter: TX4 writes one `aggregate` record (counts per path and reason, window start and end, ≤ 4,096 bytes). If refused, counting continues and the window grows.
Refused requests never ran a handler; they are not admitted records, so `audit_drop_count` stays a count of admitted records lost. A crash loses unwritten counts (residual, 9).
### 5.3 Physical guard (P; findings 4a, 4d)
Refreshed at most once per second under the writer lock. `H` = held reservations in the `tenant` file. Per file: `size(db) + size(wal) + 8 KiB × H_file ≤ cap` (512 MiB `tenant`, 64 MiB `preauth`, `H_preauth = 0`). Volume, shared by both files: `statvfs` free bytes ≥ `8 KiB × H + M`, with `M_hi = 64 MiB` for W and R, `M_lo = 16 MiB` for G and K, and no floor for O. So no path except O can write into the space kept for reserved outcomes. The unit count stays the admission authority; the guard catches a wrong overhead factor.
### 5.4 Worked example
The store confirms reports but ingests slower than arrivals. `tenant` state: A 13,100 units (a read-heavy dashboard), B 4,000 (10 open writes = 20 units of open rows), C 2,000, platform 36; total 19,136.
- A's next 7 reads pass (tenant 13,107 = S). The 8th: 13,108 > 13,107, refused 503; counter `(A, R, tenant_share)`. A's writes: 13,107 + 3 > S, refused.
- B write (after A's 7 reads, total 19,143): 19,143 + 3 ≤ 58,982 and B 4,003 ≤ 13,107: admitted. B's late outcome: B 4,002, total 19,145, no check.
- A's aggregate after 60 s: total 19,146 ≤ 65,520 and A has 0 < 8 unforwarded aggregates: written. While ingest lags, A can hold at most 8 aggregate rows; its ninth minute stays in memory.
- Under ADR-0069 2.10 as written (share on writes only, reads up to 100%), A's reads alone could add 65,536 - 19,136 = 46,400 units, past 58,982, refusing B's and C's writes. Now one tenant reaches at most 13,107 units (+ 8 aggregates), and refusing other tenants' writes takes at least `58,982 / 13,107 = 4.5` tenants at full share. Held reservations sit inside `'*'` and inside every floor, so no read or aggregate can take a unit an open write's outcome needs.

## 6. Interface for PLT-032 (local side only; PLT-032 owns the protocol)
6.1 `stream_guard(stream)`: a per-stream in-process mutex. PLT-032 holds it across one store checkpoint read, `local_snapshot` and the 4.7 comparison; `apply_receipts` and WAL truncation take it too. This serialises verification and pruning (local half of R3-2).
6.2 `local_snapshot(stream)` in one read transaction: `pruned_through`, `pruned_chain`, `prune_receipt_version`, `head_seq`, `head_chain`, and `chain_at(seq)` for `seq` in `(pruned_through, head_seq]`. Callers compare under 4.7 and never treat `L.head_seq` and `S.head_seq` as the same value.
6.3 `apply_receipts(stream, through_seq, wm_seq, receipt_version, receipts)`: TX5. Refused, nothing written, unless `through_seq ≤ wm_seq`; `receipt_version ≥ prune_receipt_version`; every `seq` in `(pruned_through, through_seq]` exists in `records` and has exactly one receipt in `{committed, rejected, conflict}`; no receipt names a seq above `through_seq`. Receipts with `seq ≤ pruned_through` are ignored, never applied or counted, so `usage` is never decremented twice (finding 7). A call with `through_seq ≤ pruned_through` is a successful no-op, so replaying original receipts of an already-committed prefix after a lost reply (R3-3) is safe locally; the store-side rule that returns them is PLT-032's and SEC-008's.
6.4 `read_batch(stream, after_seq, max_records = 500, max_bytes = 1 MiB)`: one short read transaction on the read connection; rows in `seq` order with `key_id`, `chain`, `body`. A batch never spans more than one transaction (long reads block WAL checkpoints).
6.5 `report_confirmed(stream, monotonic_time)` and `fail_closed(stream, reason)`: set under the writer lock (5.2); in memory; after a restart nothing is confirmed until PLT-032 reports.
6.6 Read-only accessors: units per tenant, held reservations, `key_dependents(key_id)`, quarantine count, oldest unforwarded `ts`, refusal counters.
6.7 The fake `AuditStore` here implements only `checkpoint(instance, stream)` and `list_open_intents(instance)`; PLT-032's conformance suite owns the rest of Q-614.

## 7. Failure semantics
### 7.1 Crash (SIGKILL) at each durability point
| Point | Crash before `COMMIT` returns | Crash after `COMMIT`, before the next step |
|---|---|---|
| DP0 | lock released by the kernel; next start repeats | same |
| DP1 | no intent, no open row; handler not called; client sees a dropped connection | open row survives; recovery closes it `unknown_after_restart` (GLB-T01) |
| DP2 | open row survives; recovery closes it as unknown (GLB-T02) | outcome unforwarded; store may list the intent as open; step 7 finds the local outcome (R3-1) |
| DP3 | no record; dropped connection; no effect | record kept; response may be lost |
| DP4 | counts lost (residual) | record kept |
| DP5 | nothing pruned; the store returns the original receipts on retry (ADR-0069 2.9) | pruned and quarantined with MACs; open rows untouched (GLB-T30) |
| DP6 | that row stays open; the next start closes it, never twice (GLB-T31) | closed; next row next |
| DP7 | old key stays active on that file | new key active; old key `verify_only` |
| DP8 | rows remain; operator repeats | rows gone; certification still needs the WAL truncation result (3) |
### 7.2 Disk full (`SQLITE_FULL`, or the 5.3 guard)
TX1 and TX3: `ROLLBACK`, 503, handler not called. TX2: real result returned, retry in memory, row and reservation kept; W and R refused until 5.3 passes. TX5 frees space and is retried by PLT-032. TX6 at start: stop at the failing row, `failed_closed`. Graceful shutdown retries queued TX2s for at most 30 s (P) and leaves the rest to recovery. INF-001 sizes the volume so `(U + U_p) × 8 KiB + 64 MiB` fits.
### 7.3 Corrupt or tampered file
- SQLite reports corruption (`SQLITE_CORRUPT`, `SQLITE_NOTADB`, `quick_check` not `ok`): state `corrupt`, not ready, page. The file is never repaired, rebuilt or deleted in place; it is kept on the volume for forensic reading, the deprovisioning probe and the key probe (4.5). (P) The instance is replaced with a **new `instance_id`** and a fresh spool, so no `seq` stream ever restarts (question 5).
- Chain, column binding, `row_mac` or `usage` check fails, an open row is missing, or 4.7 finds a mismatch: `failed_closed` (4.4).
- A live edit by another process: the epoch check stops a writer that lost its fencing; TX2 checks its row's MAC and binding; everything is re-checked at every start.

## 8. Tests (stdlib `unittest`; crash tests kill a subprocess with SIGKILL at a named hook; hooks are refused in production, as in ADR-0041; disk full is simulated with `PRAGMA max_page_count`)
| Test id | Test | Covers |
|---|---|---|
| GLB-T01 | `test_spool_intent_survives_sigkill_before_handler` | 4.2 none to open; DP1 |
| GLB-T02 | `test_restart_closes_open_intent_as_unknown` | 4.2 recovery close; DP2 before |
| GLB-T03 | `test_high_water_refuses_write_without_handler_call` | 5.1 W |
| GLB-T08 | `test_second_spool_writer_refused` (adds: epoch mismatch stops the old writer) | 4.4 step 1; TX0 |
| GLB-T09 | `test_clock_backwards_keeps_seq_order` | 4.1 append |
| GLB-T30 | `test_pruned_intent_recovered_with_identity_fields_from_open_row` | 4.2 recovery; DP5 after |
| GLB-T31 | `test_crash_during_recovery_resumes_without_double_close` | 4.4 step 6; DP6 |
| GLB-T35 | `test_verified_requests_complete_during_sustained_preauth_saturation` | 4.6 |
| GLB-T44 | `test_deprovision_probe_covers_open_rows_quarantine_and_detached_volumes` | 4.1 deprovisioning; TX8 |
| GLB-T45 | `test_tenant_over_share_or_quarantined_does_not_block_other_tenant` | 5.1 share |
| GLB-T46 | `test_missing_or_bad_mac_open_row_detected_at_recovery` | 4.2 unverifiable; 4.4 step 7 |
| GLB-T50 (P) | `test_record_over_ceiling_is_write_failure_not_truncated` | 1 record bytes |
| GLB-T51 (P) | `test_apply_receipts_contiguity_quarantine_move_and_idempotent_replay` (incl. receipts below `pruned_through` ignored) | 6.3; 4.1 |
| GLB-T52 (P) | `test_prune_never_exceeds_watermark_or_touches_open_intents` | 6.3; 4.2 |
| GLB-T53 (P) | `test_outcome_commit_failure_returns_real_result_and_keeps_row` | 4.2 retrying; 7.2 |
| GLB-T54 (P) | `test_tenant_share_applies_to_reads_and_denials` (R3-5) | 5.1 R |
| GLB-T55 (P) | `test_late_outcome_and_recovery_close_never_refused_at_full_capacity` (R3-5) | 4.3; 5.1 O |
| GLB-T56 (P) | `test_refusals_become_bounded_aggregates_per_tenant_in_band` | 5.1 G; 5.2 step 5 |
| GLB-T57 (P) | `test_store_open_intent_satisfied_by_unforwarded_local_outcome` (R3-1) | 4.4 step 7; DP2 after |
| GLB-T58 (P) | `test_usage_counters_recomputed_and_checked_at_start` | 4.3; 4.4 step 4 |
| GLB-T59 (P) | `test_rotation_record_under_old_key_and_chain_continues` | 4.5 TX7; DP7 |
| GLB-T60 (P) | `test_key_not_retirable_while_any_row_or_active_checkpoint_depends_on_it` (R3-4) | 4.5 deps |
| GLB-T61 (P) | `test_missing_referenced_key_fails_closed_without_deleting_rows` (R3-4) | 4.5; 4.4 step 4 |
| GLB-T62 (P) | `test_preauth_full_returns_429_and_writes_aggregate_in_band` | 4.6 |
| GLB-T63 (P) | `test_disk_full_refuses_intent_and_retries_outcome` | 7.2 |
| GLB-T64 (P) | `test_corrupt_file_not_ready_and_preserved` | 7.3 |
| GLB-T65 (P) | `test_local_chain_or_column_binding_tamper_detected_at_start` | 4.4 step 4 |
| GLB-T66 (P) | `test_sigkill_at_each_durability_point` (DP0 to DP8, both sides of `COMMIT`) | 7.1 |
| GLB-T67 (P) | `test_snapshot_and_prune_serialised_per_stream` (R3-2 local half) | 6.1 |
| GLB-T68 (P) | `test_secure_delete_and_wal_truncate_leave_no_closed_tenant_bytes_in_files` (M6) | 3; 9 M6 |
| GLB-T69 (P) | `test_forged_or_deleted_quarantine_row_detected_and_quarantined_intent_does_not_wedge` | 1; 4.1; 4.4 step 7 |
| GLB-T70 (P) | `test_caught_up_spool_anchor_compared_with_store_watermark` | 4.7 |
| GLB-T71 (P) | `test_store_unreachable_at_start_no_append_and_not_ready` | 4.4 step 5a |
| GLB-T72 (P) | `test_open_row_audit_id_or_tenant_swap_detected_and_missing_row_fails_closed` | 1 MAC; 4.2 absent |
| GLB-T73 (P) | `test_aggregate_band_per_tenant_cap_rotation_slot_and_floors` (both files; 8 platform aggregates do not block TX7) | 5.1 G, K; 5.3 |
| GLB-T74 (P) | `test_fail_closed_flag_set_concurrently_blocks_next_admission` | 5.2 steps 1 and 2 |
| GLB-T75 (P) | `test_key_retirement_probe_fails_closed_on_unreachable_or_corrupt_volume` | 4.5 retirable |
| GLB-T76 (P) | `test_ambiguous_commit_resolved_per_transaction_and_rollback_after_error` | 3 |
| GLB-T77 (P) | `test_close_write_refuses_recovery_outcome_and_recovery_outcome_fields` | TX2; TX6 |
Plus a measurement, not a pass or fail test: `bench_commit_rate_synchronous_full` (commits per second, one fsync each; on the test machine, later on the production volume; Eldon's low "measure sync throughput").

## 9. Open items and review findings: how each is closed or handed off
- **R3-1 (closed):** 4.4 steps 6 and 7; GLB-T57, T31, T46, T69.
- **R3-4 (closed):** keep each verification key while `deps > 0`, including the active checkpoint, and retire only after an active probe of every attached, detached and preserved file (4.5). GLB-T59 to T61, T75.
- **R3-5 (closed):** the 20% share applies to W and R; aggregates are capped per tenant inside a band, with a platform slot; held reservations count in every limit and floor; late outcomes are never refused (5). GLB-T54 to T56, T45, T73. This changes ADR-0069 2.10 ("only that tenant's writes are refused") and section 7; the ADR text must follow before Accepted.
- **R3-2, R3-3 (local half here; protocol to PLT-032 and SEC-008):** 6.1 serialises snapshot and prune; 4.7 fixes the comparison; 6.3 makes receipt replay a no-op locally and enforces contiguity only on the range being pruned.
- **M6 (P): a stated exception with conditions, pending Eldon (question 1).** The per-tenant envelope rule ([data.md](../architecture/data.md) item 3; data-retention section 8, "no tenant data is ever written under a shared key") exists so destroying one tenant's keys erases every copy. The spool is excepted because: (a) the volume key is **per instance volume**, a data key wrapped by the regional `S10a` in the KMS, never shared between volumes, and destroyed when the volume is decommissioned after a drain to zero, so the shredding unit is the volume; (b) the volume is never backed up, snapshotted or restored (ADR-0069 2.1); in-country replication, if INF-001 provides it, shares that key and lifecycle; (c) records hold identifiers and keyed digests only (ADR-0069 5.2); (d) rows live only until forwarded; a closed tenant's rows are drained, `secure_delete=ON` overwrites deleted cells, and the checked WAL truncation of section 3 runs before the deprovisioning probe certifies (GLB-T68). Residual: freed file-system blocks may still hold old frames, readable only with the volume key. Rejected fix (P): per-tenant data keys for `body` would put a KMS unwrap and a cache of every tenant's key in the request path (a KMS outage would refuse every request), and `preauth` has no verified tenant to key by.
- **Review findings, revision 1:** 1 fixed (1 quarantine MAC, 2 schema, 4.4 step 7); 2 fixed (4.7, 4.4 steps 5 and 5a); 3 fixed (1 open-row MAC and binding, TX2, 4.2 `absent`); 4 fixed (5.1, 5.2, 5.3); 5 fixed (4.5); 6 fixed (3, with UNVERIFIED in 10); 7 fixed (2 checks, TX2, TX6, 6.3, question 6).

## 10. UNVERIFIED
- Crash durability of WAL with `synchronous=FULL` on the production volume type, and `flock` semantics there.
- The production image's SQLite version (≥ 3.37 required; 3.45.1 on the dev machine, 2026-11-25).
- Commit throughput with one fsync per request; the 8 KiB unit (4 KiB × factor 2); `secure_delete` cost.
- That reopening after an I/O error on `COMMIT` always yields a definite committed-or-not state (section 3).
- That `wal_checkpoint(TRUNCATE)` returning `(0, 0)` with readers quiesced removes every frame from the file; that truncated frames are unreadable in freed blocks.
- That `PRAGMA max_page_count` reproduces a real full disk; `statvfs` accuracy on the volume.
- Whether audit metadata counts as tenant data under data-retention section 8.

## 11. Questions for Eldon
1. **Q-629**: M6: accept the per-volume key exception of section 9, or require per-tenant data keys for the spool?
2. **Q-630**: Q-614: may the fake and SEC-008 expose `list_open_intents(instance)` as a complete list taken at one checkpoint `version`? Does an intent whose outcome the store `rejected` stay on that list?
3. **Q-631**: R3-5: agree the unit model (65,536 units replacing "100,000 records or 512 MiB"), the share on reads and denials, and refusals recorded only as capped per-minute aggregates that a crash can lose?
4. **Q-632**: Secret inventory ids for the spool's HMAC key versions and the per-volume data key: to be allocated in the ADR-0038 inventory by its owner when code lands; does SEC-008 need the same chain key versions, and for how long?
5. **Q-633**: A corrupt spool retires its `instance_id`: should SEC-008 mark that instance's store-open intents as unknown outcomes for operators, or keep them open?
6. **Q-634**: SEC-008 and Q-614 (record schema, provisional here per ADR-0069 lane note): ratify the `K_chain` derivation label `seshna.spool.chain.v1`, the exclusion of `chain` from `body`, and the schemas of the `aggregate` and `key_rotation` records (5.2 step 5, TX7)?
