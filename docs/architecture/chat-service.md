# Chat service

Status: draft
Owner: eldon

Plan row OPR-010. Code: `services/operate/chat/`. One chat with modes ([ADR-0004](../decisions/ADR-0004-one-chat-role-based-views.md)); the service sits in front of the agent runtime ([agent-runtime](agent-runtime.md)) and emits only allow-listed AG-UI events ([ADR-0044](../decisions/ADR-0044-ag-ui-agent-to-screen-transport.md)). No model calls and no network here; everything external is an injected port.

## Flow of one message
`send(principal, session_id, message_id, text)` yields events: validate (principal has tenant, user, roles; message id; size; bidi clean) -> session lookup (tenant and user must match) -> dedup and one-run check (together, under a lock) -> router picks the mode -> detect language -> window the history -> `RUN_STARTED`, `STATE_SNAPSHOT` (session, mode, locale, direction), typing -> runtime events through `agui.events.sanitize` -> `RUN_FINISHED` (with display-only interrupts) or one `RUN_ERROR`.

## Rules
| Topic | Rule |
|---|---|
| Sessions | Keyed by tenant, user and session id. Another user or tenant gets `chat_session_not_found`, same as a missing id. `open_session` resumes the user's latest session or creates one. |
| Dedup | The client message id is unique per session. Same id and text after a finished run replays the stored reply and does not rerun or audit again; same id with other text is `chat_message_id_conflict`; a failed or cancelled id may be retried without a second user turn. |
| One run | One live run per session. A second message is rejected with `chat_run_in_progress` (not queued). A run mark older than the TTL is stale and is taken over (crash). A disconnect cancels the run and frees the session. |
| Cancel | `cancel()` sets the run's `CancelToken`; the stream stops, open text messages are closed, the partial reply is kept flagged `cancelled`, the stream ends with `RUN_ERROR` code `cancelled`. |
| History | Stored as data. The model sees it only as L3 `DataItem`s (`chat:history:user`, `chat:history:assistant`), sanitised and flagged by the runtime. The platform frame is built per run and travels as instructions, outside the history, so trimming (newest turns first, item and character caps, per-turn cut) can never drop it. Retention is a `RetentionHook` seam for OPR-012. |
| Language | Reply language is the majority script of the message's letters; a message with no letters keeps the session language; mixed text is kept as typed. Bidi embeddings, overrides and isolates and invisible controls are stripped from input and from every output chunk; LRM, RLM, ALM, ZWJ, ZWNJ stay. Arabic-Indic digits are normalised only by `parse_decimal` and `extract_numbers` (fail closed on ambiguity, `1,5` is not guessed); the results go to the runtime as `server_state`, never written by the model. |
| Mode | `RouterPort.route()` returns discover, ask, act or change; default and any fault or unknown value is `ask`. The mode grants nothing; the Tool API checks every call against the caller's roles. |
| Errors | Closed table in `errors.py` (bilingual, Arabic unreviewed, ADR-0033) or `internal_error`. Exception text never leaves; only its type is logged. Events naming the engine are dropped by the allow-list gate (ADR-0016). |
| Audit and logs | `chat.message_received`, `chat.message_sent` (hash and length, locale, mode, outcome) and the registered `chat.turn_completed`. No bodies in audit or logs. The hash is plain SHA-256: it proves equality, it does not hide short guessable messages. |

## Ports
`ChatStore` (sessions, entries, message records, `begin_run` / `end_run`; `MemoryChatStore` fake with `dump` / `load` to test restart), `RouterPort` (OPR-002), runtime factory (`loop_runtime_factory` wraps the OPR-001 loop and adds history to the model request), audit sink (same shape as the runtime `EventSink`), `RetentionHook`. Open points: Q-235 to Q-238.
