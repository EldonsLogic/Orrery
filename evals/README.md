# evals

Status: harness built (QA-001); data sets pending
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

**Data sets are empty until gate G1** (the Arabic core set is written separately under `sets/arabic_core/`).

## Harness (offline, no model calls)
Python package `evals/harness` (stdlib + `jsonschema`). Install: `pip install -r evals/requirements.txt`. Run from the repo root:

```
python3 -m evals.harness check                                   # validate every evals/sets/*/*.jsonl, ids, set names; counts by category and dialect; exit 1 on error
python3 -m evals.harness run --set arabic_core --adapter echo_expected   # oracle, must score 100%
python3 -m evals.harness run --set arabic_core --adapter null --out report.json   # must score 0%
python3 -m pytest evals/tests -q
```

### Record format
One JSON object per line in `evals/sets/<set>/*.jsonl`, enforced by [schema/eval-record.schema.json](schema/eval-record.schema.json) (JSON Schema 2020-12). Fields: `id` (`^[a-z0-9]+(-[a-z0-9]+)*-\d{3}$`, unique per set), `set` (folder name), `locale` (ar, ar-SA, ar-AE, ar-EG, en, mixed), `dialect` (msa, gulf, egyptian, mixed, none), `category` (accounting_term, dialect_intent, numbers, dates, mixed_language, safety), `input` (1 to 1000 chars), `expected`, `tags`, `notes`, `review` (`nativeSpeaker`, `reviewer`).

`expected.type` is one of intent, tool_call, answer, clarify, refusal. `intent` (dotted id) is required for intent and tool_call; `tool` and `args` (subset match) are allowed for tool_call only; `normalized` may hold `amount`, `currency`, `date` (ISO), `hijri` (`y`,`m`,`d`), `quantity`, `percent`; `must_include` / `must_not_include` apply to answer.

### Scoring (deterministic, numbers from code)
- intent: exact match. tool_call: intent, tool, and every expected arg present and equal.
- normalized: numbers compared numerically after mapping Arabic-Indic and Eastern Arabic digits and the separators for decimal and thousands; dates and currency exact; hijri dict exact.
- answer: substring checks after matching-only normalisation (tatweel and diacritics stripped; alef forms, ya/alef maqsura and ta marbuta/ha unified).
- clarify and refusal: response type only.
A record passes only when its type check and its `normalized` check (if any) both pass.

### Report and gate
`run` prints (or writes with `--out`) a JSON summary: totals, pass rate, per category, per dialect, failures with reasons. If `evals/sets/<set>/thresholds.json` exists (`{"min_pass_rate": 0.0}`) the command exits 1 when the pass rate is below it; no file means no gate. Exit 2 means a bad set or adapter name.

### CI hook
CI runs `python3 -m pytest evals/tests -q` and `python3 -m evals.harness check`; both are offline and need only `evals/requirements.txt`. Model runs are not part of this job.

### Plugging in a model adapter
An adapter implements the `Adapter` protocol in `harness/adapters.py`: a `name` and `respond(record) -> Response(kind, intent, tool, args, normalized, text)`, then is added to `ADAPTERS`. A real adapter must call the model only through our model gateway (not built; PLT-* rows) and read its endpoint and credentials from the environment, never from the repo. No provider SDK belongs in this package.
