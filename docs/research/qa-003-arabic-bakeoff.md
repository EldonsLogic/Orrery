# QA-003: model bake-off on the Arabic eval set (Claude tiers)

Status: draft (QA-003). Owner: eldon. Method and results are reproducible from `evals/results/qa-003/`.

## What was run
- Set: `arabic_core`, 100 prompts (accounting terms, dialects, numbers, dates, mixed language, safety), scored by the offline harness (QA-001) with the replay adapter: `python3 -m evals.harness run --set arabic_core --adapter replay:evals/results/qa-003/responses-<model>.jsonl`.
- Models: three Claude tiers (Opus, Sonnet, Haiku class), each answering the same prompts blind: they received only the prompt text and the router instructions in `evals/results/qa-003/instructions.txt`, never the expected answers. Each model ran two batches of 50.
- No API key and no model gateway exist yet, so each model ran as a subagent inside a coding session. Non-Claude models were not tested. Decoding settings were not controlled.
- Two rounds. Round 1 left out two things the set requires: the fixed reference date (2026-11-07, per the set README) and the tool argument names (`report`, `metric`, `period`, `date_from`, `date_to`). Round 1 therefore understated every model and is kept only as disclosure. Round 2 adds both and is the result below.

## Results (round 2, pass rate on 100 prompts)
| Model class | Overall | Accounting terms | Dialect intent | Mixed language | Numbers | Dates | Safety |
|---|---|---|---|---|---|---|---|
| Opus | 91% | 96% | 92% | 100% | 95% | 73% | 80% |
| Sonnet | 89% | 96% | 92% | 100% | 80% | 80% | 80% |
| Haiku | 83% | 96% | 96% | 80% | 70% | 60% | 80% |

Round 1 for comparison: Opus 80%, Sonnet 77%, Haiku 57%.
By dialect (round 2): Opus Gulf 89%, Egyptian 93%, MSA 94%; Sonnet Gulf 85%, Egyptian 90%, MSA 100%; Haiku Gulf 81%, Egyptian 86%, MSA 81%.

## Reading the numbers
- Five prompts fail for all three models. At least three look like set problems, not model errors: `ar-core-002` (the models write the definite form "الإشعار الدائن", which the substring check rejects), `ar-core-045` (a tool call is a valid answer where the set expects an intent) and `ar-core-078` (a month given as `period` rather than as a date range). `ar-core-081` and `ar-core-097` are judgement calls (overdue-invoices intent; refuse versus ask). Fixing the set is a separate, reviewed change (native speakers, QA-002 rules); this run did not edit it.
- Dates are the weakest category for every model, then numbers for Haiku and Sonnet. Haiku's extra misses are mostly relative dates and Arabic digits.
- The strategy target for the release gate is 85% at client 1 (strategy/08). Opus and Sonnet clear it on this set, Haiku does not.

## Limits (UNVERIFIED claims avoided)
- One run per model, n=100, one prompt version: differences of a few points are noise. Do not rank Opus over Sonnet on this evidence.
- The set has no native-speaker review yet (every record `nativeSpeaker: false`), and the tool arguments were supplied in the prompt, so this measures routing and extraction, not open Arabic generation quality.
- Cost and latency were not measured.

## What it supports
- Routing and extraction of Arabic and mixed requests is feasible at a Sonnet-class or stronger tier on this set; a Haiku-class tier is not enough on dates and numbers without code help.
- Numbers and dates should be resolved by code, not the model (AGENTS.md principle 6): the weak categories are the ones the platform already computes deterministically.
- Next: fix the five set issues with a native reviewer, rerun with controlled settings through the model gateway when it exists, add non-Claude models, and measure cost per request. A model-routing ADR is not proposed here.
