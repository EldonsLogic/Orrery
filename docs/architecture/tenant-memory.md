# Per-tenant memory

Status: draft
Owner: eldon

Plan row OPR-014 (Tier 3: tenancy and agent authority). Code: `services/operate/memory/`. Rules come from [prompt-injection-defence](../security/prompt-injection-defence.md) section 6 (memory is L3), [ai-layer](ai-layer.md) (per-tenant memory), [data-retention](../security/data-retention.md) (erasure) and ADR-0048 (the agent proposes, never acts).

## Model
A memory is a short note (at most 500 characters) of kind `preference`, `terminology` or `fact`, scoped to one tenant and one user. There is no tenant-wide or wildcard scope. Recipients, bank details, rates, rules, permissions and instructions are not kinds, so they cannot be stored.

## Rules
| Topic | Rule |
|---|---|
| Isolation | Every call carries `Scope(tenant_id, user_id)` (validated ids). Another tenant's or user's entry is indistinguishable from a missing one; the store re-checks the owner on read |
| Data, not instructions | Recall returns L3 `DataItem`s (`source` `memory:<kind>`, flag `memory_read`), never text for the instruction position. No entry field names a tool or role; the module imports nothing from the allow-list, so memory cannot grant authority or change an allow-list |
| Secrets | Obvious secrets (passwords, API keys, bearer tokens, JWTs, private-key headers, long opaque strings) and IDs (e-mail, IBAN, phone, long digit runs, Arabic-Indic digits too) are replaced by `[redacted]` before storing. Text that is only a secret is refused |
| Taint | The caller must say `tainted` (no default). Tainted writes, assistant notes derived from source content, and instruction-like text are stored `unverified`, never recalled, and promoted only by the owner's `confirm` with the exact text hash |
| Provenance | Source turn, source content ids, author (`user` or `assistant`), created time, confirmer and time |
| Expiry and caps | Default 90 days, maximum 365; 200 live entries per user, 5000 per tenant; oversize is refused, not truncated; recall returns at most 10 items and 2000 characters |
| Owner control | `list_entries`, `confirm`, `delete`, `erase_user` (right to erasure), `erase_tenant` (offboarding). The host must expose these only on a verified human session, never as agent tools. Hard delete, no tombstone with text |
| Audit | `memory.written`, `memory.write_quarantined`, `memory.read`, `memory.listed`, `memory.confirmed`, `memory.deleted`, `memory.erased`, `memory.tenant_erased`: ids, kind, length and keyed hash only. No audit port or a sink failure refuses the operation (a write is rolled back) |
| Fail closed | A bad scope, input, clock (NaN, infinite, negative, non-number, backwards, raising), store fault or audit fault gives a closed refusal code (`errors.py`) and stores nothing |

## Not here
Persistent store, embeddings or semantic search, model-written summaries, the event types in the events contract (Q-390), the host wiring into the chat prompt (Q-391).
