# Session log: cmp-003-mandatory-fields-and-utc

Date: 2026-11-14
Author: partner
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: CMP-003

## Summary
Applied Eldon's review of PR #43. Missing mandatory fields are refused instead of defaulted, the QR time is converted to UTC, and dates and times are checked as real values. Merged main. The PR stays on hold until it meets ADR-0031's conditions.

## Model and prompt (ADR-0031 condition 4)
- Model: Claude Opus 5.5, in Claude Code, in the partner's session.
- Prompt: the partner relayed Eldon's request, "change the made-up defaults for mandatory fields to errors, convert the QR time to UTC, and wait for ADR-0031". Eldon's review comment on #43 was the brief. Its should-fix items:
  - Missing fields get invented values: `issue_time` 12:00:00, `invoice_type` simplified, quantity 1, price 0.
  - `TIME_REGEX` has no end anchor, and dates and times are not checked as real values.
  - The QR adds "Z" without converting from local time.
  - The docstring and the README claim immutability guardrails.
  - The manifest says MIT while the repo is all rights reserved.
  - The VAT number rule needs a source.
  - Untested cases: Arabic names over 255 bytes, time zones, and trailing characters in the time.

## Files touched
- `components/compliance/zatca_sa/phase1.py`: four changes.
  - **Mandatory fields.** `generate_phase1_invoice` refuses missing fields with one error per field. The fields are:
    - On the invoice: id, date, time, timezone, type, transaction type, currency, seller, lines and totals.
    - On each line: item code, description, quantity, unit price, VAT rate and VAT category.
    - Each total.
    - Only `discount` keeps a default of 0, meaning no discount.
  - **Time and timezone.** A required `timezone` field takes an IANA name, such as `Asia/Riyadh`. QR tag 3 is the local issue time converted to UTC (`utc_timestamp`).
  - **Real dates and times.** The time pattern is anchored at both ends. The date, time and zone must parse as real values, so 2026-02-30, 25:00 and unknown zones fail.
  - **Docstring and VAT rule.** The docstring no longer claims immutability guardrails. The VAT number rule is labelled UNVERIFIED, because no official source is cited.
- `components/compliance/zatca_sa/tests/test_phase1.py`: fixtures now carry every mandatory field. Six new tests cover:
  - missing invoice, line and total fields;
  - UTC conversion, including crossing midnight into the previous UTC day;
  - trailing characters in the time;
  - impossible dates, times and zones;
  - an Arabic seller name over 255 bytes.
- `apps/engine/change_engine/change_engine/tests/test_zatca_phase1_engine.py`: the fixture gets a timezone and currency.
- `components/compliance/zatca_sa/manifest.json`: licence goes from `MIT` to `LicenseRef-Proprietary`, matching the repo LICENSE.
- `components/README.md`: the immutability claim is replaced by what the code does.

## Evidence
- `python3 -m unittest discover -s components/compliance/zatca_sa/tests -t .`: 26 tests, OK.
- The engine wrapper test: 2 tests, OK.
- The manifest was not validated against the schema with a validator, because `jsonschema` is not installed on this machine.

## Not done (left for the review or later rows)
- **Line totals against header totals.** Not added. Under ADR-0031, the engine is the one calculation authority. A useful check would compare the engine's own line net amounts with its header, not recompute lines. That needs the engine's line fields in the input, and is proposed for the ERP-007 and CMP-004 inputs.
- **The import from `components.`.** `apps/engine` still imports `components.`, which may not resolve on a bench. Unchanged.
- **Test file length.** It is now 586 lines, over the ~500 guide. It can be split in a later change.
- **ADR-0031 conditions still open:**
  - A named line-by-line human reviewer who did not prompt this code: Eldon.
  - The accountant's review of the tax maths before Phase 2.
  - ZATCA sandbox verification.
  - The manifest still says `reviewed` with an empty `reviewedBy` (Q-19 is answered, but its schema change has not landed).

## Different-model review (Codex, GPT-6.1 Terra, read-only) and fixes
The review asked for changes. Two items were blocking and one was a should-fix. All three are fixed in this session (same model and prompt as above, with the review as the brief).
- **Blocking: the direct dataclass path still had defaults** (`vat_category` "S", `currency` "SAR"). Both now default to empty, and validation refuses empty values. New tests cover callers that build the dataclasses directly.
- **Blocking: `transaction_type` was not validated.** A misspelled credit note skipped the reference checks. Now only these pairs are allowed:
  - `standard`: `tax_invoice`, `credit_note` or `debit_note`.
  - `simplified`: `simplified_tax_invoice`, `credit_note` or `debit_note`.
  - New tests cover a misspelled type and a mismatched pair.
- **Should fix: DST.** Nonexistent and ambiguous local times in zones with daylight saving are now refused. Tests cover Europe/Berlin spring-forward and fall-back; Asia/Riyadh has no daylight saving.
- Component tests: 31, OK. Engine wrapper tests: 2, OK.

## Decisions
- None.

## Tokens or cost
Unknown.

## Next step
Eldon reviews #43 line by line (ADR-0031 condition 2). #42 merges first.
