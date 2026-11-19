# ADR-0036: Tool API domain error codes

Status: Accepted
Owner: eldon
Approved by: Eldon and partner (sayegh9, 2026-11-19; cross-model review via Gemini 4 Neon high; follow-up in Q-215)

## Context
Tool API section 7 had one catch-all `engine_error`, so a user who ships more stock than exists saw a generic failure. Owners need a specific, translated reason and a next step. Engine invisibility (ADR-0016) forbids passing engine text through, and Arabic is first-class (ADR-0015).

## Decision
Keep every existing top-level `code`. Add an optional `domain` block `{code, params}` to the error object. `domain.code` comes from a new versioned catalog (`contracts/tool-api-error-catalog.json`, JSON Schema 2020-12). Each entry fixes its class, `retryable`, typed param slots, i18n key `errors.domain.<id>`, English and Arabic messages (Arabic marked unreviewed until a native reviewer signs off, ADR-0033) and an owner action. All customer text is rendered from the catalog; params are validated, escaped and stripped of bidi controls. Invalid codes or params fail closed to `internal_error` with a correlation id. Unmapped engine failures stay `engine_error` without `domain`. The initial catalog has 14 codes. Code: `services/operate/toolapi/errors.py`. Contract Tool API moves to 0.2.0 (backward compatible addition).

## Alternatives rejected
- Expand the top-level code list: breaks every client that switches on `code` and mixes class with cause.
- Pass engine messages through: leaks engine names and internals (ADR-0016), carries untrusted text, and is English only.

## Consequences
Clients and the chat can show a precise Arabic or English reason and a next step; unknown clients still work. The PLT-024 gateway mapping must fill the catalog from engine failures; until then everything stays `engine_error`. The catalog grows by minor versions; ids are stable. Arabic text needs native review.

## Supersedes
none
