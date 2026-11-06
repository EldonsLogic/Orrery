# Spec 01: Discovery (Part 1)

Status: draft
Owner: unassigned
Plan IDs: DSC (plus QA, SEC where noted)

## Purpose
Turn an owner's business into a draft, visual Blueprint with as little human typing as possible, and turn the gaps into a quote. Discovery produces proposals; it never touches a tenant's engine.

## Responsibilities
1. **Interview** in Arabic or English: structured, adaptive, resumable; the owner can answer by text, voice note (later) or by uploading files.
2. **Template-first drafts**: when the owner has no tools, show a draft Blueprint from a template (first: trading and distribution) and let the owner correct it, instead of interviewing from a blank page.
3. **Read existing tools** through connectors ([connector interface](../../contracts/connector-interface.md)): API, files, documents with Arabic OCR, email/WhatsApp forwarding, late fallback browser session.
4. **Source-to-Blueprint mapping**: propose entity, field and role mappings with confidence scores.
5. **Gap analysis**: compare the draft Blueprint with the certified component library; classify each need as covered, configurable, or a candidate new component (hand-off to the component factory in [spec 02](02-blueprint-and-library.md)).
6. **Visual Blueprint**: render the Blueprint as diagrams and plain-language summaries the owner can approve (entities, flows, roles, approvals, reports), bilingual.
7. **Quote**: effort and price from the gap analysis (component requests, migration volume, integrations).

## Interfaces
| Contract | Use |
|---|---|
| [Blueprint schema](../../contracts/blueprint.schema.json) | Writes drafts (state `draft`); every element gets provenance (`template`, `interview`, `imported`) |
| [Connector interface](../../contracts/connector-interface.md) | Calls `describe/authorize/extract/normalise/map` |
| [Component manifest](../../contracts/component.manifest.schema.json) | Reads the registry for gap analysis |
| [Events](../../contracts/events.md) | Emits `chat.turn_completed`, `meter.ai_usage`, `meter.connector_run` |
| [Build states](../../contracts/build-states.md) | Requests draft to owner_approved on the owner's approval |
| AI gateway (Part 5) | All model calls ([ai-layer](../architecture/ai-layer.md)) |

## Data owned
Interview transcripts and summaries, uploaded files (staging), the source model, mapping proposals, template library, gap reports, quotes. All per tenant (prospect) and deleted or exported per the retention policy. Templates are platform-owned and contain no customer data.

## Key behaviours
- Every AI answer that changes the draft is a Blueprint patch validated by the validator before it is shown.
- The owner sees "what I understood" summaries in their language and can correct them; corrections set `humanEdited` in provenance.
- Low-confidence mappings are shown as questions, never silently applied.
- A prospect works in a pre-tenant workspace (no engine); the engine tenant is created only after owner approval and, for first clients, team review.
- Numbers (prices, volumes, VAT) in quotes come from code.

## Failure modes
| Failure | Handling |
|---|---|
| OCR misreads Arabic digits or names | Show confidence; require confirmation below threshold; keep the original image beside the value |
| Owner gives contradictory answers | Detect via validator and ask one clarifying question; do not guess |
| Source tool unreachable or rate-limited | Fall back to the next tier (file export); record the gap |
| Model hallucinates a field or entity | Validator rejects unknown component bindings; anything not in the library becomes a gap, not an invention |
| Interview drifts | Turn budget per stage; summarise and ask to confirm |

## Security notes
- Everything from connectors and files is untrusted: quoted data only, injection defences per [ai-layer](../architecture/ai-layer.md).
- Uploaded files are scanned and parsed in a sandbox.
- Prospect data is tenant data from the first upload: encrypted, isolated, deletable.
- No credentials are stored by Discovery; tokens sit in the vault.
- The model gets redacted samples, not full records ([data](../architecture/data.md)).

## Open questions
1. Voice input for Arabic dialects: which provider passes the Arabic eval? (Depends on evals.)
2. Is cross-border processing of prospect documents allowed under PDPL before a contract exists? (Legal.)
3. Quote model: fixed price per tier vs estimate from gap size. (Commercial; see strategy 07.)
4. How much of the visual Blueprint is a diagram vs structured cards? (Product/design.)

## Acceptance criteria
**G1 (spine proven)**
- A hand-written Blueprint and a hand-written source model for a toy trading company run through mapping and gap analysis producing a deterministic gap report.
- Provenance is present on every element and the autonomy rate can be computed from a Blueprint file.
- The Arabic eval seed set exists (starting 100 prompts) with a baseline run recorded.

**G2 (pilot-ready)**
- One real business goes from first chat (or Excel upload) to an owner-approved Blueprint with a plain-language bilingual summary and a quote, with at most the human edits recorded in provenance.
- Template-first path works for trading and distribution with no tools in place.
- At least tier 1 or tier 2 connector works for the pilot's actual source.
- No credential or customer data appears in logs, events or prompts (checked by test).
