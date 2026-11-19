# services/discovery/template_flow

Status: draft (DSC-004). Python 3.9+, standard library plus `jsonschema`. No model call, no network, no file write.

Template-first discovery: show the owner the draft Blueprint made from the vertical template (DSC-002), take corrections as structured edits, return a revised **draft**. It never produces a final Blueprint: build state stays `draft`, `Revision.final` is always `False` and a person approves later (DSC-009). It is separate from the interview agent (DSC-005, `services/discovery/interview/`); the two meet only through the Blueprint draft.

```python
from template_flow import TemplateFlow
flow = TemplateFlow(draft, clock=lambda: "2026-11-19T10:00:00Z")   # clock, semantic validator are injected ports
view = flow.summary()          # owner-readable view model: i18n keys + data (aligned with the DSC-007 viewer)
rev = flow.apply([{"id": "edit-000001", "pointer": "/company/legalName/ar", "value": "...", "baseHash": view["draftHash"]}])
rev.blueprint, rev.draft_hash, rev.final   # revised draft, hash, False
flow.history                   # hash-chained correction history; TemplateFlow(draft, history=...) restores it
```

## Rules
- **Edit shape**: exactly `id` (8-64 of `A-Za-z0-9_-`), `pointer`, `value`, optional `op` (only `set`) and `baseHash` (stale draft is refused). Unknown keys refused. There is no remove.
- **Allow-list**: only paths in `registry.json` can be set (legal name, CR and VAT numbers, location, role, record and approval names, approval amount thresholds, VAT prices-include and filing period, Hijri display). Country, VAT registration, e-invoicing, meta, build state, provenance, permissions are refused. Arrays are addressed by `id` (guards by `field|op`), never by index.
- **Pointers**: ASCII `[A-Za-z0-9_|.-]` segments, at most 8, 200 characters; no `..`, escapes, empty segments or dunder/prototype names.
- **Values** (owner text is untrusted data): type and range per field kind; text is NFC, trimmed, 1-200 (names 1-80); control, bidi, zero-width, tag, `{}` and `<>` characters refused; numerals in Arabic-Indic or Persian digits and Arabic separators are normalised; yes/no accepts Arabic (`نعم`, `لا`); objects, lists and null refused; raw size cap 1000.
- **Validation**: the batch is applied to a copy; the result must add no error against `contracts/blueprint.schema.json` (0.4.0) and none from the optional injected semantic validator (for example the Blueprint validator). All or nothing.
- **Replay**: an accepted edit id can never be used again (also after restoring a history). A refused edit does not use up its id.
- **History**: one entry per edit (seq, editId, pointer, before, after, actor, time, revision, prevHash, hash), SHA-256 chained; `verify_history` and restore refuse a broken chain. `provenance.humanEdited` is set on the nearest edited element and `meta.revision` rises by one per batch.
- **Errors**: `FlowError.code` (`TFL-EDIT-001/002`, `TFL-BATCH-001/002`, `TFL-PATH-001..003`, `TFL-VALUE-001..004`, `TFL-SCHEMA-001`, `TFL-SEM-001`, `TFL-REPLAY-001`, `TFL-STALE-001`, `TFL-STATE-001`, `TFL-HIST-001`). Messages never echo owner text. Every code has an Arabic and English message key `tpl.error.<code>` in `labels.json`.
- **Labels**: `labels.json` (`ar`, `en`, same keys). A web row must merge them into the message bundles (Q-286).

Tests: `tests/` (74 tests; Arabic input, hostile paths and values, schema bypass, replay, atomicity, history chain). Run: `python -m pytest services/discovery -q`.
