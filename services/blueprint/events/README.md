# Event stream reference implementation

Python package `evstream` (BPL-011): the shared, tested library for contract 4 ([events.md](../../../contracts/events.md)). Standard library and `jsonschema` only. Fictional data in tests. Event content is untrusted: no eval, no paths built from event values, iterative bounded walks (no recursion on input).

Run from the repo root (system python has no `jsonschema`; use the venv that has it):

```
cd services/blueprint/events
PYTHONPATH=. python3 -m evstream types
PYTHONPATH=. python3 -m evstream validate FILE.json|FILE.jsonl [--chain]
```

Exit 0 when every event is valid (warnings such as `unknown_type` do not fail), 1 on any problem or unreadable file. Tests: `python3 -m pytest services/blueprint/tests -q` (see `tests/events/`).

## Layout
| Path | What |
|---|---|
| `schemas/envelope.schema.json` | The envelope. `additionalProperties: false` everywhere except `data` |
| `schemas/types.json` | Registry: type -> `schema_version`, `data_class` default, `kind` (record, audit, agent, meter, platform), `scope`, `requires_trace`, data schema ref, `assumed` note |
| `schemas/data.{record,audit,agent,meter,platform}.schema.json` | One file per family, one `$defs` entry per data shape |
| `evstream/ulid.py` | Monotonic ULID generator and validator |
| `evstream/build.py` | `Context`, `build_event` |
| `evstream/validate.py` | `validate_event`, caps and heuristics |
| `evstream/store.py` | `EventStore`, `MemoryStore`, `find_gaps` |
| `evstream/redact.py` | `redact_for_model` |
| `evstream/export.py` | `export_tenant_jsonl`, `verify_chain` |

## Registry
Types are derived only from contract section 3. Keys written `<entity>.created` (and `updated`, `submitted`, `cancelled`, `transitioned`, `deleted`) are patterns: any entity name outside `reserved_domains` matches. A reserved domain with an unknown verb is an unknown type. `build.sandbox_ready`, `build.simulation_completed`, `build.cutover_started` come from [build-states.md](../../../contracts/build-states.md) (named there, not in events.md section 3). Platform events get kind `platform` (not one of the four kinds) and `tenant_id: "platform"`. `assumed` in `types.json` marks every choice the contract does not state. A test parses the contract's section 3 and fails if a type is missing.

## Error codes
`EVS-ENV-001` envelope schema; `-ENV-002` not an object or internal failure; `EVS-TYPE-001` unknown type (warning when consuming, error when producing); `-TYPE-002` schema_version differs (warning); `EVS-DATA-001` data schema; `-DATA-002` too big; `-DATA-003` too deep; `-DATA-004` whole record; `-DATA-005` not JSON; `-DATA-006` personal minimisation; `EVS-SUBJ-001`; `EVS-TRACE-001`; `EVS-TENANT-001` tenant spoof or foreign tenant id in data; `-TENANT-002` platform scope mismatch; `-TENANT-003` mixed tenants; `EVS-SEQ-001` producer sequence; `-SEQ-002` gap; `-SEQ-003` repeat or reorder; `EVS-DUP-001` event_id used by another tenant; `-DUP-002` event_id reused with other content; `EVS-CAUSE-001` causation not found in same tenant; `-CAUSE-002` self-cause; `EVS-FIELD-001` field not allowed in `build_event`; `EVS-CLASS-001` data_class below the type default (warning); `EVS-READ-001` bad read arguments. Full list in `evstream/errors.py`.

## Rules and heuristics (named constants in `validate.py`)
- Caps: `MAX_DATA_BYTES` 64 KB UTF-8 of serialised `data`; `MAX_DATA_DEPTH` 6; `MAX_DATA_NODES` 5000.
- Data is ids and changed values, not whole records. Heuristic: more than `MAX_DATA_KEYS` = 40 object keys in `data` (flat and nested counted together), or an object under a `WHOLE_RECORD_KEYS` key (`record`, `document`, `row`, `snapshot`, ...), or an object with `__whole_record__: true`. It is a heuristic: it can reject a legitimate wide payload and miss a narrow whole record.
- Tenant: `tenant_id` comes only from `Context`. Any key in `data` that normalises to `tenantid`, `tenantids` or `tenant` is rejected, even with the right value. A string value that looks like a tenant id (`t_` plus 3 or more characters) and differs from the event's tenant is rejected; `known_tenant_ids` adds exact matches. Heuristic: a harmless value such as `t_shirt` also trips it.
- Personal minimisation: when `data_class` is `personal` or `financial`, `data` may hold ids, enums, counts and short values only. Rejected: keys in `PERSONAL_DENY_KEYS` (name, email, phone, address, iban, notes, body, text, ...), strings over `MAX_PERSONAL_STRING` = 64 characters, and values shaped like an email, IBAN or phone number.
- `subject` required for record events. `trace` required for types with `requires_trace` (agent events except `memory.expired` and `eval.regression_detected`, and `meter.ai_usage`), for `actor.kind = agent`, and whenever `trace.model_id` is set (then it must be an object). `meter.ai_usage` also needs `trace.model_id`.
- Unknown types are accepted by `validate_event` and flagged `unknown_type`; `build_event` refuses them. A different `schema_version` from the registry is a warning and the data schema is not applied.
- `validate_event(ev, registry, stamped=True, known_tenant_ids=())` never raises. `stamped=False` is for events before append (sequence must be absent).

## Store
`MemoryStore` is append-only (no update or delete method). The store assigns `sequence` (1, 2, 3 per tenant) and stamps `recorded_at`; a producer sequence is rejected (`EVS-SEQ-001`). Appending an `event_id` that exists in the same tenant with the same content returns the stored event; other content is `EVS-DUP-002`; another tenant's `event_id` is `EVS-DUP-001` (the message does not say which tenant). `causation_id` must name an existing event of the same tenant. Returned events are deep copies. `read(tenant_id, after_sequence, limit)` is capped at 1000. `gaps(tenant_id)` returns missing ranges; a gap is an alert. Real stores must implement the same interface, per-tenant partitioning and tenant-key encryption ([data.md](../../../docs/architecture/data.md)); `MemoryStore` is a reference for tests.

## Redaction
`redact_for_model(ev, policy)` returns a copy. For `personal` and `financial` events, values under id-like keys (`id`, `*_id`, `*_ids`) and under `KEEP_KEYS` (enums and structure) are kept when short; every other value becomes `[REDACTED]` (mode `mask`) or is removed (mode `drop`). A summary goes in `data._redaction`. Other classes are copied unchanged. This is a minimum: free text in a business event is not touched.

## Not implemented
- Optional per-tenant hash chain (extension, off): each event would carry the hash of its predecessor for tamper evidence. `verify_chain` checks only tenant, order and gaps.
- Producer authentication and per-producer type allow-lists (threat T55): they belong to the ingestion gateway.
- Retention periods (UNVERIFIED legal minimum, see contract).
