# Session log: erp-006-arabic-gap-audit

Date: 2026-11-14
Author: partner
Tool and model: claude-code / claude-opus-5-5
Plan IDs: ERP-006

## Summary
Measured Arabic coverage of the v1 trading scope on the pinned bench: the shipped catalogues cover 92.1% of in-scope strings, but Arabic does not load at runtime on our bench.

## Files touched
- docs/specs/arabic-translation-gap-trading.md: new; method, coverage per area, the complete list of 152 missing strings, risks, proposed tasks.
- docs/PLAN.md: ERP-006 set to doing (step 1 of the row done; the row is not finished).
- docs/open-questions.md: Q-28 (accountant reviewer for Arabic terms), Q-29 (upstream contribution).

## Decisions
- None. Tasks in section 6 of the spec are PROPOSED.
- The Codex delegate (GPT-6.1 Terra) found the catalogues but did not finish; this session computed the numbers and wrote the spec. Cross-model review is still owed: the other founder should review with a model other than Claude.

## Evidence (2026-11-14, read-only, synthetic site erp001.localhost)
- Shipped `ar.po` (frappe, erpnext, hrms): 15,996 non-empty entries (15,846 differ from English), 0 fuzzy.
- In-scope unique strings: 1,922; translated 1,770; missing 152. Report names: 30 of 30 unconditional translated, plus the batch-only report.
- Runtime: `get_translations_from_apps("ar")` returned 0 strings; no `sites/assets/locale` folder because our entrypoint replaces the upstream one that links `sites/assets` to `assets`; no compiled hrms catalogue; 0 Translation records for ar.

## Review (Antigravity, Gemini 4 Hydrogen, cross-model, read-only on the bench)
- Confirmed: runtime loader returns 0 strings, no `sites/assets/locale`, no compiled hrms catalogue, 0 Translation records; Sales Invoice, Customer, Selling and Buying counts match.
- Fixed from the review: the root cause (our entrypoint drops the upstream `sites/assets` link; the volume was not the cause); documented that labels are stripped before lookup as the engine does, and the 10 trailing-whitespace strings this makes unreachable; stated which ERP-005 doctypes are and are not counted; report count wording (30 unconditional plus one batch-only); entry count (15,846 differ from English).

## Tokens or cost
Not measured.

## Next step
ERP-006: runtime loading is fixed in PR #39 (section 6 task 1). Next, supply missing strings as configuration and get the accountant terminology review (Q-28).
