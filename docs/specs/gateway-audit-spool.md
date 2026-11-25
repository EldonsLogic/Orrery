# Gateway local audit spool: specification before code (PLT-028)

Status: draft (Tier 3, security review by a different model before code)
Owner: partner
Plan ID: PLT-028 (G2)
Related: [ADR-0069](../decisions/ADR-0069-gateway-live-binding-audit-spool.md) sections 2.1 to 2.5, 2.10, 2.11, 5.5, 7; [ADR-0038](../decisions/ADR-0038-secrets-management.md); [ADR-0041](../decisions/ADR-0041-durable-adapter-state-on-tenant-database.md); [ADR-0006](../decisions/ADR-0006-tenancy-site-per-tenant.md); [data-retention.md](../security/data-retention.md) section 8; Q-614

This is the local side of the ADR-0069 spool: files, tables, transactions, admission, recovery and key rotation in one gateway instance, built against a fake `AuditStore`. Forwarding, checkpoint and receipt protocols are PLT-032's; this spec fixes only the local interface they call (section 7). Every choice marked **(P)** is proposed and may change in review without changing the structure. It closes or hands off the ADR's open items R3-1, R3-4, R3-5, M6 and the local parts of R3-2 and R3-3 (section 9).

## 1. Files, settings and units
- **(P)** Two files per instance on the encrypted in-country volume (ADR-0069 2.1): `spool-tenant.db` and `spool-preauth.db`, each with its own `-wal` file and an advisory lock file `<name>.lock`. Never on a network file system.
- **(P)** Standard library `sqlite3` only. Start refuses if `sqlite3.sqlite_version_info < (3, 37, 0)` (STRICT tables). One writer connection per file, opened with `isolation_level=None` (explicit transactions only) and guarded by a process lock; one read connection for PLT-032's batch reads.
- **(P)** Pragmas on every open: `journal_mode=WAL` (checked to read back `wal`), `synchronous=FULL`, `foreign_keys=ON`, `secure_delete=ON` (M6), `cell_size_check=ON`, `trusted_schema=OFF`, `busy_timeout=5000`, `journal_size_limit=67108864`, `wal_autocheckpoint=1000`.
- **(P) Units.** Capacity is counted in integer units, never in measured bytes: 1 unit = one row of `records` or `quarantine`; an `open_intents` row costs 2 units (its copy of the intent plus the reserved outcome). 1 unit stands for the 4 KiB ceiling times the overhead factor 2 = 8 KiB, so the ADR's "100,000 records or 512 MiB" becomes `U = 512 MiB / 8 KiB = 65,536` units for `tenant` and `8,192` units (64 MiB) for `preauth`. A physical check (5.3) backs the logical count.
- **(P) Record bytes.** `body` is the canonical record of ADR-0069 5.1 without `chain`: JSON with sorted keys, separators `,` and `:`, UTF-8, no NaN. At most 4,096 bytes; a larger body is a write failure (503 `audit_unavailable`), never truncated. PLT-032's wire envelope adds `chain` and framing outside this ceiling.
- **(P) Chain and MAC.** Per key version `K` from the secret store (ADR-0038), two derived keys: `K_chain = HMAC(K, "seshna.spool.chain.v1")`, `K_row = HMAC(K, "seshna.spool.open.v1")`. `chain(seq) = HMAC-SHA256(K_chain[key_id], chain(seq-1) || body)`; `chain(0)` is 32 zero bytes, and `instance_id`, `stream`, `seq` and `key_id` are inside `body`. `row_mac = HMAC-SHA256(K_row[key_id], stream || be64(seq) || be64(reserved_units) || chain || intent_body)`.

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
  audit_id TEXT, tenant_id TEXT NOT NULL, key_id TEXT NOT NULL,
  chain BLOB NOT NULL CHECK (length(chain) = 32),
  body BLOB NOT NULL CHECK (length(body) BETWEEN 2 AND 4096)) STRICT;
CREATE UNIQUE INDEX records_audit_phase ON records(audit_id, phase) WHERE phase IN ('intent','outcome');
CREATE INDEX records_tenant ON records(tenant_id);
CREATE INDEX records_key ON records(key_id);
CREATE TABLE open_intents (audit_id TEXT PRIMARY KEY, seq INTEGER NOT NULL UNIQUE,
  tenant_id TEXT NOT NULL CHECK (tenant_id <> ''), key_id TEXT NOT NULL,
  chain BLOB NOT NULL CHECK (length(chain) = 32),
  intent_body BLOB NOT NULL CHECK (length(intent_body) BETWEEN 2 AND 4096),
  reserved_units INTEGER NOT NULL CHECK (reserved_units = 1),
  row_mac BLOB NOT NULL CHECK (length(row_mac) = 32)) STRICT;
CREATE INDEX open_intents_key ON open_intents(key_id);
CREATE TABLE quarantine (seq INTEGER PRIMARY KEY, phase TEXT NOT NULL, audit_id TEXT,
  tenant_id TEXT NOT NULL, key_id TEXT NOT NULL, chain BLOB NOT NULL, body BLOB NOT NULL,
  receipt TEXT NOT NULL CHECK (receipt IN ('rejected','conflict')),
  receipt_version INTEGER NOT NULL) STRICT;
CREATE INDEX quarantine_key ON quarantine(key_id);
CREATE TABLE usage (tenant_id TEXT PRIMARY KEY, units INTEGER NOT NULL CHECK (units >= 0)) STRICT;
```
- `tenant_id` is the verified tenant (`tenant` file), the unverified host tenant or `''` (`preauth`), or `''` for platform rows (`key_rotation`, platform aggregates). It is an index derived from `body`; recovery checks it equals the body's field.
- `usage` holds one row per tenant plus the row `'*'` for the file total. It is a persisted cache of `count(records) + count(quarantine) + 2 * count(open_intents)`, grouped by tenant; recovery recomputes and compares it (4.4, step 4).
- No foreign key from `open_intents` to `records`: the intent row is pruned after delivery while the open row stays (ADR-0069 2.4).

## 3. Transactions (every write is `BEGIN IMMEDIATE` ... `COMMIT`; every one first reads `owner.epoch` and stops the writer if it is not this process's epoch)
| Id | Name | Statements inside one `BEGIN IMMEDIATE` | Durability point |
|---|---|---|---|
| TX0 | start | `UPDATE owner SET epoch = epoch + 1, boot_id = ?` | DP0 |
| TX1 | admit write | admission (5) with cost 3; `INSERT records` (intent); `INSERT open_intents`; `UPDATE checkpoint` head; `UPDATE usage` tenant and `'*'` +3 | DP1 |
| TX2 | close write | `SELECT open_intents` by `audit_id`, verify `row_mac`; `INSERT records` (outcome); `DELETE open_intents`; head; usage -1 | DP2 |
| TX3 | read or denial outcome | admission cost 1; `INSERT records`; head; usage +1 | DP3 |
| TX4 | aggregate | aggregate admission cost 1; `INSERT records` (`phase = 'aggregate'`); head; usage +1 | DP4 |
| TX5 | apply receipts (called by PLT-032) | checks of 6.3; `DELETE records` committed; `INSERT quarantine ... SELECT` and `DELETE records` for rejected or conflict; `UPDATE checkpoint` pruned fields; usage per tenant | DP5 |
| TX6 | recovery close | as TX2, outcome built from `intent_body` with `status: null`, `reason: "unknown_after_restart"` | DP6 |
| TX7 | key rotation | `INSERT records` (`key_rotation`, under the old key, naming the new `key_id`); `UPDATE checkpoint SET active_key_id = new` | DP7 |
| TX8 | destroy quarantine (deprovisioning, operator, audited) | `DELETE quarantine WHERE tenant_id = ?`; usage; then outside the transaction `PRAGMA wal_checkpoint(TRUNCATE)` | DP8 |
A commit that raises `sqlite3.OperationalError` or `DatabaseError` is a rollback, except an I/O error during `COMMIT`, where the outcome is unknown: the writer closes the connection, reopens and reads `checkpoint.head_seq` to learn whether the row landed before answering (7).

## 4. State machines
### 4.1 A record in the `tenant` spool
| State | Event | Guard | Action | Next | Durability |
|---|---|---|---|---|---|
| none | TX1, TX2, TX3, TX4, TX6 or TX7 | body ≤ 4,096; admission for TX1, TX3, TX4 | append with `seq = head_seq + 1`, chain under `active_key_id` | unforwarded | DP1 to DP4, DP6, DP7 |
| none | same | body > 4,096 or admission refused | rollback; 503 `audit_unavailable` (TX2 and TX6 are never refused: 5.1) | none | none |
| unforwarded | PLT-032 reads a batch | none | nothing local changes | unforwarded | none |
| unforwarded | TX5 with receipt `committed` | 6.3 checks pass | delete row | pruned | DP5 |
| unforwarded | TX5 with `rejected` or `conflict` | 6.3 checks pass | move to `quarantine` with receipt | quarantined | DP5 |
| unforwarded | tenant deprovisioned | none | none: never deleted out of order (it would break the chain); deprovisioning waits for drain (ADR-0069 5.5) | unforwarded | none |
| quarantined | correction committed by the store (PLT-032 resolution) | audited operator action | delete quarantine row | gone | PLT-032 |
| quarantined | TX8 | deprovisioning approvals | delete | gone | DP8 |

### 4.2 An `open_intents` row
| State | Event | Guard | Action | Next | Durability |
|---|---|---|---|---|---|
| none | write request | route effect `write`; writes ready (6); admission cost 3 | TX1; then the handler is called | open | DP1 |
| none | same | any guard fails or TX1 fails | 503 `audit_unavailable`; handler never called | none | none |
| open | handler returns or raises | `row_mac` valid | TX2 | closed (row deleted) | DP2 |
| open | TX2 fails (disk full, I/O) | effect possible | return the real result; queue in-memory retry with backoff 0.1 s to 5 s; row and reservation stay | open (retrying) | none |
| open (retrying) | retry succeeds | as TX2 | TX2 | closed | DP2 |
| open | `row_mac` invalid or key missing during TX2 | none | rollback; real result returned; stream `failed_closed`; page | open | none |
| open | process dies | none | none | open, found by recovery | none |
| open | recovery (4.4, step 6) | `row_mac` valid, key present, no local outcome for `audit_id` | TX6 | closed | DP6 |
| open | recovery | `row_mac` invalid, key missing, or an outcome already exists | leave the row; writes refused; page (GLB-T46) | open (unverifiable) | none |
| open | forwarder, TX5, key retirement | any | never touched: TX5 has no statement on this table; retirement waits (4.5) | open | none |

### 4.3 A reservation (outcome units)
| State | Event | Guard | Action | Next | Durability |
|---|---|---|---|---|---|
| none | TX1 | 5.1 write guards | `reserved_units = 1` in the open row; usage +2 for the row | held | DP1 |
| held | TX2 or TX6 | none (always fits: net -1 unit) | outcome +1, open row -2 | released | DP2, DP6 |
| held | restart | none | survives in the row; usage recomputed from tables at start | held | (DP1) |
| held | TX5 or any read admission | none | cannot consume it: read and aggregate limits count held units in `'*'` and the tenant row | held | none |

### 4.4 Restart recovery (R3-1)
| Step | State | Event or check | On success | On failure |
|---|---|---|---|---|
| 1 | starting | `flock` (exclusive, non-blocking) on `<name>.lock` | 2 | refuse to serve, exit non-zero (GLB-T08) |
| 2 | locked | open, pragmas read back, `PRAGMA quick_check`, schema version | 3 | `corrupt` (8.3) |
| 3 | open | TX0 epoch bump | 4 | `corrupt` |
| 4 | fenced | keyring: every `key_id` in `records`, `open_intents`, `quarantine` and `checkpoint.active_key_id` loads from the secret store; chain verifies from `(pruned_through, pruned_chain)` to `(head_seq, head_chain)`; every `tenant_id` matches its body; every open row's `row_mac` verifies; `usage` equals the recomputation | 5 | key missing or check fails: `failed_closed` (writes refused, reads served to capacity, page); usage mismatch alone: rewrite from the recomputation and page |
| 5 | verified locally | store reachable: snapshot verification (ADR-0069 2.7, PLT-032 function; fake store here) **before any append** | 6 | verification fails: `failed_closed`; store unreachable: go to 6 and keep `store_checked = false` |
| 6 | close | for each valid open row in `seq` order: TX6, one transaction per row | 7 | TX6 fails: stop at that row, `failed_closed` |
| 7 | reconcile | needs the store. `O = list_open_intents(instance)` from the store, read while the forwarder is stopped and this process holds the lock, so it cannot shrink; for each `audit_id` in `O`: **satisfied** if `records` or `quarantine` holds a chain-verified `outcome` with that `audit_id`; else **missing**. Also, every local `intent` in `records` or `quarantine` must have a local `outcome` | `writes_ready` once a report is confirmed; start the forwarder | any missing: writes refused, page with the list; reads continue |
| 8 | serving | store unreachable at 5: reads only; steps 5 and 7 retried every 5 s | as above | as above |
Why this closes R3-1: step 6 turns every surviving open row into a local outcome first, so step 7 has one rule: a store-open intent is satisfied by a verified local outcome, whether the original one (committed locally, not yet forwarded) or the rebuilt one. An open intent with neither has truly lost its row. Invariant (tested): at the end of step 6, `open_intents` is empty or the instance is `failed_closed`.

### 4.5 MAC and chain key rotation (R3-4)
| Key state (local view) | Event | Guard | Action | Next | Durability |
|---|---|---|---|---|---|
| active | rotation requested with a new `key_id` | new key loads from the secret store and its derived keys compute | TX7 | verify_only | DP7 |
| active | TX7 fails | none | rollback; keep the old key active; alert | active | none |
| verify_only | rows depend on it | `deps(k) = count(records) + count(open_intents) + count(quarantine) WHERE key_id = k` > 0 | keep it loaded; export `spool_rows_by_key{key_id}` | verify_only | none |
| verify_only | deps reaches 0 on this instance | none | report `retirable` on the internal metric | retirable | none |
| retirable | key administrator retires the version in the secret store (ADR-0038 item 5 admin identity, outside the gateway) | every instance and every retained volume reports 0, and the store's own retention rule for that key is met (SEC-008) | gateway unloads it at next refresh | retired | secret store |
| any | start finds a row whose `key_id` cannot load | none | `failed_closed`; the row is never deleted or re-MACed | failed_closed | none |
(P) Keep-the-key, not re-authentication: unforwarded `records` under the old key need it anyway until pruned, so open rows add no new retention rule; re-MACing open rows would add a second code path that writes MAC material and would not help `records`, whose chain bytes the store re-verifies. Rotation never waits on deps; only retirement does.

### 4.6 The `preauth` spool
| State | Event | Guard | Action | Next | Durability |
|---|---|---|---|---|---|
| none | unverified denial or listener event (ADR-0069 1.5, 3.2) | total + 1 ≤ `8,192 - 256` | TX3 | unforwarded | DP3 |
| none | same | over the limit | 429 `rate_limited`; add to the in-memory counter `(reason)` | counted | none |
| counted | each 60 s | total + 1 ≤ 8,192 (band of 256) | TX4 with the counts and the window | unforwarded | DP4 |
| counted | band full | none | keep counting; the window grows; `preauth_unrecorded` metric | counted | none |
| unforwarded | TX5 | 6.3 | as 4.1 | pruned or quarantined | DP5 |
Verified requests never call `preauth` admission (ADR-0069 3.2). No `open_intents`, no tenant share; the `tenant_id` column holds the unverified host tenant only for the deprovisioning probe.

## 5. Admission (R3-5)
### 5.1 Limits for `tenant` ((P), `U = 65,536`)
| Path | Cost | File-total limit | Tenant-share limit `S = 0.20 U = 13,107` | Other guards |
|---|---|---|---|---|
| W: write intent (TX1) | 3 | total + 3 ≤ `0.90 U` = 58,982 | tenant + 3 ≤ S | `writes_ready`; a confirmed report within 30 s; physical (5.3) |
| R: read, denial or validation outcome (TX3) | 1 | total + 1 ≤ `U - B`, band `B = 0.01 U` = 655, so 64,881 | tenant + 1 ≤ S | physical (5.3) |
| G: aggregate (TX4) | 1 | total + 1 ≤ U | none (one record per tenant per 60 s) | physical free space only |
| O: late outcome (TX2), recovery close (TX6) | -1 net | none | none | never refused by admission |
| Platform (TX7, platform aggregates) | 1 | total + 1 ≤ U | none | none |
### 5.2 Algorithm
1. Before any transaction: stream not `failed_closed`; for W also `writes_ready` and `now_monotonic - last_confirmed ≤ 30 s`; physical check (5.3) for W and R.
2. `BEGIN IMMEDIATE`; epoch check; read `usage` for `'*'` and the tenant.
3. Apply the table row for the path. If any limit fails: `ROLLBACK`, answer 503 `audit_unavailable` (handler not called), and add one to the in-memory counter `(tenant, path, reason)`.
4. Otherwise insert, update `usage` for the tenant and `'*'`, `COMMIT`.
5. Every 60 s, per tenant with a non-zero counter: TX4 writes one `aggregate` record (counts per path and reason, window start and end, at most 4,096 bytes). If TX4 is refused, counting continues and the window grows.
Refused requests never ran a handler; they are not admitted records, so `audit_drop_count` stays a count of admitted records lost. A crash loses unwritten counts (residual, 9).

### 5.3 Physical guard (P)
At most once per second: `size(db) + size(wal) + 8 KiB × held reservations ≤ 512 MiB`, and `statvfs` free bytes ≥ `8 KiB × held reservations + 64 MiB`. Failing either refuses W and R (503); G and O still try. This catches the overhead factor being wrong; the unit count stays the admission authority.

### 5.4 Worked example
The store confirms reports but ingests slower than arrivals. `tenant` state: A 13,100 units (a read-heavy dashboard), B 4,000 (10 open writes = 20 units of open rows), C 2,000, platform 36; total 19,136.
- A's next 7 reads pass (tenant 13,107 = S). The 8th: 13,108 > 13,107, refused 503; counter `(A, R, tenant_share)`. A's writes: 13,107 + 3 > S, refused.
- B write (after A's 7 reads, total 19,143): 19,143 + 3 ≤ 58,982 and B 4,003 ≤ 13,107: admitted. B's late outcome: B 4,002, total 19,145, no check.
- A's aggregate after 60 s: total 19,146 ≤ 65,536: written. A's next aggregate comes 60 s later whatever its read rate.
- Under the ADR's rule as written (share on writes only, reads up to 100%), A's reads alone could add 65,536 - 19,136 = 46,400 units, past 58,982, refusing B's and C's writes. Now one tenant reaches at most 13,107 units, and refusing other tenants' writes takes at least `58,982 / 13,107 = 4.5` tenants at full share. The band keeps 655 units for aggregates and platform records once reads stop at 64,881; held reservations sit inside `'*'`, so no read can take a unit an open write's outcome needs.

## 6. Interface for PLT-032 (local side only; PLT-032 owns the protocol)
6.1 `stream_guard(stream)`: a per-stream in-process mutex. PLT-032 holds it across one store checkpoint read, `local_snapshot` and the comparison of ADR-0069 2.7; `apply_receipts` takes it too. This serialises verification and pruning, which is the local half of R3-2.
6.2 `local_snapshot(stream)` in one read transaction: `pruned_through`, `pruned_chain`, `prune_receipt_version`, `head_seq`, `head_chain`, and `chain_at(seq)` for `seq` in `(pruned_through, head_seq]`.
6.3 `apply_receipts(stream, through_seq, wm_seq, receipt_version, receipts)`: TX5. Refused, with nothing written, unless: `through_seq ≤ wm_seq`; `receipt_version ≥ prune_receipt_version`; every `seq` in `(pruned_through, through_seq]` exists in `records` and has exactly one receipt in `{committed, rejected, conflict}`; no receipt names a seq above `through_seq`. A call with `through_seq ≤ pruned_through` is a successful no-op, so replaying the original receipts of an already-committed prefix after a lost reply (R3-3) is safe locally; the store-side rule that returns those receipts is PLT-032's and SEC-008's.
6.4 `read_batch(stream, after_seq, max_records = 500, max_bytes = 1 MiB)`: one short read transaction on the read connection; rows in `seq` order with `key_id`, `chain`, `body`. Long reads block WAL checkpoints, so a batch never spans more than one transaction.
6.5 `report_confirmed(stream, monotonic_time)` and `fail_closed(stream, reason)`: in memory; after a restart nothing is confirmed until PLT-032 reports.
6.6 Read-only accessors for metrics: units per tenant, held reservations, `spool_rows_by_key`, quarantine count, oldest unforwarded `ts`, refusal counters.
6.7 The fake `AuditStore` used here implements only `checkpoint(instance, stream)` and `list_open_intents(instance)`; PLT-032's conformance suite owns the rest of Q-614.

## 7. Failure semantics
### 7.1 Crash (SIGKILL) at each durability point
| Point | Crash before `COMMIT` returns | Crash after `COMMIT`, before the next step |
|---|---|---|
| DP0 | lock released by the kernel; next start repeats | same |
| DP1 | no intent, no open row; handler not called; client sees a dropped connection | open row survives; recovery closes it `unknown_after_restart` (no effect happened, but it is unknown; GLB-T01) |
| DP2 | open row survives; recovery closes it as unknown (GLB-T02) | outcome unforwarded; store may list the intent as open; step 7 finds the local outcome (R3-1) |
| DP3 | no record; client sees a dropped connection; no effect | record kept; response may be lost |
| DP4 | counts lost (residual) | record kept |
| DP5 | nothing pruned; the store returns the original receipts on retry (ADR-0069 2.9) | pruned; open rows untouched (GLB-T30) |
| DP6 | that row stays open; the next start closes it, never twice (GLB-T31) | closed; next row next |
| DP7 | old key stays active | new key active; old key `verify_only` |
| DP8 | rows remain; operator repeats | rows gone; WAL truncation runs at next start if not run |
### 7.2 Disk full (`SQLITE_FULL`, or the 5.3 guard)
TX1 and TX3: rollback, 503, handler not called. TX2: real result returned, retry in memory, row and reservation kept; new W and R refused until 5.3 passes. TX5 frees space and is retried by PLT-032. TX6 at start: stop at the failing row, `failed_closed`. Graceful shutdown retries queued TX2s for at most 30 s (P) and leaves the rest to recovery. The unit budget (5.1) is set so that `U × 8 KiB` plus the 64 MiB margin fits the volume (INF-001 sizes it).
### 7.3 Corrupt or tampered file
- SQLite reports corruption (`SQLITE_CORRUPT`, `SQLITE_NOTADB`, `quick_check` not `ok`): state `corrupt`, not ready for any audited traffic (nothing can be appended), page. The file is never repaired, rebuilt or deleted in place: it is kept read-only on the volume for forensic reading and the deprovisioning probe. (P) The instance is replaced with a **new `instance_id`** and a fresh spool, so no `seq` stream is ever restarted; the old instance's store-open intents are an operator item (question 5).
- Chain, `tenant_id`, `row_mac` or `usage` check fails, or an open row is missing (4.4): `failed_closed` per ADR-0069 7.
- A live edit by another process: the epoch check stops a writer that lost its fencing; chain and MAC checks run on every TX2 and at every start.

## 8. Tests (stdlib `unittest`; crash tests run the spool in a subprocess killed with SIGKILL at a named hook; hooks are refused in production, as in ADR-0041; disk full is simulated with `PRAGMA max_page_count`)
| Test id | Test | Covers |
|---|---|---|
| GLB-T01 | `test_spool_intent_survives_sigkill_before_handler` | 4.2 none to open; DP1 |
| GLB-T02 | `test_restart_closes_open_intent_as_unknown` | 4.2 open to closed by recovery; DP2 before |
| GLB-T03 | `test_high_water_refuses_write_without_handler_call` | 5.1 W total limit |
| GLB-T08 | `test_second_spool_writer_refused` (adds: epoch mismatch stops the old writer) | 4.4 step 1; TX0 |
| GLB-T09 | `test_clock_backwards_keeps_seq_order` | 4.1 append |
| GLB-T30 | `test_pruned_intent_recovered_with_identity_fields_from_open_row` | 4.2 recovery; DP5 after |
| GLB-T31 | `test_crash_during_recovery_resumes_without_double_close` | 4.4 step 6; DP6 |
| GLB-T35 | `test_verified_requests_complete_during_sustained_preauth_saturation` | 4.6 |
| GLB-T44 | `test_deprovision_probe_covers_open_rows_quarantine_and_detached_volumes` | 4.1 deprovisioning; TX8; DP8 |
| GLB-T45 | `test_tenant_over_share_or_quarantined_does_not_block_other_tenant` | 5.1 share |
| GLB-T46 | `test_missing_or_bad_mac_open_row_detected_at_recovery` | 4.2 unverifiable; 4.4 step 7 missing |
| GLB-T50 (P) | `test_record_over_ceiling_is_write_failure_not_truncated` | 1 record bytes |
| GLB-T51 (P) | `test_apply_receipts_contiguity_quarantine_move_and_idempotent_replay` | 6.3; 4.1 pruned and quarantined |
| GLB-T52 (P) | `test_prune_never_exceeds_watermark_or_touches_open_intents` | 6.3; 4.2 forwarder row |
| GLB-T53 (P) | `test_outcome_commit_failure_returns_real_result_and_keeps_row` | 4.2 retrying; 7.2 |
| GLB-T54 (P) | `test_tenant_share_applies_to_reads_and_denials` (R3-5) | 5.1 R |
| GLB-T55 (P) | `test_late_outcome_and_recovery_close_never_refused_at_full_capacity` (R3-5) | 4.3; 5.1 O |
| GLB-T56 (P) | `test_refusals_become_one_aggregate_per_tenant_per_minute_in_band` | 5.2 step 5; 4.6 counted |
| GLB-T57 (P) | `test_store_open_intent_satisfied_by_unforwarded_local_outcome` (R3-1) | 4.4 step 7; DP2 after |
| GLB-T58 (P) | `test_usage_counters_recomputed_and_checked_at_start` | 4.3 restart; 4.4 step 4 |
| GLB-T59 (P) | `test_rotation_record_under_old_key_and_chain_continues` | 4.5 TX7; DP7 |
| GLB-T60 (P) | `test_key_not_retirable_while_open_row_or_record_depends_on_it` (R3-4) | 4.5 verify_only |
| GLB-T61 (P) | `test_missing_referenced_key_fails_closed_without_deleting_rows` (R3-4) | 4.5 any; 4.4 step 4 |
| GLB-T62 (P) | `test_preauth_full_returns_429_and_writes_aggregate_in_band` | 4.6 |
| GLB-T63 (P) | `test_disk_full_refuses_intent_and_retries_outcome` | 7.2 |
| GLB-T64 (P) | `test_corrupt_file_not_ready_and_preserved` | 7.3 |
| GLB-T65 (P) | `test_local_chain_or_tenant_field_tamper_detected_at_start` | 4.4 step 4 |
| GLB-T66 (P) | `test_sigkill_at_each_durability_point` (parametrised DP0 to DP8, both sides of `COMMIT`) | 7.1 |
| GLB-T67 (P) | `test_snapshot_and_prune_serialised_per_stream` (R3-2 local half) | 6.1 |
| GLB-T68 (P) | `test_secure_delete_and_wal_truncate_leave_no_closed_tenant_bytes_in_files` (M6) | 9 M6 |
Plus a measurement, not a pass or fail test: `bench_commit_rate_synchronous_full` (commits per second with one fsync each, on the test machine and later on the production volume; Eldon's low "measure sync throughput").

## 9. Open items: how each is closed or handed off
- **R3-1 (closed here):** 4.4 steps 6 and 7; GLB-T57, T31, T46.
- **R3-4 (closed here):** keep each verification key while any local row under it remains (4.5); retirement is gated on `deps = 0` on every instance and volume; a missing key fails closed without touching rows. GLB-T59 to T61.
- **R3-5 (closed here):** the 20% share applies to W and R; refusals become bounded aggregates; held reservations count in every limit and late outcomes are never refused (5). GLB-T54 to T56, T45. This changes ADR-0069 2.10 ("only that tenant's writes are refused") and section 7's row; the ADR text must follow before Accepted.
- **R3-2, R3-3 (local half here, protocol to PLT-032 and SEC-008):** 6.1 serialises snapshot and prune; 6.3 makes receipt replay a no-op locally and enforces contiguity on the pruned range only. Revalidating the store version and returning original prefix receipts stay PLT-032's and SEC-008's.
- **M6 (P): a stated exception, with conditions, pending Eldon (question 1).** The per-tenant envelope rule ([data.md](../architecture/data.md) item 3; data-retention section 8, "no tenant data is ever written under a shared key") exists so destroying one tenant's keys erases every copy. The spool is excepted because: (a) the volume key is **per instance volume**, a data key wrapped by the regional `S10a` in the KMS, never shared between volumes, and destroyed when the volume is decommissioned after a drain to zero, so the shredding unit is the volume; (b) the volume is never backed up, snapshotted or restored (ADR-0069 2.1); in-country replication, if INF-001 provides it, shares that key and lifecycle; (c) records hold identifiers and keyed digests only, never bodies, raw paths or tokens (ADR-0069 5.2); (d) rows live only until forwarded; a closed tenant's rows are drained, then `secure_delete=ON` overwrites deleted cells and `wal_checkpoint(TRUNCATE)` drops WAL frames before the deprovisioning probe certifies (GLB-T68). Residual: freed file-system blocks may still hold old frames, readable only with the volume key. Rejected fix (P): per-tenant data keys for `body` would put a KMS unwrap and a cache of every tenant's key in the request path (a KMS outage would refuse every request), and `preauth` has no verified tenant to key by.

## 10. UNVERIFIED
- Crash durability of WAL with `synchronous=FULL` on the production volume type, and `flock` semantics there.
- The production image's SQLite version (≥ 3.37 required; 3.45.1 on the dev machine, 2026-11-25).
- Commit throughput with one fsync per request; the 8 KiB unit (4 KiB × factor 2); `secure_delete` cost.
- That `PRAGMA max_page_count` reproduces the behaviour of a real full disk; `statvfs` accuracy on the volume.
- Whether truncated WAL frames remain readable in freed blocks; whether audit metadata counts as tenant data under data-retention section 8.

## 11. Questions for Eldon
1. M6: accept the per-volume key exception of section 9, or require per-tenant data keys for the spool?
2. Q-614: may the fake and SEC-008 expose `list_open_intents(instance)` as a complete list taken at one checkpoint `version`? Does an intent whose outcome the store `rejected` stay on that list?
3. R3-5: agree the unit model (65,536 units replacing "100,000 records or 512 MiB") and the share applied to reads and denials, with refusals recorded only as per-minute aggregates that a crash can lose?
4. Secret inventory ids for the spool's HMAC key versions and the per-volume data key: to be allocated in the ADR-0038 inventory by its owner when code lands; does SEC-008 need the same chain key versions, and for how long?
5. A corrupt spool retires its `instance_id`: should SEC-008 mark that instance's store-open intents as unknown outcomes for operators, or keep them open?
