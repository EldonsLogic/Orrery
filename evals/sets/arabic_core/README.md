# arabic_core eval set (v0)

Status: draft
Owner: eldon

Purpose: the "Arabic/English core" set from [../../README.md](../../README.md). 100 short chat prompts, as an owner or accountant of a small trading company would type them, that check the assistant understands Arabic business language (Gulf, Egyptian, MSA, Arabizi and code-switching), reads numbers and dates correctly, picks the right intent, and refuses unsafe requests. Entities and tools follow [../../../contracts/examples/blueprint-trading-minimal.json](../../../contracts/examples/blueprint-trading-minimal.json) and [../../../contracts/tool-api.md](../../../contracts/tool-api.md).

Files
| File | Content |
|---|---|
| `cases.jsonl` | 100 records, one JSON object per line, UTF-8, Arabic unescaped; ids `ar-core-001` to `ar-core-100`; validates against [../../schema/eval-record.schema.json](../../schema/eval-record.schema.json) |
| `thresholds.json` | `min_pass_rate` 0.0 until the QA-003 bake-off sets it |

## Review status
**Not reviewed. Do not use as a gate.** Every record has `review.nativeSpeaker: false` and `reviewer: null`. The set was written by a non-native author (an AI agent). A native speaker of each dialect (Gulf: Saudi and Emirati; Egyptian) and an accountant must review phrasing, expected intents and answer keywords before any threshold above 0.0 is set. Reviewers set `nativeSpeaker: true` and their name per record.

Records whose expectation is debatable say `UNSURE:` in `notes` (13 at v0): ar-core-005, 008, 020, 043, 053, 059, 061, 071, 072, 078, 081, 088, 097. Most are placeholder report ids, the canonical unit for carton orders, or clarify-vs-act choices.

## Coverage
By category and dialect

| Category | msa | gulf | egyptian | mixed | Total |
|---|---|---|---|---|---|
| accounting_term | 7 | 13 | 5 | 0 | 25 |
| dialect_intent | 3 | 12 | 10 | 0 | 25 |
| numbers | 3 | 11 | 6 | 0 | 20 |
| dates | 2 | 9 | 4 | 0 | 15 |
| mixed_language | 0 | 5 | 3 | 2 | 10 |
| safety | 1 | 3 | 1 | 0 | 5 |
| **Total** | 16 | 53 | 29 | 2 | 100 |

By category and locale

| Category | ar-SA | ar-AE | ar-EG | ar | mixed |
|---|---|---|---|---|---|
| accounting_term | 9 | 6 | 5 | 5 | 0 |
| dialect_intent | 8 | 4 | 10 | 3 | 0 |
| numbers | 6 | 5 | 6 | 3 | 0 |
| dates | 7 | 2 | 4 | 2 | 0 |
| mixed_language | 3 | 2 | 3 | 0 | 2 |
| safety | 2 | 1 | 1 | 1 | 0 |
| **Total** | 35 | 20 | 29 | 14 | 2 |

By expected type: intent 65, tool_call 13, answer 12, clarify 6, refusal 4.

What each category tests
- **accounting_term**: explain (answer with `must_include` key terms) and do (intent) for VAT summary, tax vs simplified invoice, credit/debit notes, journal entries, receivables/payables, cost centre, fixed assets and depreciation, opening balance, custody (عهدة), receipt/payment vouchers, returns, discounts received/allowed, trial balance.
- **dialect_intent**: Gulf (أبي، ابغى، وش، شو، زين، حق، ودي، الحين، عطني، هال‑), Egyptian (عايز، ازاي، فين، دلوقتي، بتاع، كده، مش، كام، هات) and 3 MSA controls; tags `pair_*` link the same intent across dialects.
- **numbers**: Eastern Arabic digits with ٬ and ٫, number words (MSA and colloquial: خمسمية، ألفين ونص، تلات تلاف وميتين، نص مليون), mixed digit systems, SAR/AED/EGP with abbreviations ر.س، د.إ، ج.م, ٪ percentages, units (حبة، كرتون، دستة = 12). `normalized.amount` / `quantity` / `percent` hold the exact value; every conversion is spelled out in `notes`.
- **dates**: Gregorian with Egyptian/Gulf (يناير، مارس، فبراير) and Levantine (كانون الثاني، آذار) month names; relative dates resolved from `reference_date=2026-11-07` stated in `notes`, or clarify; Hijri dates as `normalized.hijri {y,m,d}` only; Ramadan hours and fiscal year questions answered from company settings.
- **mixed_language**: Arabizi (abghaa, shu, 3ayez) and English terms (PO, VAT report, aging report, invoice) inside Arabic.
- **safety**: in-model VAT computation, editing a posted invoice, prompt injection inside quoted supplier text (Gulf and Egyptian), and an approval-bypassing external send. All expect no write tool call.

## Intent vocabulary (23)
| Intent | Meaning |
|---|---|
| `sales.create_invoice` | Draft a sales (tax) invoice |
| `sales.create_order` | Create a sales order |
| `sales.create_quote` | Create a quotation |
| `sales.create_credit_note` | Credit note against an invoice |
| `sales.create_debit_note` | Debit note against an invoice |
| `sales.record_return` | Record a sales return |
| `sales.list_overdue` | List overdue or due-by invoices |
| `purchasing.create_po` | Create a purchase order |
| `purchasing.list_payables` | List amounts owed to suppliers |
| `inventory.check_stock` | Stock on hand for an item |
| `customers.create` | Create a customer |
| `customers.search` | Find a customer or contact detail |
| `finance.vat_summary` | VAT summary for a period |
| `finance.post_payment` | Incoming payment / receipt voucher (سند قبض) |
| `finance.post_disbursement` | Outgoing payment / payment voucher (سند صرف) or paid expense |
| `finance.create_journal_entry` | Manual journal entry |
| `finance.set_opening_balance` | Opening balance for an account |
| `finance.record_custody` | Custody / imprest advance (عهدة) |
| `assets.register` | Register a fixed asset |
| `reports.show` | Run a report or metric |
| `calendar.convert_date` | Hijri/Gregorian conversion |
| `calendar.working_hours` | Working hours, including Ramadan hours |
| `calendar.fiscal_period` | Fiscal year and period questions |

`tool` and `args` appear only on `tool_call` records and only use tools from the tool-api example table (`report.run`, `metric.query`, `customer.search`). Report ids `vat_summary`, `trial_balance`, `sales_returns`, `sales`, `expenses` are placeholders until a tenant tool set defines them.

## Known gaps
- Not native-reviewed (see above). Gulf coverage is Saudi and Emirati only; no Kuwaiti, Qatari, Bahraini or Omani variants. No Levantine or Maghrebi dialects.
- No legal facts are asserted: tax rates, invoice thresholds and Hijri-to-Gregorian equivalents are deliberately absent. Gregorian dates for Hijri inputs must come from the calendar code ([calendars-and-locale](../../../docs/architecture/calendars-and-locale.md)).
- Answer cases use substring `must_include` only; quality of explanations needs human or model grading.
- Single-turn only; no follow-up after a clarify.
- Relative-date cases depend on the fixed reference date 2026-11-07; the harness must inject it.
- Few voice-style or very long inputs, few typos beyond ة/ه and missing hamza.
- All company, customer and supplier names are fictional (e.g. مؤسسة النخلة التجارية، شركة النيل للتوريدات); invoice/PO numbers are made up.
