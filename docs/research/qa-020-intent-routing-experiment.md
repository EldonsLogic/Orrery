# QA-020: intent routing with a bounded-decision model, against a small general model and rules

Status: design and harness only (QA-020, optional). No model was called and no network was used. Owner: eldon.
Not a dependency: no gate, plan row or product decision waits on this. Synthetic data only.

## Question
When a chat turn arrives in Arabic or English, which tool intent does it map to, and how often is a risky action (R3 or R4) routed as if it were a read or a draft?

Our architecture puts routing on the small tier ([ai-layer, Tiering](../architecture/ai-layer.md)) and says ledger, tax and permission logic is code, never model (AGENTS.md principles 3 and 6). Routing is therefore a model task only where it is a classification with a closed output. This experiment asks whether a bounded-decision model (the output is limited to the intent vocabulary plus abstain) beats a small general model and a rules router enough to justify building it. It does not ask whether any model may act: the platform's risk class and approval rules still decide what runs ([tool-api, sections 2 and 11](../../contracts/tool-api.md)).

"Bounded-decision model" is not defined in the repo (a search of docs/ and agents/ found no definition). This design assumes a model whose decoding is restricted to a closed label set. That assumption is UNVERIFIED with the founders; see "What would change a decision".

## The three arms
1. **Rules baseline** (`evals/harness/intent_routing.py`, `RULES`). Bilingual keyword and regex patterns on normalised text (`normalize_arabic`: diacritics and tatweel removed, alef, ya and ta marbuta unified). One matching intent routes; zero or several matches abstain. Cost is zero, latency is measured.
2. **Small general model**: a small-tier chat model, prompted with the intent list and the instructions in a prompt-registry entry, asked for one intent or `abstain` as JSON. Model and version are chosen from `agents/model-registry.md` at run time and recorded with the run. Called only through the model gateway (PLT-009, not built), so the run is not in this session.
3. **Bounded-decision model**: the same closed label set enforced by decoding or a classifier head, with abstain as a label. Model and version chosen at run time, as for arm 2.

Models run at fixed settings (temperature 0 where the provider allows it, fixed max tokens, one prompt version) and three times each. Predictions go to `predictions-<arm>-<run>.ndjson` in the format the harness documents; `score` produces the same report for every arm.

## Metrics
Computed by `score` from the predictions file. Abstain is a valid output and is not an error by itself.

| Metric | Definition |
|---|---|
| Accuracy | predicted intent equals expected intent, over all cases (abstain counts as wrong) |
| Per-intent precision, recall, F1 | one-vs-rest over the 26 vocabulary intents; macro F1 over intents with support |
| Wrong-risk-class rate | cases where a predicted risk class differs from the expected one, over all cases |
| Under-classified rate | cases where the predicted risk class is lower than expected, over all cases. This is the safety metric |
| Over-classified rate | predicted risk class higher than expected (costs friction, not safety) |
| Abstain rate | cases with no intent, over all cases; reported separately for ambiguous and unambiguous cases |
| Latency | per call, mean, p50 and p95 in ms, measured on the same machine class for every arm |
| Cost per 1000 | mean cost per call times 1000, from provider usage fields |

Risk classes (R0 read, R1 draft, R2 operational write, R3 ledger or tax posting, R4 never agent-creatable) follow `contracts/tool-api.md` section 11. The exact mapping is in `services/operate/toolapi/policy.py`, which is not in this worktree, so the mapping in the harness is UNVERIFIED until checked against that file.

## Pass and stop criteria (fixed before any model run)
Pass means the bounded-decision arm may move to a routing spike. All must hold on the native-reviewed set (not the synthetic set below):
- Under-classified rate on R3 and R4 cases is zero. One R4 under-classification stops the arm.
- Accuracy at least 3 points above the small general model, and at least 5 points above the rules arm, with a 95% bootstrap interval over cases reported.
- Arabic accuracy within 5 points of English accuracy, and no dialect group below 80%.
- Abstain rate at most 10% on unambiguous cases.
- p95 latency and cost per 1000 within the small-tier budget. The budget numbers are not set in this document and must be set before the run (UNVERIFIED).

Stop, with no further work on the arm, if any of these hold:
- The rules arm is within 2 points of the best model arm. Rules win on simplicity, cost and auditability.
- The bounded-decision arm fails the hard gate above.
- Results differ across the three runs by more than the interval width.
- No native-reviewed set exists when the work would start.

## Synthetic data rules
- Set: `evals/sets/intent_routing/cases.ndjson`, 60 cases, 30 English and 30 Arabic. Each case has `id`, `text`, `lang`, `dialect`, `expected_intent`, `expected_risk_class`, `ambiguous` and `review`.
- Intents are drawn from the 23-intent vocabulary in `evals/sets/arabic_core/README.md` (product and Tool API verbs) plus three Tool API verbs the set needs: `sales.cancel_invoice`, `supplier.update_bank_details` and `approval.decide`.
- Entities are fictional (Al Noor Trading, Nile Supplies, Delta Packaging, Gulf Dates Co). Identifiers are made up. IBAN-like strings start with `XX00TEST`. No `@` in any text. The checker enforces these.
- Arabic spread: MSA 8, Gulf 7, Egyptian 7, Levantine 2 (the set has only two Levantine cases), code-switched Arabic and English 6. Gulf is Saudi and Emirati style only. Kuwaiti, Qatari, Bahraini, Omani, Iraqi and Maghrebi variants are absent.
- Code-switching: English tool names and identifiers inside Arabic (VAT summary, PO, Credit note, Approve), as in the owner's chat.
- Arabic records carry `review: unreviewed` (ADR-0033: a native Arabic speaker reviews Arabic terminology). They are not used as a gate until a native reviewer signs each label and text. The author of this set is an AI agent, not a native speaker.
- Ambiguity: 5 cases are flagged (`ambiguous: true`). A good router may abstain on these. Ambiguity flags are not used to excuse errors on unambiguous cases.
- Arabic text is written in the matching-normalised form in the rules only. The hamza mark on ئ (as in دائن) is a combining mark that the normaliser removes, so rule patterns use the matching form. Model arms see the raw text.

## Threats to validity
- **Sample size.** n=60 gives a 95% interval of about ±10 points at 80% accuracy. Differences of a few points are noise (the same caution as QA-003).
- **Contamination of the rules baseline.** The rule patterns were written after the cases were drafted, with those cases in view. The rules score 58 of 60 (96.7%) on this set, which is a sanity check, not an out-of-sample estimate. A fair baseline needs a held-out set written before the rules, by a different author.
- **Author bias.** One AI author wrote both the cases and the labels. Labels for debatable cases (ambiguity flags) are judgement calls.
- **Label ambiguity.** For example, "the invoices due this week" can mean due-by or overdue. Native review may change labels; more than 5% changed labels invalidates this run.
- **Short, clean, single-turn text.** No typos, voice transcripts, long messages, follow-up turns after a clarify, or pasted documents. Real traffic will be harder.
- **Dialect coverage.** See the synthetic data rules.
- **Decoding and drift.** Provider model versions change; decoding settings may not be controllable on every provider. Record both with every run.
- **Latency.** Measured on one machine class; network latency to a gateway is not in the rules number. Compare arms only within the same run conditions.
- **Scope of the label.** Intent accuracy does not test slot extraction, numbers or dates (see QA-003, where dates and numbers were the weakest categories and should be computed by code).

## What would change a decision
- A native reviewer changes more than 5% of labels or flags several cases as not Arabic that a Saudi or Emirati speaker would write: rerun before reading any score.
- A real anonymised sample of owner chat, with consent and under the data rules, shows a different intent distribution: rebuild the set on it.
- The bounded-decision option turns out not to be buildable on the gateway's providers: the arm is moot and the spike does not start.
- Rules reach parity on a fair held-out set: keep rules and drop both model arms for routing.
- A risk-class mapping change in `policy.py` changes expected R3 and R4 labels: update the set and rerun.

## Cost estimate (UNVERIFIED prices)
- Per call (assumption, to be measured): about 850 input tokens (intent list and instructions plus the message) and about 15 output tokens.
- Per 1000 calls: about 0.85M input and 15k output tokens. Cost per 1000 = (850,000 × input price + 15,000 × output price) / 1,000,000, in USD per million tokens.
- One run is 60 calls per model arm. Three runs per arm, two model arms: about 360 calls and about 0.31M input tokens in total.
- Prices are UNVERIFIED. They must be read from the provider's price list on the run day and recorded with the run. At any published list price this should be a small amount; the exact figure is not claimed here.
- Rules arm: zero model cost.

## Sources
- Internal: [ai-layer](../architecture/ai-layer.md) (tiering, cost caps, evals); [qa-003-arabic-bakeoff](qa-003-arabic-bakeoff.md) (method and caveats); [tool-api](../../contracts/tool-api.md) (verbs, risk classes); [evals README](../../evals/README.md) (offline harness conventions); [arabic_core README](../../evals/sets/arabic_core/README.md) (intent vocabulary); [ADR-0033](../decisions/ADR-0033-v1-valuation-rounding-and-arabic-review.md) (Arabic review).
- External: none consulted. No web access was used in this session. Any vendor claim about model capability, price or latency is UNVERIFIED.

## Run status
- Harness and 60-case set built; the QA-020 tests and repo hygiene pass.
- Rules arm run: accuracy 96.7% (58/60), macro F1 0.982, abstain rate 3.3% (the two ambiguous cases), under-classified rate 0, latency p95 well under 1 ms. Read with the contamination caveat above.
- Model arms: not run. Blocked on the model gateway (PLT-009) and the native review of the Arabic labels.
