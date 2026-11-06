# evals

Status: draft
Owner: unassigned

Purpose: evaluation sets and harnesses that gate model, prompt and component changes. Design: [ai-layer](../docs/architecture/ai-layer.md).

Planned eval sets
| Set | Content | Format |
|---|---|---|
| Arabic/English core | 100 prompts at start: Gulf and MSA, mixed language, accounting terms, Hijri dates, number formats | JSONL: id, input, expected behaviour or tool call, tags, locale |
| Interview to Blueprint | Conversations to expected Blueprint patches | JSONL + schema validation |
| Source mapping | Anonymised source models to expected mappings | JSON |
| Tool-call correctness | Right tool, right args, refusal when not permitted | JSONL |
| Injection resistance | Untrusted documents with embedded instructions | JSONL |
| Dates and calendars | Hijri conversion, working days, due dates, divergence overrides ([calendars-and-locale](../docs/architecture/calendars-and-locale.md)) | JSONL |
| Month simulation | Replay datasets (fictional) with expected reconciliation | CSV + JSON |
| Tenant-theme contrast | Sample brand palettes in light and dark; expected pass / auto-adjust / reject ([theming](../docs/architecture/theming.md)) | JSON |
| RTL checks | Screens, documents and date pickers rendered in RTL; golden screenshots and PDFs | Image/PDF goldens + assertions |

Thresholds: TBD per set before G1; recorded per release. Eval data uses fictional or anonymised content only.

**Empty until gate G1.**
